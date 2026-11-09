"""Contas a pagar: títulos do RET, malotes da lotérica e o arquivo onde ficam guardados.

Os títulos ficam num arquivo separado da planilha oficial (`Hoth - Contas a Pagar e Fluxo 2026.xlsx`, na mesma
pasta), porque mudam todo dia e não são caixa realizado. Um título nunca é apagado: reimportar o RET atualiza
valor e vencimento e marca os que saíram do relatório; se foi pago, quem diz é a conciliação (`conciliacao.py`).

O arquivo é gravado inteiro pelo openpyxl (não tem fórmulas), numa cópia temporária, com backup antes em
`BKP\\Contas a Pagar` — o mesmo cuidado da planilha oficial, sem precisar do Excel.
"""
import datetime as dt
import hashlib
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.table import Table, TableStyleInfo

from .gravacao import PlanilhaEmUso, _substituir
from .texto import chave, limpar

NOME_ARQUIVO = "Hoth - Contas a Pagar e Fluxo 2026.xlsx"

# Marcações feitas pelo usuário; valem antes da conciliação automática.
MARCAS = {
    "": "",
    "confirmado": "Pagamento confirmado",
    "aguardando_fatura": "Aguardando fatura (cartão de crédito)",
    "pago_fora": "Pago fora (baixa manual)",
    "cancelado": "Cancelado",
}

COLUNAS_TITULO = [
    ("ID", "id"), ("Código", "codigo"), ("Fornecedor", "fornecedor"), ("Documento", "documento"),
    ("Parcela", "parcela"), ("Duplicata", "duplicata"), ("Compra", "compra"), ("Vencimento", "vencimento"),
    ("Valor", "valor"), ("Banco RET", "banco_ret"), ("Cobrança", "cobranca"), ("Conta", "conta"),
    ("No RET", "no_ret"), ("Primeira importação", "primeira_importacao"), ("Última vez no RET", "ultima_vez_ret"),
    ("Marca", "marca"), ("Lançamento confirmado", "lancamento_confirmado"), ("Observação", "observacao"),
    ("Histórico", "historico"),
    # Resultado da última conciliação (gravado para o Power BI; o app sempre recalcula)
    ("Situação", "situacao"), ("Prova", "prova"), ("ID lançamento", "id_lancamento"), ("Data pagamento", "data_pagamento"),
    ("Valor pago", "valor_pago"), ("Malote", "malote"),
]
COLUNAS_MALOTE = [("ID", "id"), ("Envio", "envio"), ("Total da fita", "total_fita"), ("Observação", "observacao"),
                  ("Criado em", "criado_em")]
COLUNAS_MALOTE_VALOR = [("Malote", "malote"), ("Ordem", "ordem"), ("Valor", "valor"), ("ID título", "titulo"),
                        ("Observação", "observacao")]
COLUNAS_AUDITORIA = [("Data/hora", "quando"), ("Ação", "acao"), ("Detalhe", "detalhe"), ("Backup", "backup")]
COLUNAS_CATEGORIA = [("Código", "codigo"), ("Fornecedor", "fornecedor"), ("Categoria", "categoria"),
                     ("Atualizado em", "atualizado_em")]
COLUNAS_LISTA_CATEGORIAS = [("Categoria", "nome"), ("Ordem", "ordem")]
COLUNAS_FATURA = [("ID", "id"), ("Vencimento", "vencimento"), ("Total", "total"), ("Cartão", "cartao"),
                  ("Arquivo", "arquivo"), ("SHA256", "sha256"), ("ID débito", "id_debito"), ("Data débito", "data_debito"),
                  ("Descrição débito", "descricao_debito"), ("Conta débito", "conta_debito"),
                  ("Origem débito", "origem_debito"), ("Itens", "itens"), ("IDs itens", "ids_itens"),
                  ("Agrupada", "agrupada"), ("Situação", "situacao"), ("Aberta em", "aberta_em"), ("Backup", "backup")]
COLUNAS_ENTRADA = [("ID", "id"), ("Data", "data"), ("Descrição", "descricao"), ("Valor", "valor"), ("Forma", "forma")]

CATEGORIAS_PADRAO = ["MERCADORIA", "DESPESA", "FINANCEIRO"]


# ------------------------------------------------------------------------------------------- leitura do RET
def _data_br(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    t = limpar(v)
    return dt.datetime.strptime(t, "%d/%m/%Y").date() if re.fullmatch(r"\d{2}/\d{2}/\d{4}", t) else None


def _texto_ret(v) -> str:
    # O RET grava parte dos campos como número: 62052.0 -> "62052".
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return limpar(v)


def doc_normalizado(doc) -> str:
    """Documento para comparar: sem acento, espaços e zeros à esquerda ("002207399" = "2207399")."""
    return re.sub(r"\s", "", chave(doc)).lstrip("0")


def id_titulo(codigo, documento, parcela, duplicata, compra, ocorrencia: int) -> str:
    base = "|".join([codigo, doc_normalizado(documento), str(parcela), chave(duplicata),
                     compra.isoformat() if compra else "", str(ocorrencia)])
    return hashlib.sha1(base.encode()).hexdigest()[:16].upper()


def eh_ret_abertos(linhas) -> bool:
    return bool(linhas) and [chave(c) for c in linhas[0][:2]] == ["VENCTO", "ATRASO"]


def ler_ret_abertos(caminho, linhas=None) -> dict:
    """Relatório de contas a pagar em aberto do RET: Vencto | Atraso | Documento | Par | Duplicata | Fornecedor |
    Compra | Loja | A Pagar R$ | Cobrança | Banco | Cheque."""
    if linhas is None:
        from .leitores import _linhas_xls
        linhas = _linhas_xls(caminho)
    if not eh_ret_abertos(linhas):
        raise ValueError(f"{Path(caminho).name}: não é o relatório de contas a pagar em aberto do RET "
                         "(cabeçalho 'Vencto | Atraso' não encontrado)")
    cab = [chave(c) for c in linhas[0]]
    c = {n: cab.index(n) for n in ("VENCTO", "DOCUMENTO", "PAR", "DUPLICATA", "FORNECEDOR", "COMPRA", "A PAGAR R$",
                                   "COBRANCA", "BANCO")}
    titulos, ocorrencias = [], Counter()
    for row in linhas[1:]:
        venc, valor, fornecedor = _data_br(row[c["VENCTO"]]), row[c["A PAGAR R$"]], limpar(row[c["FORNECEDOR"]])
        if not venc or not isinstance(valor, (int, float)) or not fornecedor:
            continue   # linha de total ("14 registro(s) listado(s)") ou em branco
        m = re.match(r"^(\d{3,6}) - ", fornecedor)
        codigo = m.group(1) if m else ""
        documento, duplicata = _texto_ret(row[c["DOCUMENTO"]]), _texto_ret(row[c["DUPLICATA"]])
        parcela = int(row[c["PAR"]]) if isinstance(row[c["PAR"]], float) else limpar(row[c["PAR"]])
        compra = _data_br(row[c["COMPRA"]])
        k = (codigo, doc_normalizado(documento), str(parcela), chave(duplicata), compra)
        ocorrencias[k] += 1
        titulos.append({
            "id": id_titulo(codigo, documento, parcela, duplicata, compra, ocorrencias[k]), "codigo": codigo,
            "fornecedor": fornecedor, "documento": documento, "parcela": parcela, "duplicata": duplicata,
            "compra": compra, "vencimento": venc, "valor": round(float(valor), 2),
            "banco_ret": _texto_ret(row[c["BANCO"]]), "cobranca": _texto_ret(row[c["COBRANCA"]])})
    if not titulos:
        raise ValueError(f"{Path(caminho).name}: nenhum título em aberto no relatório")
    datas = [t["vencimento"] for t in titulos]
    return {"titulos": titulos, "de": min(datas), "ate": max(datas)}


# --------------------------------------------------------------------------------------------- o arquivo
@dataclass
class Carteira:
    titulos: list = field(default_factory=list)
    malotes: list = field(default_factory=list)
    malote_valores: list = field(default_factory=list)
    auditoria: list = field(default_factory=list)
    categorias: list = field(default_factory=list)          # categoria por código de fornecedor
    lista_categorias: list = field(default_factory=list)    # nomes (Mercadoria, Despesa, ... e as criadas)
    entradas: list = field(default_factory=list)            # entradas previstas, digitadas no app
    faturas: list = field(default_factory=list)             # faturas do cartão abertas (débito trocado pelos itens)

    def debitos_abertos(self) -> set[str]:
        """IDs das linhas de débito de fatura que foram trocadas pelos itens (não voltam ao reimportar o extrato)."""
        return {str(f["id_debito"]) for f in self.faturas if f.get("situacao") == "aberta" and f.get("id_debito")}

    def itens_de_fatura(self) -> set[str]:
        return {i for f in self.faturas if f.get("situacao") == "aberta" for i in str(f.get("ids_itens") or "").split(";") if i}

    def por_id(self) -> dict:
        return {t["id"]: t for t in self.titulos}

    def nomes_categorias(self) -> list[str]:
        if not self.lista_categorias:
            return list(CATEGORIAS_PADRAO)
        return [c["nome"] for c in sorted(self.lista_categorias, key=lambda c: (c.get("ordem") or 0, c["nome"]))]

    def categoria_por_codigo(self) -> dict:
        return {str(c["codigo"]): c["categoria"] for c in self.categorias if c.get("categoria")}


def _ler_tabela(ws, colunas) -> list[dict]:
    linhas = ws.iter_rows(values_only=True)
    cab = list(next(linhas, ()))
    campo = dict(colunas)
    saida = []
    for r in linhas:
        if not any(v not in (None, "") for v in r):
            continue
        d = {campo[c]: v for c, v in zip(cab, r) if c in campo}
        for k, v in d.items():
            if isinstance(v, dt.datetime) and k not in ("criado_em", "quando"):
                d[k] = v.date()
            elif v is None:
                d[k] = ""
        saida.append(d)
    return saida


class ArquivoTitulos:
    def __init__(self, caminho, pasta_bkp, manter_backups: int = 60):
        self.caminho = Path(caminho)
        self.pasta_bkp = Path(pasta_bkp)
        self._uso = PlanilhaEmUso(self.caminho, self.pasta_bkp, manter_backups)

    @classmethod
    def da_config(cls, cfg: dict) -> "ArquivoTitulos":
        caminho = cfg.get("arquivo_titulos") or str(Path(cfg["planilha"]).with_name(NOME_ARQUIVO))
        bkp = cfg.get("pasta_bkp_titulos") or str(Path(cfg["pasta_bkp"]) / "Contas a Pagar")
        return cls(caminho, bkp, cfg.get("manter_backups", 60))

    def ler(self) -> Carteira:
        if not self.caminho.exists():
            return Carteira()
        wb = openpyxl.load_workbook(self.caminho, read_only=True, data_only=True)
        try:
            aba = lambda nome, colunas: _ler_tabela(wb[nome], colunas) if nome in wb.sheetnames else []
            return Carteira(aba("Títulos", COLUNAS_TITULO), aba("Malotes", COLUNAS_MALOTE),
                            aba("Malote valores", COLUNAS_MALOTE_VALOR), aba("Auditoria", COLUNAS_AUDITORIA),
                            aba("Categorias", COLUNAS_CATEGORIA), aba("Lista de categorias", COLUNAS_LISTA_CATEGORIAS),
                            aba("Entradas", COLUNAS_ENTRADA), aba("Faturas", COLUNAS_FATURA))
        finally:
            wb.close()

    def assinatura(self):
        """Muda quando o arquivo muda (para cache)."""
        if not self.caminho.exists():
            return None
        st = self.caminho.stat()
        return (st.st_mtime_ns, st.st_size)

    def gravar(self, carteira: Carteira, acao: str, detalhe: str) -> Path | None:
        """Grava a carteira inteira: confere que o arquivo está fechado, faz backup, grava numa cópia e troca."""
        backup = None
        if self.caminho.exists():
            self._uso.verificar_livre()
            backup = self._uso.backup(acao)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        carteira.auditoria.append({"quando": dt.datetime.now().replace(microsecond=0), "acao": acao,
                                   "detalhe": detalhe, "backup": str(backup or "")})
        tmp = self.caminho.with_name(f"~hoth_gravando_{self.caminho.name}")
        try:
            _salvar_xlsx(carteira, tmp)
            if self.caminho.exists():
                self._uso.verificar_livre()
            _substituir(tmp, self.caminho)
        except BaseException:
            if backup:
                backup.unlink(missing_ok=True)
            raise
        finally:
            if tmp.exists():
                tmp.unlink()
        self._uso._limpar_backups()
        return backup


def _salvar_xlsx(c: Carteira, caminho: Path):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    abas = [("Títulos", "tbTitulos", COLUNAS_TITULO, c.titulos), ("Malotes", "tbMalotes", COLUNAS_MALOTE, c.malotes),
            ("Malote valores", "tbMaloteValores", COLUNAS_MALOTE_VALOR, c.malote_valores),
            ("Categorias", "tbCategorias", COLUNAS_CATEGORIA, c.categorias),
            ("Lista de categorias", "tbListaCategorias", COLUNAS_LISTA_CATEGORIAS,
             c.lista_categorias or [{"nome": n, "ordem": i} for i, n in enumerate(CATEGORIAS_PADRAO, 1)]),
            ("Entradas", "tbEntradas", COLUNAS_ENTRADA, c.entradas),
            ("Faturas", "tbFaturas", COLUNAS_FATURA, c.faturas),
            ("Auditoria", "tbAuditoriaCP", COLUNAS_AUDITORIA, c.auditoria)]
    for aba, tabela, colunas, linhas in abas:
        ws = wb.create_sheet(aba)
        ws.append([c for c, _ in colunas])
        for d in linhas:
            ws.append([_celula(d.get(k)) for _, k in colunas])
        for i, (cab, k) in enumerate(colunas, start=1):
            ws.column_dimensions[L(i)].width = max(10, min(45, len(cab) + 4))
            cel = ws.cell(1, i)
            cel.font, cel.fill = Font(bold=True, color="E6E8EB"), PatternFill("solid", fgColor="1B1D21")
            for r in range(2, len(linhas) + 2):
                cel = ws.cell(r, i)
                if isinstance(cel.value, dt.datetime):
                    cel.number_format = "DD/MM/YYYY HH:MM"
                elif isinstance(cel.value, dt.date):
                    cel.number_format = "DD/MM/YYYY"
                elif isinstance(cel.value, float):
                    cel.number_format = "#,##0.00"
                elif k in ("id", "documento", "codigo", "titulo", "duplicata", "id_lancamento", "nome", "id_debito",
                           "ids_itens", "sha256"):
                    cel.number_format = "@"
        ref = f"A1:{L(len(colunas))}{max(2, len(linhas) + 1)}"
        if not linhas:
            ws.append([None] * len(colunas))
        t = Table(displayName=tabela, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium1", showRowStripes=True)
        ws.add_table(t)
        ws.freeze_panes = "A2"
    wb.save(caminho)


def _celula(v):
    if v is None or v == "":
        return None
    if isinstance(v, (list, dict, set)):
        return str(v)
    return v


# ------------------------------------------------------------------------------------- importar o RET
def comparar_importacao(carteira: Carteira, lido: dict) -> dict:
    """Prévia: o que entra, o que muda e o que saiu do relatório (só dentro do período que o relatório cobre)."""
    atuais = carteira.por_id()
    no_relatorio = {t["id"] for t in lido["titulos"]}
    novos = [t for t in lido["titulos"] if t["id"] not in atuais]
    mudaram = []
    for t in lido["titulos"]:
        a = atuais.get(t["id"])
        if a and (round(float(a["valor"] or 0), 2) != t["valor"] or a["vencimento"] != t["vencimento"]):
            mudaram.append({**t, "valor_antes": a["valor"], "vencimento_antes": a["vencimento"]})
    sairam = [a for a in carteira.titulos if a["id"] not in no_relatorio and a.get("no_ret") == "Sim"
              and isinstance(a.get("vencimento"), dt.date) and lido["de"] <= a["vencimento"] <= lido["ate"]]
    return {"novos": novos, "mudaram": mudaram, "sairam": sairam, "de": lido["de"], "ate": lido["ate"],
            "lidos": len(lido["titulos"]), "total": round(sum(t["valor"] for t in lido["titulos"]), 2)}


def aplicar_importacao(carteira: Carteira, lido: dict, classificar=None, hoje: dt.date | None = None) -> dict:
    """Atualiza a carteira com o relatório. `classificar(titulo) -> conta` (opcional)."""
    hoje = hoje or dt.date.today()
    cmp = comparar_importacao(carteira, lido)
    atuais = carteira.por_id()
    for t in lido["titulos"]:
        a = atuais.get(t["id"])
        if a is None:
            novo = {**t, "conta": classificar(t) if classificar else "", "no_ret": "Sim",
                    "primeira_importacao": hoje, "ultima_vez_ret": hoje, "marca": "", "lancamento_confirmado": "",
                    "observacao": "", "historico": ""}
            carteira.titulos.append(novo)
            continue
        mudancas = []
        if round(float(a["valor"] or 0), 2) != t["valor"]:
            mudancas.append(f"valor {a['valor']} -> {t['valor']:.2f}")
        if a["vencimento"] != t["vencimento"]:
            antes = a["vencimento"].strftime("%d/%m/%Y") if isinstance(a["vencimento"], dt.date) else a["vencimento"]
            mudancas.append(f"vencimento {antes} -> {t['vencimento']:%d/%m/%Y}")
        if mudancas:
            a["historico"] = "; ".join(x for x in [a.get("historico"), f"{hoje:%d/%m/%Y}: " + ", ".join(mudancas)] if x)
        a.update({k: t[k] for k in ("fornecedor", "vencimento", "valor", "banco_ret", "cobranca")})
        a["no_ret"], a["ultima_vez_ret"] = "Sim", hoje
        if not a.get("conta") and classificar:
            a["conta"] = classificar(t)
    for a in cmp["sairam"]:
        a["no_ret"] = "Não"
        a["historico"] = "; ".join(x for x in [a.get("historico"), f"{hoje:%d/%m/%Y}: saiu do RET em aberto"] if x)
    return cmp


# ------------------------------------------------------------------------------------------- malotes
def novo_id_malote(carteira: Carteira, envio: dt.date) -> str:
    base = f"M{envio:%Y%m%d}"
    usados = {str(m["id"]) for m in carteira.malotes}
    n = 1
    while f"{base}-{n}" in usados:   # malote excluído deixa buraco na numeração: contar repetiria um ID
        n += 1
    return f"{base}-{n}"


def titulos_em_malote(carteira: Carteira) -> dict:
    """{id do título: id do malote}."""
    return {v["titulo"]: v["malote"] for v in carteira.malote_valores if v.get("titulo")}


def conferir_titulos_do_malote(carteira: Carteira, titulos: list[str], ignorar: str = ""):
    """Recusa título que já está em outro malote (`ignorar` = o próprio malote, na edição) ou repetido na fita."""
    em_outro = {t: m for t, m in titulos_em_malote(carteira).items() if m != ignorar}
    repetidos = [t for t in titulos if t and t in em_outro]
    if repetidos:
        raise ValueError(f"{len(repetidos)} título(s) já estão em outro malote ({em_outro[repetidos[0]]}).")
    ids = [t for t in titulos if t]
    if len(ids) != len(set(ids)):
        raise ValueError("O mesmo título foi escolhido para dois valores.")


def _malote(carteira: Carteira, mid: str) -> dict:
    malote = next((m for m in carteira.malotes if m["id"] == mid), None)
    if malote is None:
        raise ValueError(f"Malote {mid} não encontrado. Atualize a tela.")
    return malote


def excluir_malote(carteira: Carteira, mid: str) -> dict:
    """Tira o malote e os valores dele; os títulos voltam a ficar livres. Devolve o malote excluído."""
    malote = _malote(carteira, mid)
    carteira.malotes.remove(malote)
    carteira.malote_valores = [v for v in carteira.malote_valores if v["malote"] != mid]
    return malote


def editar_malote(carteira: Carteira, mid: str, envio: dt.date, total_fita, observacao: str, valores: list[dict]) -> str:
    """Troca os dados e os valores do malote. Se a data de envio mudar, o ID (que contém a data) muda junto.

    `valores`: [{valor, titulo, observacao}] na ordem da fita. Devolve o ID final.
    """
    malote = _malote(carteira, mid)
    if not valores:
        raise ValueError("O malote ficaria sem valores. Para tirar o malote inteiro, use Excluir.")
    conferir_titulos_do_malote(carteira, [v["titulo"] for v in valores], ignorar=mid)
    novo = mid if malote["envio"] == envio else novo_id_malote(carteira, envio)
    malote.update(id=novo, envio=envio, total_fita=total_fita, observacao=observacao)
    carteira.malote_valores = [v for v in carteira.malote_valores if v["malote"] != mid]
    carteira.malote_valores += [{"malote": novo, "ordem": i, "valor": round(v["valor"], 2), "titulo": v["titulo"],
                                 "observacao": v.get("observacao", "")} for i, v in enumerate(valores, start=1)]
    return novo


# ------------------------------------------------------------------------------------------ categorias
def cadastro_base(caminho) -> dict:
    """Categorias já aprovadas na versão Base do fluxo ({código: categoria}); vazio se não houver o arquivo."""
    import sqlite3
    caminho = Path(caminho)
    if not caminho.exists():
        return {}
    con = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
    try:
        return {str(c): str(cat).upper() for c, cat in con.execute("select codigo, categoria from fornecedores") if cat}
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def definir_categorias(carteira: Carteira, itens: list[dict]):
    """itens = [{codigo, fornecedor, categoria}]; categoria vazia apaga a escolha."""
    atuais = {str(c["codigo"]): c for c in carteira.categorias}
    agora = dt.datetime.now().replace(microsecond=0)
    validas = {chave(n): n for n in carteira.nomes_categorias()}
    for i in itens:
        cod, cat = str(i["codigo"]), validas.get(chave(i.get("categoria")), "")
        if i.get("categoria") and not cat:
            raise ValueError(f"Categoria não existe: {i['categoria']}")
        if cod in atuais:
            atuais[cod].update(categoria=cat, atualizado_em=agora, fornecedor=i.get("fornecedor") or atuais[cod]["fornecedor"])
        else:
            novo = {"codigo": cod, "fornecedor": i.get("fornecedor", ""), "categoria": cat, "atualizado_em": agora}
            carteira.categorias.append(novo)
            atuais[cod] = novo


def criar_categoria(carteira: Carteira, nome: str) -> str:
    nome = limpar(nome).upper()
    if not nome:
        raise ValueError("Informe o nome da categoria.")
    if chave(nome) in {chave(n) for n in carteira.nomes_categorias()}:
        raise ValueError(f"A categoria {nome} já existe.")
    if not carteira.lista_categorias:
        carteira.lista_categorias = [{"nome": n, "ordem": i} for i, n in enumerate(CATEGORIAS_PADRAO, 1)]
    carteira.lista_categorias.append({"nome": nome, "ordem": len(carteira.lista_categorias) + 1})
    return nome
