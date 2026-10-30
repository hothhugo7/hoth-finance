"""Importação de extratos: prévia (revisável no Excel) e gravação na planilha em uso.

Fluxo:
1. `previa()` lê o extrato, separa o que já existe na planilha e classifica os novos.
2. `salvar_previa()` gera um Excel onde você confirma ou corrige a conta de cada lançamento.
3. `importar()` lê essa prévia revisada e grava na planilha em uso (com backup antes).
"""
import datetime as dt
import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

from .arquivo import abrir_planilha
from .classificador import Classificador
from .comprovantes import casar, ler_pasta
from .gravacao import PlanilhaEmUso
from .leitores import ler_extrato
from .texto import chave

COLUNAS = ["id", "banco", "data", "ano", "mes", "descricao", "documento", "valor", "conta"]
PASTA_COMPROVANTES = r"\\servidor\financeiro\FECHAMENTO FINANCEIRO\Comprovantes de pagamento Santander"
COL_CONTA = "Conta (confirme ou corrija)"


def sha256(caminho) -> str:
    return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()


def carregar_lancamentos(planilha) -> list[dict]:
    wb = abrir_planilha(planilha, read_only=True, data_only=True)
    out = []
    try:
        for row in wb["Lançamentos"].iter_rows(min_row=2, max_col=9, values_only=True):
            if not row[0] and not row[2]:
                continue
            l = dict(zip(COLUNAS, row))
            if isinstance(l["data"], dt.datetime):
                l["data"] = l["data"].date()
            l["conta"] = l["conta"] or ""
            out.append(l)
    finally:
        wb.close()
    return out


def arquivo_regras_fixas(planilha) -> Path:
    """Fica ao lado da planilha, na rede, para valer em todos os computadores."""
    return Path(planilha).with_name("Regras fixas.json")


def carregar_regras_fixas(planilha) -> dict:
    """{código do fornecedor: conta ("" = sempre revisar)}. Sem o arquivo, não há regras fixas."""
    caminho = arquivo_regras_fixas(planilha)
    if not caminho.exists():
        return {}
    return {codigo: r["conta"] for codigo, r in json.loads(caminho.read_text(encoding="utf-8")).items()}


def salvar_regra_fixa(planilha, chave_regra: str, nome: str, conta: str | None):
    """Inclui/altera (conta, "" = sempre revisar) ou remove (None) uma regra fixa. A versão anterior fica em .bak."""
    caminho = arquivo_regras_fixas(planilha)
    regras = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {}
    if conta is None:
        regras.pop(chave_regra, None)
    else:
        campo = "descricao" if chave_regra.startswith("desc:") else "fornecedor"
        regras[chave_regra] = {campo: nome, "conta": conta}
    if caminho.exists():
        shutil.copy2(caminho, caminho.with_name(caminho.name + ".bak"))
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(json.dumps(dict(sorted(regras.items())), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, caminho)


def titulos_identificados(lancamentos, comprovantes) -> dict:
    casados = casar([l for l in lancamentos if l["banco"] == "Santander"], comprovantes)
    return {i: r["comprovante"].favorecido for i, r in casados.items() if r["comprovante"]}


def debitos_de_faturas_abertas() -> set[str]:
    """IDs dos débitos de fatura do cartão já trocados pelas compras: contam como "já está na planilha", senão
    reimportar o extrato traria o débito de volta (em dobro com as compras)."""
    from . import config
    from .titulos import ArquivoTitulos
    try:
        return ArquivoTitulos.da_config(config.carregar()).ler().debitos_abertos()
    except (OSError, KeyError, ValueError):
        return set()


def previa(extrato, planilha, pasta_comprovantes=PASTA_COMPROVANTES) -> dict:
    lido = ler_extrato(extrato)
    historico = carregar_lancamentos(planilha)
    ids = {l["id"] for l in historico} | debitos_de_faturas_abertas()
    novos = [l for l in lido["lancamentos"] if l["id"] not in ids]
    comprovantes, nao_lidos = ler_pasta(pasta_comprovantes) if lido["banco"] == "Santander" else ([], [])
    clf = Classificador(historico, titulos_identificados(historico, comprovantes), carregar_regras_fixas(planilha))
    casados = casar(novos, comprovantes)
    for l in novos:
        c = casados.get(l["id"], {})
        favorecido = c["comprovante"].favorecido if c.get("comprovante") else ""
        res = clf.classificar(l, favorecido)
        l.update(conta=res.conta, proposta=res.conta, regra=res.regra, confianca=res.confianca,
                 sugestoes=res.sugestoes, favorecido=favorecido, casamento=c.get("regra", ""),
                 comprovante=c["comprovante"].arquivo if c.get("comprovante") else "",
                 candidatos=[f"{x.favorecido} ({x.arquivo})" for x in c.get("candidatos", [])])
    saldos = []
    if lido.get("saldo_final") is not None and lido.get("saldo_data") and lido["saldo_data"].day == 1:
        d = lido["saldo_data"]
        saldos.append({"banco": lido["banco"], "ano": d.year, "mes": d.month, "saldo": lido["saldo_final"]})
    return {"banco": lido["banco"], "conta_bancaria": lido["conta"], "extrato": str(extrato),
            "sha256": sha256(extrato), "lidos": len(lido["lancamentos"]),
            "ja_existem": len(lido["lancamentos"]) - len(novos), "novos": novos, "saldos": saldos,
            "comprovantes_nao_lidos": nao_lidos}


def salvar_previa(p: dict, caminho, contas: list[str]):
    """Excel de revisão. A coluna "Conta (confirme ou corrija)" tem a lista do Plano de Contas.
    Deixe em branco o que ainda não sabe: entra na planilha como Sem classificação."""
    if Path(caminho).exists() and previa_revisada(caminho):
        raise ValueError(f"{Path(caminho).name} já foi revisada e salva depois de gerada. Grave essa prévia ou "
                         "escolha outro nome; ela não é sobrescrita.")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Prévia"
    cab = ["ID", "Data", "Descrição", "Valor", COL_CONTA, "Conta proposta", "Regra", "Confiança",
           "Favorecido (comprovante)", "Comprovante", "Sugestões", "Candidatos (ambíguo)"]
    ws.append(cab)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="C9CDD2"), PatternFill("solid", fgColor="1E1F22")
    amarelo, verde = PatternFill("solid", fgColor="FFF8E1"), PatternFill("solid", fgColor="E8F5E9")
    for l in sorted(p["novos"], key=lambda l: (bool(l["proposta"]), l["data"])):
        ws.append([l["id"], l["data"], l["descricao"], l["valor"], l["proposta"], l["proposta"], l["regra"],
                   l["confianca"], l["favorecido"], l["comprovante"],
                   "; ".join(f"{s[0]} ({s[1]})" for s in l["sugestoes"]), "; ".join(l["candidatos"])])
        r = ws.max_row
        ws.cell(r, 2).number_format = "DD/MM/YYYY"
        ws.cell(r, 4).number_format = "#,##0.00;-#,##0.00"
        ws.cell(r, 5).fill = verde if l["proposta"] else amarelo
    for i, w in enumerate([18, 11, 52, 13, 40, 34, 11, 10, 32, 24, 70, 50], start=1):
        ws.column_dimensions[L(i)].width = w
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:L{max(2, ws.max_row)}"

    lista = wb.create_sheet("Contas")
    for i, conta in enumerate(contas, start=1):
        lista.cell(i, 1, conta)
    lista.sheet_state = "hidden"
    dv = DataValidation(type="list", formula1=f"=Contas!$A$1:$A${len(contas)}", allow_blank=True,
                        showErrorMessage=True, errorTitle="Conta inválida", error="Escolha uma conta da lista.")
    ws.add_data_validation(dv)
    dv.add(f"E2:E{max(2, ws.max_row)}")

    ctl = wb.create_sheet("Controle")
    for k in ("banco", "conta_bancaria", "extrato", "sha256", "lidos", "ja_existem"):
        ctl.append([k, p[k]])
    ctl.append(["gerada_em", dt.datetime.now().replace(microsecond=0)])
    ctl.sheet_state = "hidden"
    wb.save(caminho)


def previa_revisada(caminho) -> bool:
    """Alguma conta mudou em relação à proposta, ou o arquivo foi salvo de novo (no Excel) depois de gerado."""
    try:
        controle, escolhas = ler_previa(caminho)
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        try:
            ws = wb["Prévia"]
            cab = list(next(ws.iter_rows(max_row=1, values_only=True)))
            i_id, i_prop = cab.index("ID"), cab.index("Conta proposta")
            propostas = {r[i_id]: (r[i_prop] or "").strip() for r in ws.iter_rows(min_row=2, values_only=True) if r[i_id]}
        finally:
            wb.close()
    except (KeyError, ValueError, StopIteration, OSError):
        return True   # não é uma prévia nossa: não mexe
    gerada = controle.get("gerada_em")
    salva = dt.datetime.fromtimestamp(Path(caminho).stat().st_mtime)
    return escolhas != propostas or (isinstance(gerada, dt.datetime) and salva > gerada + dt.timedelta(minutes=1))


def ler_previa(caminho) -> tuple[dict, dict]:
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    try:
        controle = {r[0]: r[1] for r in wb["Controle"].iter_rows(values_only=True) if r[0]}
        ws = wb["Prévia"]
        cab = list(next(ws.iter_rows(max_row=1, values_only=True)))
        i_id, i_conta = cab.index("ID"), cab.index(COL_CONTA)
        escolhas = {r[i_id]: (r[i_conta] or "").strip() for r in ws.iter_rows(min_row=2, values_only=True) if r[i_id]}
    finally:
        wb.close()
    return controle, escolhas


def importar(caminho_previa, planilha: PlanilhaEmUso, pasta_comprovantes=PASTA_COMPROVANTES) -> dict:
    controle, escolhas = ler_previa(caminho_previa)
    return importar_escolhas(controle["extrato"], controle["sha256"], escolhas, planilha, pasta_comprovantes)


def importar_escolhas(extrato, sha_previa: str, escolhas: dict, planilha: PlanilhaEmUso,
                      pasta_comprovantes=PASTA_COMPROVANTES) -> dict:
    """`escolhas` = {id do lançamento: conta escolhida ("" = sem classificação)}."""
    if sha256(extrato) != sha_previa:
        raise ValueError("O extrato mudou depois da prévia. Gere a prévia de novo.")
    p = previa(extrato, planilha.caminho, pasta_comprovantes)
    validas = {chave(c): c for c in planilha.contas()}
    invalidas = sorted({c for c in escolhas.values() if c and chave(c) not in validas})
    if invalidas:
        raise ValueError("Contas que não existem no Plano de Contas: " + "; ".join(invalidas))
    nome_arquivo = Path(extrato).name
    registros, cont = [], Counter()
    for l in p["novos"]:
        if l["id"] not in escolhas:
            cont["fora da prévia"] += 1   # apareceu depois da prévia: fica para a próxima
            continue
        conta = validas.get(chave(escolhas[l["id"]]), "")
        if not conta:
            origem, cont_k = f"Importação {p['banco']}: pendente de revisão", "pendentes"
        elif conta == l["proposta"]:
            origem, cont_k = f"Importação {p['banco']}: automática ({l['regra']}, {l['confianca']})", "automáticos"
        else:
            origem, cont_k = f"Importação {p['banco']}: revisão manual", "revisados"
        cont[cont_k] += 1
        obs = []
        if l["favorecido"]:
            obs.append(f"Comprovante: {l['favorecido']} ({l['comprovante']}, {l['casamento']})")
        if l.get("cpf_cnpj"):
            obs.append(f"CPF/CNPJ {l['cpf_cnpj']}")
        if not conta and l["sugestoes"]:
            obs.append("Sugestões: " + "; ".join(s[0] for s in l["sugestoes"]))
        registros.append({**l, "conta": conta, "origem": origem, "referencia": nome_arquivo,
                          "observacao": " | ".join(obs)})
    datas = [l["data"] for l in registros]
    periodo = f"{min(datas):%d/%m} a {max(datas):%d/%m/%Y}" if datas else "sem lançamentos novos"
    detalhe = (f"{len(registros)} lançamentos {p['banco']} de {periodo}: {cont['automáticos']} automáticos, "
               f"{cont['revisados']} revisados, {cont['pendentes']} pendentes")
    if not registros:
        # Nada novo: a planilha não é aberta nem copiada para o BKP.
        return {"detalhe": "Nenhum lançamento novo: tudo já estava na planilha.", "gravados": 0,
                "duplicados_ignorados": p["ja_existem"], "saldos": [], "backup": None,
                "fora_da_previa": cont["fora da prévia"], "ja_existiam_na_previa": p["ja_existem"]}
    info = planilha.gravar_lancamentos(registros, acao=f"Importação {p['banco']}", detalhe=detalhe,
                                       arquivo=str(extrato), saldos=p["saldos"])
    info.update(detalhe=detalhe, fora_da_previa=cont["fora da prévia"], ja_existiam_na_previa=p["ja_existem"])
    return info
