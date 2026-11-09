"""API local do app Hoth (FastAPI). Só escuta em 127.0.0.1.

Leituras usam a planilha em uso; toda gravação passa por PlanilhaEmUso (backup antes, cópia temporária,
troca no fim). Uma gravação por vez.
"""
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import colagem, config
from ..classificador import Classificador, chave_regra_descricao, codigo_fornecedor
from ..comprovantes import ler_pasta
from ..conciliacao import PAGOS, SITUACOES, aplicar_resultado, conciliar
from ..consulta import candidatos_malote
from ..fatura import (DEBITO, SenhaFatura, aberta_a_mao, achar_debito, classificar_itens,
                      itens_como_lancamentos, ler_fatura, listar_pdfs)
from ..fatura import agrupar as agrupar_itens
from ..fatura import sha256 as fatura_sha256
from ..fluxo import NOME_ARQUIVO as NOME_FLUXO
from ..fluxo import SEM_CATEGORIA, calcular, gerar_planilha, movimentos, por_mes, sugestao_entradas
from ..gravacao import PlanilhaEmUso, PlanilhaOcupada, _substituir
from ..importacao import (arquivo_regras_fixas, carregar_regras_fixas, importar_escolhas, previa, salvar_regra_fixa,
                          titulos_identificados)
from ..titulos import (MARCAS, ArquivoTitulos, aplicar_importacao, cadastro_base, comparar_importacao,
                       criar_categoria, definir_categorias, ler_ret_abertos, novo_id_malote, titulos_em_malote)
from ..plano import ErroPlano, Rascunho, editor_com_rascunho
from ..planilha_atual import aplicar_renomeacoes, ler
from ..texto import chave

RAIZ = config.RAIZ
ESTATICO = Path(__file__).resolve().parent / "static"
DADOS = RAIZ / "Dados"

_trava = threading.Lock()
_sessoes: dict[str, dict] = {}
_cache = {"chave": None, "conteudo": None}


def _planilha() -> PlanilhaEmUso:
    cfg = config.carregar()
    return PlanilhaEmUso(cfg["planilha"], cfg["pasta_bkp"], cfg["manter_backups"])


def _conteudo():
    pl = _planilha()
    st = pl.caminho.stat()
    k = (str(pl.caminho), st.st_mtime_ns, st.st_size)
    if _cache["chave"] != k:
        _cache["conteudo"], _cache["chave"] = ler(pl.caminho), k
    return _cache["conteudo"]


def _gravando(func):
    """Executa uma gravação com a trava e traduz os erros conhecidos para HTTP."""
    if not _trava.acquire(blocking=False):
        raise HTTPException(409, "Já existe uma gravação em andamento. Aguarde.")
    try:
        return func()
    except PlanilhaOcupada as e:
        raise HTTPException(423, str(e))
    except (ValueError, ErroPlano) as e:
        raise HTTPException(400, str(e))
    finally:
        _trava.release()
        _cache["chave"] = None


def _rascunho() -> Rascunho:
    return Rascunho(DADOS / "plano_rascunho.json")


def _uso(cont) -> Counter:
    uso = Counter(l["conta"] for l in cont.lancamentos if l["conta"])
    for lista in (cont.ajustes, cont.orcamento, cont.dre_manual):
        uso.update(x["conta"] for x in lista if x.get("conta"))
    return uso


app = FastAPI(title="Hoth Finance")


@app.middleware("http")
async def sem_cache(request, call_next):
    resposta = await call_next(request)
    if request.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


# ------------------------------------------------------------------- estado
@app.get("/api/estado")
def estado():
    pl = _planilha()
    cont = _conteudo()
    lanc = cont.lancamentos
    pendentes = [l for l in lanc if not l["conta"]]
    try:
        pl.verificar_livre()
        aberta = ""
    except PlanilhaOcupada as e:
        aberta = str(e)
    ultimas = [a for a in cont.auditoria if a[1] and a[1].startswith("Importação")]
    por_banco = Counter(l["banco"] for l in lanc)
    ultima_data = {}
    for l in lanc:
        if l["data"] and (l["banco"] not in ultima_data or l["data"] > ultima_data[l["banco"]]):
            ultima_data[l["banco"]] = l["data"]
    return {
        "empresa": cont.estrutura.empresa, "ano": cont.estrutura.ano, "planilha": str(pl.caminho),
        "planilha_aberta": aberta, "lancamentos": len(lanc), "pendentes": len(pendentes),
        "pendentes_valor": round(sum(l["valor"] for l in pendentes), 2),
        "bancos": [{"banco": b, "lancamentos": n, "ultima_data": ultima_data.get(b)} for b, n in por_banco.most_common()],
        "ultima_importacao": ultimas[-1] if ultimas else None, "backups": len(pl.listar_backups()),
        "rascunho_plano": len(_rascunho().operacoes()),
    }


# ---------------------------------------------------------------- importação
@app.post("/api/importacao/previa")
async def importacao_previa(arquivo: UploadFile = File(...)):
    dados = await arquivo.read()
    sufixo = Path(arquivo.filename or "").suffix.lower()
    if sufixo not in (".xlsx", ".xls", ".ofx"):
        raise HTTPException(400, "Envie o extrato do Santander (.xlsx), o OFX da Cora (.ofx) ou o relatório da lotérica do RET (.xls)")
    h = hashlib.sha256(dados).hexdigest()
    pasta = DADOS / "Extratos" / f"{dt.date.today():%Y-%m}"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{Path(arquivo.filename).stem} [{h[:8]}]{sufixo}"
    if not destino.exists():
        destino.write_bytes(dados)
    cfg = config.carregar()
    try:
        p = previa(destino, _planilha().caminho, cfg["pasta_comprovantes"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    token = secrets.token_urlsafe(12)
    _sessoes[token] = {"extrato": str(destino), "sha256": p["sha256"]}
    return {
        "token": token, "banco": p["banco"], "arquivo": arquivo.filename, "lidos": p["lidos"],
        "ja_existem": p["ja_existem"], "saldos": p["saldos"], "comprovantes_nao_lidos": p["comprovantes_nao_lidos"],
        "novos": [{
            "id": l["id"], "data": l["data"], "descricao": l["descricao"], "valor": l["valor"],
            "proposta": l["proposta"], "regra": l["regra"], "confianca": l["confianca"],
            "favorecido": l["favorecido"], "comprovante": l["comprovante"], "cpf_cnpj": l.get("cpf_cnpj", ""),
            "sugestoes": [{"conta": s[0], "motivo": s[1]} for s in l["sugestoes"]], "candidatos": l["candidatos"],
        } for l in sorted(p["novos"], key=lambda l: l["data"])],
    }


class Gravar(BaseModel):
    token: str
    escolhas: dict[str, str]


@app.post("/api/importacao/gravar")
def importacao_gravar(req: Gravar):
    s = _sessoes.get(req.token)
    if not s:
        raise HTTPException(404, "Prévia expirada. Envie o extrato de novo.")
    cfg = config.carregar()

    def fazer():
        info = importar_escolhas(s["extrato"], s["sha256"], req.escolhas, _planilha(), cfg["pasta_comprovantes"])
        _sessoes.pop(req.token, None)
        info["backup"] = str(info["backup"]) if info.get("backup") else None
        return info

    return _gravando(fazer)


# ------------------------------------------------------- colagem Caixa Loja
def _contas_ativas(cont) -> list[str]:
    return [c.nome for c in cont.estrutura.contas if c.ativa]


class Abrir(BaseModel):
    qual: str = "oficial"


@app.post("/api/abrir")
def abrir_planilha(req: Abrir):
    """Abre a planilha no Excel deste computador (oficial ou a do fluxo projetado). Lembrete: aberta, ela impede gravar."""
    caminho = _planilha().caminho if req.qual == "oficial" else _arquivo_fluxo().caminho
    if not caminho.exists():
        raise HTTPException(404, f"Planilha não encontrada: {caminho}")
    os.startfile(str(caminho))
    return {"detalhe": f"Abrindo {caminho.name} no Excel. Feche antes de importar ou gravar no app."}


@app.get("/api/caixa/ultimo")
def caixa_ultimo():
    """A última linha do CONTROLE DE CAIXA que está na Hoth (sem os boletos do RET, "00025 - ..."): no CONTROLE,
    cola-se tudo o que vem abaixo dela. No mesmo dia vale a ordem da planilha, que é a ordem em que foi colado."""
    do_controle = [(i, l) for i, l in enumerate(_conteudo().lancamentos) if l["banco"] == colagem.BANCO and l.get("data")
                   and not re.match(r"^\d{3,6} - ", str(l["descricao"]))]
    if not do_controle:
        return {"ultima_data": None, "linhas": [], "ultima_colagem": None}
    _, ultima = max(do_controle, key=lambda il: (il[1]["data"], il[0]))
    quando = max((l["importado_em"] for _, l in do_controle
                  if str(l.get("origem") or "").startswith("Colagem") and l.get("importado_em")), default=None)
    return {"ultima_data": ultima["data"], "ultima_colagem": quando,
            "linhas": [{k: ultima[k] for k in ("data", "descricao", "valor", "conta")}]}


class Colado(BaseModel):
    texto: str
    desde: dt.date | None = None


@app.post("/api/caixa/interpretar")
def caixa_interpretar(req: Colado):
    if "\t" not in req.texto:
        raise HTTPException(400, "Isso não parece linhas copiadas do CONTROLE DE CAIXA. Selecione as células de DATA "
                                 "até SAÍDA no Excel, copie (Ctrl+C) e cole aqui.")
    cont = _conteudo()
    linhas = colagem.interpretar(req.texto, _contas_ativas(cont), {l["id"] for l in cont.lancamentos},
                                 [l for l in cont.lancamentos if l["banco"] == colagem.BANCO], req.desde)
    if not linhas:
        raise HTTPException(400, "Nada para ler. Copie as linhas do CONTROLE DE CAIXA (de DATA até SAÍDA) e cole aqui.")
    return {"linhas": linhas}


class LinhaCaixa(BaseModel):
    linha: int
    data: str | None
    descricao: str
    plano_original: str = ""
    conta: str = ""
    valor: float
    incluir: bool
    ja_existe: bool = False


class GravarCaixa(BaseModel):
    linhas: list[LinhaCaixa]


@app.post("/api/caixa/gravar")
def caixa_gravar(req: GravarCaixa):
    def fazer():
        cont = ler(_planilha().caminho)   # leitura fresca: a planilha pode ter mudado depois da colagem
        regs = colagem.registros([l.model_dump() for l in req.linhas], _contas_ativas(cont),
                                 {l["id"] for l in cont.lancamentos})
        if not regs:
            raise ValueError("Nenhuma linha marcada para gravar.")
        datas = [r["data"] for r in regs]
        pendentes = sum(1 for r in regs if not r["conta"])
        detalhe = (f"{len(regs)} lançamentos Caixa Loja colados do CONTROLE DE CAIXA, de {min(datas):%d/%m} a "
                   f"{max(datas):%d/%m/%Y}: {len(regs) - pendentes} com conta, {pendentes} pendentes")
        info = _planilha().gravar_lancamentos(regs, acao="Colagem Caixa Loja", detalhe=detalhe,
                                              arquivo="CONTROLE DE CAIXA (colado)")
        return {"gravados": info["gravados"], "duplicados_ignorados": info["duplicados_ignorados"],
                "detalhe": detalhe, "backup": str(info["backup"]) if info.get("backup") else None}

    return _gravando(fazer)


# ------------------------------------------------------------ contas a pagar
_cp_cache = {"chave": None, "valor": None}
_comp_cache = {"quando": 0.0, "lidos": {}, "lista": []}
_cp_sessoes: dict[str, dict] = {}


def _arquivo_titulos() -> ArquivoTitulos:
    return ArquivoTitulos.da_config(config.carregar())


def _comprovantes() -> list:
    """Comprovantes do Santander, relidos no máximo a cada 5 minutos (PDFs já lidos ficam em memória)."""
    if time.time() - _comp_cache["quando"] > 300:
        try:
            _comp_cache["lista"], _ = ler_pasta(config.carregar()["pasta_comprovantes"], _comp_cache["lidos"])
        except OSError:
            _comp_cache["lista"] = []   # pasta da rede indisponível: segue sem comprovantes
        _comp_cache["quando"] = time.time()
    return _comp_cache["lista"]


def _contas_pagar():
    """(carteira, resultado da conciliação, favorecidos, lançamentos), com cache."""
    cont = _conteudo()
    arq = _arquivo_titulos()
    comps = _comprovantes()
    k = (_cache["chave"], str(arq.caminho), arq.assinatura(), _comp_cache["quando"], dt.date.today())
    if _cp_cache["chave"] != k:
        carteira = arq.ler()
        lanc = cont.lancamentos
        favorecidos = titulos_identificados(lanc, comps)
        resultado = conciliar(carteira.titulos, lanc, favorecidos, carteira)
        _cp_cache["chave"], _cp_cache["valor"] = k, (carteira, resultado, favorecidos, lanc)
    return _cp_cache["valor"]


def _titulo_json(t, r, lanc_por_id):
    cands = [{"id": c, "data": lanc_por_id[c]["data"], "banco": lanc_por_id[c]["banco"],
              "descricao": lanc_por_id[c]["descricao"]} for c in r.get("candidatos", []) if c in lanc_por_id]
    return {k: t.get(k) for k in ("id", "codigo", "fornecedor", "documento", "parcela", "duplicata", "compra",
                                  "vencimento", "valor", "banco_ret", "conta", "no_ret", "marca", "observacao",
                                  "historico")} | {
        "situacao": r.get("situacao", ""), "situacao_texto": SITUACOES.get(r.get("situacao", ""), ""),
        "prova": r.get("prova", ""), "data_pagamento": r.get("data_pagamento"), "valor_pago": r.get("valor_pago"),
        "banco_pagamento": r.get("banco_pagamento", ""), "descricao_pagamento": r.get("descricao_pagamento", ""),
        "id_lancamento": r.get("id_lancamento", ""), "malote": r.get("malote", ""), "candidatos": cands}


@app.get("/api/cp/titulos")
def cp_titulos(situacao: str = "", busca: str = "", ate: dt.date | None = None):
    carteira, resultado, _, lanc = _contas_pagar()
    lanc_por_id = {l["id"]: l for l in lanc}
    termos = chave(busca).split()
    resumo = {}
    for t in carteira.titulos:
        s = resultado.get(t["id"], {}).get("situacao", "")
        r = resumo.setdefault(s, {"situacao": s, "texto": SITUACOES.get(s, s), "quantidade": 0, "valor": 0.0})
        r["quantidade"] += 1
        r["valor"] = round(r["valor"] + float(t["valor"] or 0), 2)
    sel = [t for t in carteira.titulos
           if (not situacao or resultado.get(t["id"], {}).get("situacao") in situacao.split(","))
           and (ate is None or (isinstance(t["vencimento"], dt.date) and t["vencimento"] <= ate))
           and all(x in chave(f"{t['fornecedor']} {t['documento']} {float(t['valor'] or 0):.2f}") for x in termos)]
    sel.sort(key=lambda t: (t["vencimento"] if isinstance(t["vencimento"], dt.date) else dt.date.max, t["fornecedor"]))
    arq = _arquivo_titulos()
    return {"arquivo": str(arq.caminho), "existe": arq.caminho.exists(), "resumo": list(resumo.values()),
            "total": len(sel), "soma": round(sum(float(t["valor"] or 0) for t in sel), 2),
            "itens": [_titulo_json(t, resultado.get(t["id"], {}), lanc_por_id) for t in sel[:1000]],
            "ultima_importacao": next((a for a in reversed(carteira.auditoria) if a["acao"] == "Importação RET"), None)}


@app.post("/api/cp/previa")
async def cp_previa(arquivo: UploadFile = File(...)):
    dados = await arquivo.read()
    if Path(arquivo.filename or "").suffix.lower() != ".xls":
        raise HTTPException(400, "Envie o relatório de contas a pagar em aberto do RET (.xls)")
    h = hashlib.sha256(dados).hexdigest()
    pasta = DADOS / "Contas a Pagar" / f"{dt.date.today():%Y-%m}"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{Path(arquivo.filename).stem} [{h[:8]}].xls"
    if not destino.exists():
        destino.write_bytes(dados)
    try:
        lido = ler_ret_abertos(destino)
    except ValueError as e:
        raise HTTPException(400, str(e))
    carteira, *_ = _contas_pagar()
    cmp = comparar_importacao(carteira, lido)
    token = secrets.token_urlsafe(12)
    _cp_sessoes[token] = {"arquivo": str(destino), "sha256": h}
    resumo = lambda lista: [{k: t.get(k) for k in ("fornecedor", "documento", "vencimento", "valor",
                                                   "valor_antes", "vencimento_antes")} for t in lista[:300]]
    return {"token": token, "arquivo": arquivo.filename, "lidos": cmp["lidos"], "total": cmp["total"],
            "de": cmp["de"], "ate": cmp["ate"], "novos": len(cmp["novos"]), "mudaram": resumo(cmp["mudaram"]),
            "sairam": resumo(cmp["sairam"]), "valor_novos": round(sum(t["valor"] for t in cmp["novos"]), 2)}


class Token(BaseModel):
    token: str


def _gravar_carteira(carteira, acao, detalhe):
    """Concilia de novo, copia a situação para os títulos (para o Power BI) e grava o arquivo."""
    cont = _conteudo()
    favorecidos = titulos_identificados(cont.lancamentos, _comprovantes())
    resultado = conciliar(carteira.titulos, cont.lancamentos, favorecidos, carteira)
    aplicar_resultado(carteira.titulos, resultado)
    backup = _arquivo_titulos().gravar(carteira, acao, detalhe)
    _cp_cache["chave"] = None
    _fluxo_status["aviso"] = _atualizar_planilha_fluxo(carteira, resultado)
    return backup


# ----------------------------------------------------------------- fluxo de caixa
_fluxo_status = {"aviso": ""}


def _arquivo_fluxo() -> PlanilhaEmUso:
    cfg = config.carregar()
    caminho = cfg.get("arquivo_fluxo") or str(Path(cfg["planilha"]).with_name(NOME_FLUXO))
    bkp = cfg.get("pasta_bkp_fluxo") or str(Path(cfg["pasta_bkp"]) / "Fluxo de Caixa")
    return PlanilhaEmUso(caminho, bkp, cfg.get("manter_backups", 60))


def _base() -> dict:
    """Cadastro de categorias da versão Base: no pacote vai junto do executável; no código, fica na pasta acima."""
    cfg = config.carregar()
    if cfg.get("cadastro_base"):
        return cadastro_base(cfg["cadastro_base"])
    no_pacote = RAIZ / "cadastro_base.sqlite3"
    return cadastro_base(no_pacote if no_pacote.exists() else RAIZ.parent / "Dados" / "classificacoes.sqlite3")


def _categorias_efetivas(carteira) -> tuple[dict, dict]:
    """({código: categoria} usado no fluxo, {código: origem}). Sem escolha sua, vale a da versão Base."""
    proprias = carteira.categoria_por_codigo()
    validas = {chave(n): n for n in carteira.nomes_categorias()}
    efetivas, origem = {}, {}
    for cod, cat in _base().items():
        if chave(cat) in validas:
            efetivas[cod], origem[cod] = validas[chave(cat)], "base"
    for cod, cat in proprias.items():
        efetivas[cod], origem[cod] = cat, "voce"
    return efetivas, origem


def _movimentos(carteira, resultado):
    efetivas, _ = _categorias_efetivas(carteira)
    envio = {m["id"]: m["envio"] for m in carteira.malotes}
    return movimentos(carteira.titulos, resultado, efetivas, envio)


def _periodo_planilha(movs) -> tuple[dt.date, dt.date]:
    hoje = dt.date.today()
    de = (hoje.replace(day=1) - dt.timedelta(days=1)).replace(day=1)          # início do mês anterior
    fim_mes_seguinte = (hoje.replace(day=28) + dt.timedelta(days=40)).replace(day=1) - dt.timedelta(days=1)
    futuros = [m["data"] for m in movs if m["data"] >= hoje]
    ate = min(max(futuros + [fim_mes_seguinte]), hoje + dt.timedelta(days=400))
    return de, ate


def _atualizar_planilha_fluxo(carteira, resultado) -> str:
    """Refaz a planilha do fluxo. Não impede a gravação do contas a pagar: se falhar, devolve o aviso."""
    try:
        movs = _movimentos(carteira, resultado)
        de, ate = _periodo_planilha(movs)
        calc = calcular(movs, carteira.entradas, de, ate, carteira.nomes_categorias())
        sem_cat = sum(1 for m in movs if m["categoria"] == SEM_CATEGORIA)
        conferencia = [
            ("Títulos no fluxo", len(movs), True),
            ("Títulos sem categoria (classifique no app)", sem_cat, sem_cat == 0),
            ("Saídas no período", calc["totais"]["saidas"], True),
            ("Entradas no período", calc["totais"]["entradas"], True),
        ]
        arq = _arquivo_fluxo()
        tmp = arq.caminho.with_name(f"~hoth_gravando_{arq.caminho.name}")
        gerar_planilha(tmp, calculo=calc, movs=movs, entradas=carteira.entradas, empresa=_conteudo().estrutura.empresa,
                       gerado_em=dt.datetime.now(), conferencia=conferencia)
        try:
            if arq.caminho.exists():
                arq.verificar_livre()
                arq.backup("atualizacao")
            _substituir(tmp, arq.caminho)
        finally:
            tmp.unlink(missing_ok=True)
        arq._limpar_backups()
        return ""
    except PlanilhaOcupada:
        return "A planilha do fluxo está aberta no Excel e não foi atualizada. Feche-a e clique em Atualizar planilha."
    except OSError as e:
        return f"Não consegui atualizar a planilha do fluxo: {e}"


@app.post("/api/cp/importar")
def cp_importar(req: Token):
    s = _cp_sessoes.get(req.token)
    if not s:
        raise HTTPException(404, "Prévia expirada. Envie o relatório de novo.")

    def fazer():
        if hashlib.sha256(Path(s["arquivo"]).read_bytes()).hexdigest() != s["sha256"]:
            raise ValueError("O relatório mudou depois da prévia. Envie de novo.")
        cont = _conteudo()
        carteira = _arquivo_titulos().ler()
        clf = Classificador(cont.lancamentos, None, carregar_regras_fixas(_planilha().caminho))
        classificar = lambda t: clf.classificar({"banco": "Caixa Loja", "descricao": t["fornecedor"],
                                                 "valor": -t["valor"]}).conta
        cmp = aplicar_importacao(carteira, ler_ret_abertos(s["arquivo"]), classificar)
        detalhe = (f"{cmp['lidos']} títulos em aberto (vencimentos {cmp['de']:%d/%m/%Y} a {cmp['ate']:%d/%m/%Y}): "
                   f"{len(cmp['novos'])} novos, {len(cmp['mudaram'])} alterados, {len(cmp['sairam'])} saíram do RET")
        backup = _gravar_carteira(carteira, "Importação RET", detalhe)
        _cp_sessoes.pop(req.token, None)
        return {"detalhe": detalhe, "backup": str(backup) if backup else None}

    return _gravando(fazer)


class Marcar(BaseModel):
    ids: list[str]
    marca: str
    observacao: str = ""
    lancamento: str = ""


@app.post("/api/cp/marcar")
def cp_marcar(req: Marcar):
    if req.marca not in MARCAS:
        raise HTTPException(400, f"Marcação inválida: {req.marca}")

    def fazer():
        _, resultado, *_ = _contas_pagar()       # pagamento proposto hoje (para "confirmar")
        carteira = _arquivo_titulos().ler()      # leitura fresca para gravar
        por_id = carteira.por_id()
        alvo = [por_id[i] for i in req.ids if i in por_id]
        for t in alvo:
            t["marca"] = req.marca
            if req.marca == "confirmado":
                t["lancamento_confirmado"] = req.lancamento or resultado.get(t["id"], {}).get("id_lancamento", "")
                if not t["lancamento_confirmado"]:
                    raise ValueError(f"{t['fornecedor']}: não há pagamento para confirmar.")
            else:
                t["lancamento_confirmado"] = ""
            if req.observacao:
                t["observacao"] = req.observacao
        texto = MARCAS[req.marca] or "Marcação removida"
        _gravar_carteira(carteira, "Marcação", f"{len(alvo)} títulos: {texto}")
        return {"alterados": len(alvo)}

    return _gravando(fazer)


class ValorMalote(BaseModel):
    valor: float
    envio: dt.date
    escolhidos: list[str] = []


@app.post("/api/cp/malote/candidatos")
def cp_malote_candidatos(req: ValorMalote):
    carteira, resultado, *_ = _contas_pagar()
    return candidatos_malote(req.valor, req.envio, carteira.titulos, resultado, set(req.escolhidos),
                             titulos_em_malote(carteira))


class LinhaMalote(BaseModel):
    valor: float
    titulo: str = ""
    observacao: str = ""


class NovoMalote(BaseModel):
    envio: dt.date
    total_fita: float | None = None
    observacao: str = ""
    valores: list[LinhaMalote]


@app.post("/api/cp/malote")
def cp_malote_salvar(req: NovoMalote):
    if not req.valores:
        raise HTTPException(400, "Digite pelo menos um valor da fita.")

    def fazer():
        carteira = _arquivo_titulos().ler()
        if not carteira.titulos:
            raise ValueError("Importe o relatório de contas em aberto do RET antes de registrar malotes.")
        em_outro = titulos_em_malote(carteira)
        repetidos = [v.titulo for v in req.valores if v.titulo and v.titulo in em_outro]
        if repetidos:
            raise ValueError(f"{len(repetidos)} título(s) já estão em outro malote ({em_outro[repetidos[0]]}).")
        ids = [v.titulo for v in req.valores if v.titulo]
        if len(ids) != len(set(ids)):
            raise ValueError("O mesmo título foi escolhido para dois valores.")
        mid = novo_id_malote(carteira, req.envio)
        carteira.malotes.append({"id": mid, "envio": req.envio, "total_fita": req.total_fita,
                                 "observacao": req.observacao, "criado_em": dt.datetime.now().replace(microsecond=0)})
        for i, v in enumerate(req.valores, start=1):
            carteira.malote_valores.append({"malote": mid, "ordem": i, "valor": round(v.valor, 2), "titulo": v.titulo,
                                            "observacao": v.observacao})
        soma = round(sum(v.valor for v in req.valores), 2)
        detalhe = (f"Malote {mid} de {req.envio:%d/%m/%Y}: {len(req.valores)} valores, R$ {soma:.2f}, "
                   f"{len(ids)} com título")
        _gravar_carteira(carteira, "Malote", detalhe)
        return {"id": mid, "detalhe": detalhe}

    return _gravando(fazer)


@app.get("/api/cp/malotes")
def cp_malotes():
    carteira, resultado, *_ = _contas_pagar()
    nomes = carteira.por_id()
    saida = []
    for m in sorted(carteira.malotes, key=lambda m: m["envio"], reverse=True):
        valores = []
        for v in sorted((v for v in carteira.malote_valores if v["malote"] == m["id"]), key=lambda v: v["ordem"]):
            t = nomes.get(v.get("titulo"))
            r = resultado.get(v.get("titulo"), {})
            valores.append({"valor": v["valor"], "titulo": v.get("titulo") or "", "observacao": v.get("observacao", ""),
                            "fornecedor": t["fornecedor"] if t else "", "vencimento": t["vencimento"] if t else None,
                            "situacao": r.get("situacao", ""), "situacao_texto": SITUACOES.get(r.get("situacao", ""), ""),
                            "voltou": r.get("situacao") in PAGOS, "data_pagamento": r.get("data_pagamento")})
        pend = [v for v in valores if not v["voltou"]]
        saida.append({**m, "valores": valores, "quantidade": len(valores),
                      "soma": round(sum(v["valor"] for v in valores), 2), "pendentes": len(pend),
                      "valor_pendente": round(sum(v["valor"] for v in pend), 2),
                      "dias": (dt.date.today() - m["envio"]).days if isinstance(m["envio"], dt.date) else None})
    return saida


@app.get("/api/cp/categorias")
def cp_categorias():
    """Fornecedores dos títulos (em aberto primeiro) com a categoria de cada um."""
    carteira, resultado, *_ = _contas_pagar()
    efetivas, origem = _categorias_efetivas(carteira)
    # Sugestão pela conta do plano que o classificador deu ao boleto: grupo 03 (CPV) = mercadoria.
    grupo_da_conta = {chave(c.nome): c.grupo for c in _conteudo().estrutura.contas}
    nomes = {chave(n): n for n in carteira.nomes_categorias()}
    sugerir = lambda conta: (nomes.get("MERCADORIA") if grupo_da_conta.get(chave(conta)) == "03"
                             else nomes.get("DESPESA")) if conta else ""
    forn = {}
    for t in carteira.titulos:
        cod = str(t.get("codigo") or "")
        if not cod:
            continue
        f = forn.setdefault(cod, {"codigo": cod, "fornecedor": t["fornecedor"], "categoria": efetivas.get(cod, ""),
                                  "origem": origem.get(cod, ""), "titulos": 0, "em_aberto": 0.0, "sugestao": "",
                                  "conta": ""})
        if not f["sugestao"] and t.get("conta"):
            f["sugestao"], f["conta"] = sugerir(t["conta"]) or "", t["conta"]
        f["titulos"] += 1
        if resultado.get(t["id"], {}).get("situacao") in ("vencido", "a_vencer", "aguardando_fatura", "no_malote"):
            f["em_aberto"] = round(f["em_aberto"] + float(t["valor"] or 0), 2)
    lista = sorted(forn.values(), key=lambda f: (f["origem"] == "voce", -f["em_aberto"], f["fornecedor"]))
    return {"categorias": carteira.nomes_categorias(), "fornecedores": lista,
            "pendentes": sum(1 for f in lista if not f["categoria"]),
            "da_versao_base": sum(1 for f in lista if f["origem"] == "base")}


class ItemCategoria(BaseModel):
    codigo: str
    fornecedor: str = ""
    categoria: str


class Categorias(BaseModel):
    itens: list[ItemCategoria] = []
    nova: str = ""


@app.post("/api/cp/categorias")
def cp_categorias_salvar(req: Categorias):
    def fazer():
        carteira = _arquivo_titulos().ler()
        partes = []
        if req.nova.strip():
            partes.append(f"categoria nova {criar_categoria(carteira, req.nova)}")
        if req.itens:
            definir_categorias(carteira, [i.model_dump() for i in req.itens])
            partes.append(f"{len(req.itens)} fornecedor(es) classificados")
        if not partes:
            raise ValueError("Nada para gravar.")
        _gravar_carteira(carteira, "Categorias", "; ".join(partes))
        detalhe = "; ".join(partes)
        return {"detalhe": detalhe[:1].upper() + detalhe[1:], "aviso_fluxo": _fluxo_status["aviso"]}

    return _gravando(fazer)


@app.get("/api/fluxo")
def fluxo(de: dt.date | None = None, ate: dt.date | None = None):
    carteira, resultado, _, lanc = _contas_pagar()
    hoje = dt.date.today()
    de = de or hoje
    ate = ate or hoje + dt.timedelta(days=30)
    if ate < de:
        raise HTTPException(400, "A data final é anterior à inicial.")
    if (ate - de).days > 800:
        raise HTTPException(400, "Escolha um período de até 2 anos.")
    movs = _movimentos(carteira, resultado)
    calc = calcular(movs, carteira.entradas, de, ate, carteira.nomes_categorias())
    no_periodo = [m for m in movs if de <= m["data"] <= ate]
    arq = _arquivo_fluxo()
    return {**calc, "meses": por_mes(calc["dias"], calc["categorias"]),
            "titulos": sorted(no_periodo, key=lambda m: (m["data"], -m["valor"]))[:500],
            "sem_categoria": sum(1 for m in no_periodo if m["categoria"] == SEM_CATEGORIA),
            "entradas_lancadas": sorted([e for e in carteira.entradas if isinstance(e.get("data"), dt.date)],
                                        key=lambda e: e["data"]),
            "sugestao": sugestao_entradas(lanc), "planilha": str(arq.caminho), "planilha_existe": arq.caminho.exists(),
            "aviso_planilha": _fluxo_status["aviso"]}


class Entrada(BaseModel):
    data: dt.date
    descricao: str
    valor: float
    forma: str = ""
    repetir_ate: dt.date | None = None   # repete no mesmo dia da semana até essa data


class Entradas(BaseModel):
    incluir: list[Entrada] = []
    remover: list[str] = []


@app.post("/api/fluxo/entradas")
def fluxo_entradas(req: Entradas):
    def fazer():
        carteira = _arquivo_titulos().ler()
        antes = len(carteira.entradas)
        carteira.entradas = [e for e in carteira.entradas if e["id"] not in set(req.remover)]
        removidas = antes - len(carteira.entradas)
        novas = 0
        for e in req.incluir:
            if e.valor <= 0 or not e.descricao.strip():
                raise ValueError("Cada entrada precisa de descrição e valor maior que zero.")
            d = e.data
            while True:
                carteira.entradas.append({"id": secrets.token_hex(6).upper(), "data": d, "descricao": e.descricao.strip(),
                                          "valor": round(e.valor, 2), "forma": e.forma.strip()})
                novas += 1
                d += dt.timedelta(days=7)
                if not e.repetir_ate or d > e.repetir_ate or novas > 200:
                    break
        detalhe = f"{novas} entrada(s) incluída(s), {removidas} removida(s)"
        _gravar_carteira(carteira, "Entradas", detalhe)
        return {"detalhe": detalhe, "aviso_fluxo": _fluxo_status["aviso"]}

    return _gravando(fazer)


@app.post("/api/fluxo/planilha")
def fluxo_planilha():
    def fazer():
        carteira, resultado, *_ = _contas_pagar()
        aviso = _atualizar_planilha_fluxo(carteira, resultado)
        _fluxo_status["aviso"] = aviso
        if aviso:
            raise ValueError(aviso)
        return {"detalhe": f"Planilha atualizada: {_arquivo_fluxo().caminho}"}

    return _gravando(fazer)


# ------------------------------------------------- aprendizado das classificações
@app.get("/api/aprendizado")
def aprendizado(busca: str = "", banco: str = "", sentido: str = ""):
    """O que o classificador aprendeu: cada descrição já classificada (por banco e sentido), a conta mais usada e a
    consistência; e as regras fixas (por fornecedor e por descrição) que valem antes do aprendizado."""
    cont = _conteudo()
    regras_arq = arquivo_regras_fixas(_planilha().caminho)
    bruto = json.loads(regras_arq.read_text(encoding="utf-8")) if regras_arq.exists() else {}
    regras = [{"tipo": "descricao" if k.startswith("desc:") else "fornecedor", "chave": k,
               "nome": r.get("descricao") or r.get("fornecedor") or "", "conta": r.get("conta", "")}
              for k, r in sorted(bruto.items())]
    grupos: dict = {}
    for l in cont.lancamentos:
        if not l.get("conta") or not l.get("descricao"):
            continue
        k = (l["banco"], chave(l["descricao"]), (l["valor"] or 0) > 0)
        g = grupos.setdefault(k, {"descricao": l["descricao"], "contas": Counter()})
        g["contas"][l["conta"]] += 1
    termos = chave(busca).split()
    saida = []
    for (b, desc, entrada), g in grupos.items():
        if (banco and b != banco) or (sentido and sentido != ("entrada" if entrada else "saída")) \
                or not all(t in desc for t in termos):
            continue
        conta, n = g["contas"].most_common(1)[0]
        total = sum(g["contas"].values())
        k_desc = chave_regra_descricao(g["descricao"])
        k_cod = codigo_fornecedor(g["descricao"])
        regra = k_desc if k_desc in bruto else (k_cod if k_cod in bruto else None)
        saida.append({"banco": b, "descricao": g["descricao"], "sentido": "entrada" if entrada else "saída",
                      "vezes": total, "conta": conta, "consistencia": round(n / total, 2),
                      "outras": [{"conta": c, "vezes": q} for c, q in g["contas"].most_common()[1:4]], "regra": regra})
    saida.sort(key=lambda x: (x["consistencia"] >= 0.95, -x["vezes"]))   # divididas primeiro (são as que pedem decisão)
    return {"regras": regras, "aprendidos": saida[:300], "total": len(saida), "arquivo_regras": str(regras_arq)}


class RegraReq(BaseModel):
    tipo: str            # fornecedor | descricao
    chave: str           # código do fornecedor ("00487") ou a descrição
    nome: str = ""
    conta: str | None    # None = tirar a regra; "" = sempre revisar


@app.post("/api/aprendizado/regra")
def aprendizado_regra(req: RegraReq):
    def fazer():
        if req.tipo == "descricao":
            k = req.chave if req.chave.startswith("desc:") else chave_regra_descricao(req.chave)
        elif req.tipo == "fornecedor" and re.fullmatch(r"\d{3,6}", req.chave.strip()):
            k = req.chave.strip()
        else:
            raise ValueError("Regra inválida: use o código do fornecedor (ex.: 00487) ou uma descrição.")
        conta = req.conta
        if conta:
            validas = {chave(c): c for c in _planilha().contas()}
            if chave(conta) not in validas:
                raise ValueError(f"Conta não existe no Plano de Contas: {conta}")
            conta = validas[chave(conta)]
        salvar_regra_fixa(_planilha().caminho, k, req.nome or req.chave, conta)
        texto = "removida" if conta is None else ("sempre revisar" if conta == "" else f"sempre {conta}")
        return {"detalhe": f"Regra {texto}: {req.nome or req.chave}"}

    return _gravando(fazer)


# ----------------------------------------------------------- fatura do cartão
_fat_cache: dict = {}       # caminho -> (mtime, resumo lido)
_fat_sessoes: dict[str, dict] = {}


def _pastas_fatura() -> list[Path]:
    cfg = config.carregar()
    return [Path(p) for p in [cfg.get("pasta_faturas"), DADOS / "Faturas"] if p]


def _ler_fatura(caminho: Path) -> dict:
    mt = caminho.stat().st_mtime
    if caminho not in _fat_cache or _fat_cache[caminho][0] != mt:
        _fat_cache[caminho] = (mt, ler_fatura(caminho, config.carregar().get("senha_fatura", "")))
    return _fat_cache[caminho][1]


def _fatura_permitida(arquivo: str) -> Path:
    alvo = Path(arquivo).resolve()
    if not any(p.resolve() in alvo.parents for p in _pastas_fatura() if p.exists()) or not alvo.is_file():
        raise HTTPException(404, "Fatura não encontrada na pasta de faturas")
    return alvo


@app.get("/api/fatura/lista")
def fatura_lista():
    carteira, *_ = _contas_pagar()
    lanc = _conteudo().lancamentos
    abertas = {(f["vencimento"], round(float(f["total"] or 0), 2)): f for f in carteira.faturas if f.get("situacao") == "aberta"}
    ano = _conteudo().estrutura.ano
    saida, ignoradas, vistos = [], 0, set()
    for pasta in _pastas_fatura():
        for p in listar_pdfs(pasta):
            try:
                f = _ler_fatura(p)
            except (SenhaFatura, ValueError):
                ignoradas += 1        # layout antigo (2024–2025) ou PDF que não é fatura
                continue
            k = (f["vencimento"], round(f["total"], 2))
            if f["vencimento"].year != ano or k in vistos:   # só o ano da planilha; cópias repetidas uma vez só
                continue
            vistos.add(k)
            aberta = abertas.get(k)
            deb = achar_debito(f, lanc, carteira.debitos_abertos()) if not aberta else []
            mao = aberta_a_mao(f, lanc) if not aberta and not deb else None
            situacao = ("aberta" if aberta else "pronta" if len(deb) == 1 else "aberta_mao" if mao
                        else "sem_debito" if not deb else "varios_debitos")
            saida.append({"arquivo": str(p), "nome": p.name, "pasta": p.parent.name, "vencimento": f["vencimento"],
                          "total": f["total"], "itens": len(f["itens"]), "confere": abs(f["total"] - f["soma_itens"]) < 0.005,
                          "situacao": situacao, "aberta_em": aberta.get("aberta_em") if aberta else None,
                          "aberta_mao": mao["data"] if mao else None,
                          "debito": {"data": deb[0]["data"], "valor": deb[0]["valor"]} if len(deb) == 1 else None})
    # Débitos de fatura no extrato que ainda não foram abertos (falta o PDF?)
    ja = {(x["vencimento"], round(x["total"], 2)) for x in saida}
    sem_pdf = [{"data": l["data"], "valor": l["valor"], "descricao": l["descricao"]} for l in lanc
               if l["banco"] == "Santander" and l.get("data") and DEBITO.search(str(l["descricao"]))
               and l["id"] not in carteira.debitos_abertos()
               and not any(k[1] == round(-l["valor"], 2) for k in ja)]
    ordem = {"pronta": 0, "sem_debito": 1, "varios_debitos": 2, "aberta": 3, "aberta_mao": 4}
    saida.sort(key=lambda x: (ordem[x["situacao"]], -x["vencimento"].toordinal()))
    return {"faturas": saida, "debitos_sem_pdf": sorted(sem_pdf, key=lambda x: x["data"]), "ignoradas": ignoradas,
            "pasta": str(_pastas_fatura()[0]) if _pastas_fatura() else "",
            "abertas": sorted(carteira.faturas, key=lambda f: f["vencimento"], reverse=True)}


class PreviaFatura(BaseModel):
    arquivo: str
    agrupar: bool = False


def _previa_fatura(caminho: Path, agrupar: bool):
    carteira, *_ = _contas_pagar()
    cont = _conteudo()
    f = _ler_fatura(caminho)
    if abs(f["total"] - f["soma_itens"]) >= 0.005:
        raise HTTPException(400, f"A soma das compras ({f['soma_itens']:.2f}) não bate com o total da fatura "
                                 f"({f['total']:.2f}). Não é seguro abrir esta fatura automaticamente.")
    if any(x.get("situacao") == "aberta" and x["vencimento"] == f["vencimento"]
           and abs(float(x["total"] or 0) - f["total"]) < 0.005 for x in carteira.faturas):
        raise HTTPException(400, f"A fatura de vencimento {f['vencimento']:%d/%m/%Y} já foi aberta.")
    debitos = achar_debito(f, cont.lancamentos, carteira.debitos_abertos())
    itens = agrupar_itens(f["itens"]) if agrupar else [dict(x) for x in f["itens"]]
    clf = Classificador(cont.lancamentos, None, carregar_regras_fixas(_planilha().caminho))
    classificar_itens(itens, cont.lancamentos, clf)
    lancs = itens_como_lancamentos(itens, debitos[0]) if len(debitos) == 1 else []
    for x, l in zip(itens, lancs):
        x["id"] = l["id"]
    token = secrets.token_urlsafe(12)
    _fat_sessoes[token] = {"arquivo": str(caminho), "agrupar": agrupar, "itens": itens, "lancs": lancs,
                           "debito": debitos[0] if len(debitos) == 1 else None, "fatura": f}
    return {"token": token, "arquivo": caminho.name, "vencimento": f["vencimento"], "fechamento": f["fechamento"],
            "total": f["total"], "cartao": f["cartao"], "agrupada": agrupar,
            "debito": {"data": debitos[0]["data"], "valor": debitos[0]["valor"], "descricao": debitos[0]["descricao"],
                       "conta": debitos[0].get("conta", "")} if len(debitos) == 1 else None,
            "aviso": "" if len(debitos) == 1 else (
                "O débito desta fatura ainda não está no extrato do Santander importado. Importe o extrato e tente de novo."
                if not debitos else f"Há {len(debitos)} débitos com esse valor; abra pela planilha."),
            "itens": [{"id": x.get("id", str(i)), "data_compra": x["data_compra"], "descricao": x["descricao"],
                       "valor": x["valor"], "texto_fatura": x["texto_fatura"], "proposta": x.get("proposta", ""),
                       "regra": x.get("regra", ""), "confianca": x.get("confianca", ""),
                       "sugestoes": x.get("sugestoes", [])} for i, x in enumerate(itens)]}


@app.post("/api/fatura/previa")
def fatura_previa(req: PreviaFatura):
    try:
        return _previa_fatura(_fatura_permitida(req.arquivo), req.agrupar)
    except SenhaFatura as e:
        raise HTTPException(400, str(e))


@app.post("/api/fatura/enviar")
async def fatura_enviar(arquivo: UploadFile = File(...)):
    dados = await arquivo.read()
    if Path(arquivo.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(400, "Envie o PDF da fatura do cartão.")
    pasta = DADOS / "Faturas"
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{Path(arquivo.filename).stem} [{hashlib.sha256(dados).hexdigest()[:8]}].pdf"
    if not destino.exists():
        destino.write_bytes(dados)
    try:
        return _previa_fatura(destino, False)
    except (SenhaFatura, ValueError) as e:
        raise HTTPException(400, str(e))


class GravarFatura(BaseModel):
    token: str
    escolhas: dict[str, str]


@app.post("/api/fatura/gravar")
def fatura_gravar(req: GravarFatura):
    s = _fat_sessoes.get(req.token)
    if not s:
        raise HTTPException(404, "Prévia expirada. Abra a fatura de novo.")
    if not s["debito"]:
        raise HTTPException(400, "Sem o débito da fatura no extrato não dá para abrir.")

    def fazer():
        validas = {chave(c): c for c in _planilha().contas()}
        invalidas = sorted({c for c in req.escolhas.values() if c and chave(c) not in validas})
        if invalidas:
            raise ValueError("Contas que não existem no Plano de Contas: " + "; ".join(invalidas))
        titulos = _arquivo_titulos()
        if titulos.caminho.exists():   # o registro da fatura vai para lá: confere antes de mexer na planilha
            titulos._uso.verificar_livre()
        nome = Path(s["arquivo"]).name
        registros, pendentes = [], 0
        for x, l in zip(s["itens"], s["lancs"]):
            conta = validas.get(chave(req.escolhas.get(l["id"], "")), "")
            pendentes += not conta
            modo = ("pendente de revisão" if not conta else
                    f"automática ({x['regra']}, {x['confianca']})" if conta == x.get("proposta") else "revisão manual")
            registros.append({**l, "conta": conta, "origem": f"Fatura do cartão: {modo}", "referencia": nome,
                              "observacao": f"Compra em {x['data_compra']:%d/%m/%Y} · fatura venc. "
                                            f"{s['fatura']['vencimento']:%d/%m/%Y} · {x['texto_fatura']}"})
        d = s["debito"]
        detalhe = (f"Fatura do cartão venc. {s['fatura']['vencimento']:%d/%m/%Y} ({s['fatura']['total']:.2f}): débito de "
                   f"{d['data']:%d/%m/%Y} trocado por {len(registros)} compras ({pendentes} sem conta)")
        info = _planilha().substituir_lancamentos([d["id"]], registros, acao="Fatura do cartão", detalhe=detalhe,
                                                  arquivo=s["arquivo"])
        carteira = _arquivo_titulos().ler()
        carteira.faturas.append({
            "id": f"F{s['fatura']['vencimento']:%Y%m%d}-{len(carteira.faturas) + 1}", "vencimento": s["fatura"]["vencimento"],
            "total": s["fatura"]["total"], "cartao": s["fatura"]["cartao"], "arquivo": s["arquivo"],
            "sha256": fatura_sha256(s["arquivo"]), "id_debito": d["id"], "data_debito": d["data"],
            "descricao_debito": d["descricao"], "conta_debito": d.get("conta", ""), "origem_debito": d.get("origem", ""),
            "itens": len(registros), "ids_itens": ";".join(r["id"] for r in registros), "agrupada": "Sim" if s["agrupar"] else "Não",
            "situacao": "aberta", "aberta_em": dt.datetime.now().replace(microsecond=0), "backup": str(info["backup"])})
        _gravar_carteira(carteira, "Fatura do cartão", detalhe)
        _fat_sessoes.pop(req.token, None)
        return {"detalhe": detalhe, "backup": str(info["backup"]), "aviso_fluxo": _fluxo_status["aviso"]}

    return _gravando(fazer)


class Desfazer(BaseModel):
    id: str


@app.post("/api/fatura/desfazer")
def fatura_desfazer(req: Desfazer):
    def fazer():
        carteira = _arquivo_titulos().ler()
        f = next((x for x in carteira.faturas if x["id"] == req.id and x.get("situacao") == "aberta"), None)
        if not f:
            raise ValueError("Fatura não encontrada ou já desfeita.")
        debito = {"id": str(f["id_debito"]), "banco": "Santander", "data": f["data_debito"],
                  "descricao": f["descricao_debito"], "documento": "", "valor": -round(float(f["total"]), 2),
                  "conta": f.get("conta_debito") or "", "origem": f.get("origem_debito") or "Fatura desfeita",
                  "referencia": "", "observacao": f"Fatura venc. {f['vencimento']:%d/%m/%Y} desfeita no app"}
        ids = [i for i in str(f["ids_itens"]).split(";") if i]
        detalhe = f"Fatura venc. {f['vencimento']:%d/%m/%Y} desfeita: {len(ids)} compras voltaram a ser o débito"
        info = _planilha().substituir_lancamentos(ids, [debito], acao="Desfazer fatura", detalhe=detalhe)
        f["situacao"] = "desfeita"
        _gravar_carteira(carteira, "Desfazer fatura", detalhe)
        return {"detalhe": detalhe, "backup": str(info["backup"])}

    return _gravando(fazer)


# --------------------------------------------------------------- lançamentos
@app.get("/api/lancamentos")
def lancamentos(busca: str = "", banco: str = "", mes: int = 0, conta: str = "", pendentes: bool = False,
                pagina: int = 1, por_pagina: int = 100):
    lanc = _conteudo().lancamentos
    termos = chave(busca).split()
    sel = [l for l in lanc
           if (not banco or l["banco"] == banco) and (not mes or (l["data"] and l["data"].month == mes))
           and (not conta or l["conta"] == conta) and (not pendentes or not l["conta"])
           and all(t in chave(f"{l['descricao']} {l['observacao']} {l['conta']} {l['valor']:.2f}") for t in termos)]
    sel.sort(key=lambda l: (l["data"] or dt.date.min), reverse=True)
    ini = (max(pagina, 1) - 1) * por_pagina
    return {"total": len(sel), "soma": round(sum(l["valor"] for l in sel), 2),
            "itens": [{k: l[k] for k in ("id", "banco", "data", "descricao", "valor", "conta", "grupo", "origem",
                                          "observacao")} for l in sel[ini:ini + por_pagina]]}


class Reclassificar(BaseModel):
    ids: list[str]
    conta: str


@app.post("/api/lancamentos/reclassificar")
def reclassificar(req: Reclassificar):
    cont = _conteudo()
    validas = {chave(c.nome): c.nome for c in cont.estrutura.contas}
    if req.conta and chave(req.conta) not in validas:
        raise HTTPException(400, f"Conta não existe: {req.conta}")
    conta = validas.get(chave(req.conta), "")
    origem = f"Reclassificado no app em {dt.date.today():%d/%m/%Y}"

    def fazer():
        info = _planilha().reclassificar(req.ids, conta, origem)
        return {"alterados": info["alterados"], "backup": str(info["backup"])}

    return _gravando(fazer)


@app.get("/api/contas")
def contas():
    return [c.nome for c in sorted(_conteudo().estrutura.contas, key=lambda c: c.codigo) if c.ativa]


# ------------------------------------------------------------ plano de contas
def _plano_json(ed, cont):
    uso = _uso(cont)
    grupos = {g.codigo: g.nome for g in ed.est.grupos}
    return {
        "grupos": [{"codigo": g.codigo, "nome": g.nome, "natureza": g.natureza, "entra_dre": g.entra_dre,
                    "entra_dfc": g.entra_dfc, "resultado_apos": g.resultado_apos,
                    "base_percentual": g.base_percentual} for g in ed.est.grupos],
        "contas": [{"codigo": c.codigo, "nome": c.nome, "grupo": c.grupo, "grupo_nome": grupos.get(c.grupo, ""),
                    "grupo_dre": c.grupo_dre, "entra_dfc": c.entra_dfc, "entra_dre": c.entra_dre,
                    "dre_manual": c.dre_manual, "fixo_variavel": c.fixo_variavel, "ativa": c.ativa,
                    "observacao": c.observacao,
                    "uso": uso.get(c.nome, 0) + sum(uso.get(a, 0) for a, n in ed.renomeacoes.items() if n == c.nome)}
                   for c in sorted(ed.est.contas, key=lambda c: (list(grupos).index(c.grupo)
                                                                 if c.grupo in grupos else 99, c.ordem, c.codigo))],
        "rascunho": ed.operacoes, "renomeacoes": ed.renomeacoes,
    }


@app.get("/api/plano")
def plano():
    cont = _conteudo()
    try:
        ed = editor_com_rascunho(cont.estrutura, _uso(cont), _rascunho().operacoes())
    except ErroPlano as e:
        _rascunho().limpar()
        raise HTTPException(409, f"O rascunho não vale mais para a planilha atual e foi descartado: {e}")
    return _plano_json(ed, cont)


@app.post("/api/plano/operacao")
def plano_operacao(op: dict):
    cont = _conteudo()
    ops = _rascunho().operacoes()
    try:
        ed = editor_com_rascunho(cont.estrutura, _uso(cont), ops)
        ed.aplicar(op)
    except ErroPlano as e:
        raise HTTPException(400, str(e))
    _rascunho().salvar(ops + [op])
    return _plano_json(ed, cont)


@app.delete("/api/plano/rascunho")
def plano_descartar():
    _rascunho().limpar()
    return plano()


@app.post("/api/plano/aplicar")
def plano_aplicar():
    ops = _rascunho().operacoes()
    if not ops:
        raise HTTPException(400, "Não há alterações para aplicar")

    def fazer():
        cont = ler(_planilha().caminho)
        ed = editor_com_rascunho(cont.estrutura, _uso(cont), ops)
        cont.estrutura = ed.est
        aplicar_renomeacoes(cont, ed.renomeacoes)
        detalhe = f"{len(ops)} alterações no plano de contas/grupos"
        if ed.renomeacoes:
            detalhe += "; renomeadas/mescladas: " + "; ".join(f"{a} -> {n}" for a, n in ed.renomeacoes.items())
        bkp = _planilha().reconstruir(cont, "Alteração do plano", detalhe)
        _rascunho().limpar()
        return {"backup": str(bkp), "detalhe": detalhe}

    return _gravando(fazer)


# ----------------------------------------------------------------- versões
@app.get("/api/versoes")
def versoes():
    pl = _planilha()
    return {"backups": [{"arquivo": b.name, "tamanho": b.stat().st_size,
                         "data": dt.datetime.fromtimestamp(b.stat().st_mtime).replace(microsecond=0)}
                        for b in pl.listar_backups()],
            "auditoria": list(reversed(_conteudo().auditoria))}


class Restaurar(BaseModel):
    arquivo: str


@app.post("/api/versoes/restaurar")
def restaurar(req: Restaurar):
    pl = _planilha()
    alvo = pl.pasta_bkp / Path(req.arquivo).name  # só arquivos da pasta BKP
    return _gravando(lambda: {"backup": str(pl.restaurar(alvo))})


# --------------------------------------------------------------- frontend
if ESTATICO.exists():
    app.mount("/assets", StaticFiles(directory=ESTATICO / "assets"), name="assets")

    @app.get("/{caminho:path}")
    def spa(caminho: str):
        arquivo = ESTATICO / caminho
        if caminho and arquivo.is_file():
            return FileResponse(arquivo)
        return FileResponse(ESTATICO / "index.html")
