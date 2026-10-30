"""Conciliação dos títulos do contas a pagar com os pagamentos já gravados na planilha oficial.

O pagamento é procurado em **todos** os bancos: a forma e o banco escritos no RET mudam na hora da baixa.
Ordem (para no primeiro que decide; cada lançamento paga no máximo um título):

0. Marcação do usuário: cancelado, aguardando fatura, pago fora, pagamento confirmado (com o lançamento escolhido).
1. Lotérica: lançamento da Caixa Loja com o mesmo código de fornecedor e o mesmo documento -> conferido
   (valor diferente = pago com diferença).
2. Lotérica sem documento: mesmo código de fornecedor e valor, perto do vencimento -> conferido.
3. Comprovante: lançamento casado com comprovante cujo favorecido é o fornecedor, mesmo valor -> conferido.
4. Malote: título digitado numa fita ainda sem retorno -> no malote.
5. Nome: lançamento com o mesmo valor, perto do vencimento, cuja descrição traz uma palavra do nome do fornecedor
   (ex.: "vigilante de rua" digitado no Caixa Loja sem o código) -> provável.
6. Só valor: qualquer banco, mesmo valor, perto do vencimento, um único candidato -> provável.
Sem prova: saiu do RET -> baixado sem prova; senão vencido ou a vencer.
"""
import datetime as dt
import re
from collections import defaultdict

from .classificador import chave_nome
from .texto import chave
from .titulos import doc_normalizado, titulos_em_malote

# (dias antes do vencimento, dias depois) em que o pagamento pode aparecer
JANELA_LOTERICA = (-20, 45)       # malote pode voltar semanas depois
JANELA_VALOR = (-5, 10)
JANELA_FATURA = (-10, 60)         # compra no cartão: o débito da fatura vem até ~2 meses depois
TARIFA_BOLETO = 1.65

SITUACOES = {
    "pago_conferido": "Pago e conferido",
    "pago_diferenca": "Pago com diferença",
    "pago_provavel": "Pago provável",
    "pago_fora": "Pago fora",
    "no_malote": "No malote",
    "aguardando_fatura": "Aguardando fatura",
    "baixado_sem_prova": "Baixado no RET sem prova",
    "vencido": "Em aberto — vencido",
    "a_vencer": "Em aberto — a vencer",
    "cancelado": "Cancelado",
}
PAGOS = {"pago_conferido", "pago_diferenca", "pago_provavel", "pago_fora"}
CODIGO = re.compile(r"^(\d{3,6}) - ")


def _codigo(descricao) -> str:
    m = CODIGO.match(str(descricao or ""))
    return m.group(1) if m else ""


def _nome(texto) -> str:
    """Começo do nome do fornecedor para comparar com o favorecido do comprovante. Nomes curtos ("BRF S.A")
    ficam vazios na chave_nome; nesse caso usa as letras do nome como estão."""
    texto = re.sub(r"^\d{3,6} - ", "", str(texto or ""))
    return chave_nome(texto)[:8] or re.sub(r"[^A-Z0-9]", "", chave(texto))[:8]


COMUNS = {"COMERCIO", "COMERCIAL", "LTDA", "ALIMENTOS", "DISTRIBUIDORA", "DISTRIBUICAO", "INDUSTRIA", "PRODUTOS",
          "SERVICOS", "BRASIL", "GERAL", "PAGAMENTO", "TITULO", "FORNECEDOR", "MENSALIDADE"}


def _palavras(texto) -> set[str]:
    texto = re.sub(r"^\d{3,6} - ", "", str(texto or ""))
    return {p for p in re.findall(r"[A-Z0-9]+", chave(texto)) if len(p) >= 5 and p not in COMUNS}


def _dias(lanc, titulo) -> int:
    return (lanc["data"] - titulo["vencimento"]).days


def conciliar(titulos: list[dict], lancamentos: list[dict], favorecidos: dict | None = None,
              carteira_malotes=None, hoje: dt.date | None = None) -> dict:
    """Devolve {id do título: resultado}. Não altera os títulos.

    `lancamentos`: da planilha oficial (id, banco, data, descricao, documento, valor).
    `favorecidos`: {id do lançamento: favorecido do comprovante} (Santander).
    `carteira_malotes`: Carteira (para saber os títulos que estão em malote).
    """
    hoje = hoje or dt.date.today()
    favorecidos = favorecidos or {}
    em_malote = titulos_em_malote(carteira_malotes) if carteira_malotes else {}
    itens_fatura = carteira_malotes.itens_de_fatura() if carteira_malotes else set()
    saidas = [l for l in lancamentos if l.get("data") and (l.get("valor") or 0) < 0]
    por_id = {l["id"]: l for l in saidas}
    por_codigo = defaultdict(list)
    por_valor = defaultdict(list)
    for l in saidas:
        if l["banco"] == "Caixa Loja" and _codigo(l["descricao"]):
            por_codigo[_codigo(l["descricao"])].append(l)
        por_valor[round(-l["valor"], 2)].append(l)
    usados: set[str] = set()
    res: dict[str, dict] = {}
    validos = [t for t in titulos if isinstance(t.get("vencimento"), dt.date)]
    pendentes = sorted(validos, key=lambda t: (t["vencimento"], t["id"]))

    def pago(t, situacao, lanc, prova, **extra):
        usados.add(lanc["id"])
        res[t["id"]] = {"situacao": situacao, "prova": prova, "id_lancamento": lanc["id"], "data_pagamento": lanc["data"],
                        "valor_pago": round(-lanc["valor"], 2), "banco_pagamento": lanc["banco"],
                        "descricao_pagamento": lanc["descricao"], **extra}

    # 0. marcações do usuário
    for t in pendentes:
        marca = t.get("marca") or ""
        if marca == "cancelado":
            res[t["id"]] = {"situacao": "cancelado", "prova": "Marcado como cancelado"}
        elif marca == "aguardando_fatura":
            # Compra da fatura do cartão (já aberta) com o mesmo valor, até 60 dias depois do vencimento do boleto.
            item = next((l for l in por_valor.get(round(float(t["valor"] or 0), 2), []) if l["id"] in itens_fatura
                         and l["id"] not in usados and JANELA_FATURA[0] <= _dias(l, t) <= JANELA_FATURA[1]), None)
            if item:
                pago(t, "pago_conferido", item, f"Fatura do cartão: {item['descricao']}")
            else:
                res[t["id"]] = {"situacao": "aguardando_fatura", "prova": "Cartão de crédito: baixa com a fatura"}
        elif marca == "pago_fora":
            res[t["id"]] = {"situacao": "pago_fora", "prova": t.get("observacao") or "Baixa manual"}
        elif marca == "confirmado" and t.get("lancamento_confirmado") in por_id:
            pago(t, "pago_conferido", por_id[t["lancamento_confirmado"]], "Confirmado por você")
    abertos = lambda: [t for t in pendentes if t["id"] not in res]

    # 1-2. lotérica / Caixa Loja com o código do fornecedor
    for t in abertos():
        cands = [l for l in por_codigo.get(t["codigo"], []) if l["id"] not in usados
                 and JANELA_LOTERICA[0] <= _dias(l, t) <= JANELA_LOTERICA[1]]
        doc = doc_normalizado(t.get("documento"))
        com_doc = [l for l in cands if doc and doc_normalizado(l.get("documento")) == doc]
        if com_doc:
            l = min(com_doc, key=lambda l: abs(-l["valor"] - t["valor"]))
            igual = abs(-l["valor"] - t["valor"]) < 0.005
            pago(t, "pago_conferido" if igual else "pago_diferenca", l,
                 f"Lotérica/Caixa Loja: fornecedor e documento {t['documento']}")
            continue
        mesmo_valor = [l for l in cands if abs(-l["valor"] - t["valor"]) < 0.005]
        if mesmo_valor:
            l = min(mesmo_valor, key=lambda l: abs(_dias(l, t)))
            pago(t, "pago_conferido", l, "Lotérica/Caixa Loja: fornecedor e valor")

    # 3. comprovante do Santander com o favorecido = fornecedor
    for t in abertos():
        nome = _nome(t["fornecedor"])
        if not nome:
            continue
        cands = [l for v in (t["valor"], round(t["valor"] + TARIFA_BOLETO, 2)) for l in por_valor.get(v, [])
                 if l["id"] not in usados and l["id"] in favorecidos
                 and _nome(favorecidos[l["id"]]) == nome and JANELA_VALOR[0] <= _dias(l, t) <= JANELA_VALOR[1]]
        if cands:
            l = min(cands, key=lambda l: abs(_dias(l, t)))
            pago(t, "pago_conferido", l, f"Comprovante: {favorecidos[l['id']]}")

    # 4. malote
    for t in abertos():
        if t["id"] in em_malote:
            res[t["id"]] = {"situacao": "no_malote", "prova": f"Malote {em_malote[t['id']]}",
                            "malote": em_malote[t["id"]]}

    # 5. mesmo valor e a descrição traz o nome do fornecedor
    for t in abertos():
        nome = _palavras(t["fornecedor"])
        cands = [l for l in por_valor.get(t["valor"], []) if l["id"] not in usados and nome & _palavras(l["descricao"])
                 and JANELA_VALOR[0] <= _dias(l, t) <= JANELA_VALOR[1]]
        if cands:
            l = min(cands, key=lambda l: abs(_dias(l, t)))
            pago(t, "pago_provavel", l, f"Mesmo valor e nome em {l['banco']}: {l['descricao']} — confirme")

    # 6. só pelo valor, em qualquer banco (um único candidato)
    for t in abertos():
        cands = [l for l in por_valor.get(t["valor"], []) if l["id"] not in usados
                 and JANELA_VALOR[0] <= _dias(l, t) <= JANELA_VALOR[1]]
        if len(cands) == 1:
            pago(t, "pago_provavel", cands[0], f"Mesmo valor em {cands[0]['banco']} — confirme")
        elif 1 < len(cands) <= 3:
            res[t["id"]] = {"situacao": "", "candidatos": [c["id"] for c in cands],
                            "prova": f"{len(cands)} pagamentos com o mesmo valor — escolha qual"}
        elif cands:   # valor comum (ex.: 100,00): listar todos só atrapalha
            res[t["id"]] = {"situacao": "", "prova": f"{len(cands)} pagamentos com esse valor perto do vencimento — nenhum com o nome do fornecedor"}

    # sem prova
    for t in pendentes:
        r = res.setdefault(t["id"], {"situacao": "", "prova": ""})
        if not r["situacao"]:
            if t.get("no_ret") == "Não":
                r["situacao"] = "baixado_sem_prova"
            else:
                r["situacao"] = "vencido" if t["vencimento"] < hoje else "a_vencer"
    for t in pendentes:  # o malote fica como informação mesmo depois de pago
        res[t["id"]]["malote"] = em_malote.get(t["id"], "")
    return res


def aplicar_resultado(titulos: list[dict], resultado: dict):
    """Copia o resultado da conciliação para os títulos (colunas gravadas para o Power BI)."""
    for t in titulos:
        r = resultado.get(t["id"], {})
        t["situacao"] = SITUACOES.get(r.get("situacao", ""), "")
        t["prova"] = r.get("prova", "")
        t["id_lancamento"] = r.get("id_lancamento", "")
        t["data_pagamento"] = r.get("data_pagamento", "")
        t["valor_pago"] = r.get("valor_pago", "")
        t["malote"] = r.get("malote", "")
