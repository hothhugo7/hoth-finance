import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.classificador import Classificador  # noqa: E402
from hoth.fatura import (aberta_a_mao, achar_debito, agrupar, classificar_itens, descricao_item,  # noqa: E402
                         itens_como_lancamentos, ler_fatura)
from hoth.titulos import Carteira  # noqa: E402

D = dt.date

# Trecho no formato do texto extraído do PDF da fatura (Santander Empresas Mastercard).
TEXTO = "\n".join([
    "FATURA MENSAL", "EMPRESAS MASTERCARD",
    "VALORES EM REAIS Data de Vencimento: 10/10/2026 Data do Fechamento da Fatura: 03/10/2026",
    "SUPERMERCADO EXEMPLO LTDA", "5500 XXXX XXXX 0000",
    "Fatura Anterior", "24.640,75 -", "Pagamentos/Créditos", "24.640,77 =", "Saldo", "-0,02 +",
    "Despesas/Débitos", "1.000,78 =", "Total", "1.000,76",
    "Demonstrativo de Transações",
    "Transações Nacionais",
    "30-06-2026 PRONTO *M G S DISTRIBU PARC  03/05SAO PAULO\\      338,80  ",
    "02-09-2026 ASSAI ATACADISTA LJ246 LIMEIRA\\      500,00  ",
    "10-09-2026 DEB  AUTOM  DE FATURA EM      -24.640,75  ",
    "19-09-2026 EC          *SHELLBOX RIO DE JANEIR\\         ",
    "E",
    "     50,00  ",
    "28-09-2026 ANUIDADE DIFERENCIADA       0,00  ",
    "Transações Internacionais",
    "12-09-2026 OPENAI *CHATGPT SUBSCR SAN FRANCISCO\\ 19,90 BRL 3,75 107,21 5,40",
    "12-09-2026 IOF DESPESA NO EXTERIOR      4,77  ",
    "Total de compras desta Fatura (R$ + US$) 1.000,78",
])


def test_descricao_sem_cidade_e_com_parcela():
    assert descricao_item("ASSAI ATACADISTA LJ246 LIMEIRA\\") == "ASSAI ATACADISTA LJ246"
    assert descricao_item("PRONTO *M G S DISTRIBU PARC  02/05SAO PAULO\\") == "PRONTO *M G S DISTRIBU PARC 02/05"
    assert descricao_item("PNEU Z PARC 07/10GUARULHOS\\") == "PNEU Z PARC 07/10"


def test_le_fatura_soma_igual_ao_debito():
    f = ler_fatura("fatura.pdf", texto=TEXTO)
    assert (f["vencimento"], f["total"], f["compras"], f["cartao"]) == (D(2026, 10, 10), 1000.76, 1000.78, "final 0000")
    descr = [x["descricao"] for x in f["itens"]]
    assert descr == ["PRONTO *M G S DISTRIBU PARC 03/05", "ASSAI ATACADISTA LJ246", "EC *SHELLBOX",
                     "OPENAI *CHATGPT SUBSCR", "IOF DESPESA NO EXTERIOR", "SALDO DA FATURA ANTERIOR"]
    assert [x["valor"] for x in f["itens"]] == [338.8, 500.0, 50.0, 107.21, 4.77, -0.02]  # internacional em R$
    assert f["soma_itens"] == f["total"]                                                # o saldo credor fecha a conta
    with pytest.raises(ValueError, match="fatura"):
        ler_fatura("outro.pdf", texto="Extrato qualquer")


def test_agrupar_por_estabelecimento():
    itens = [{"data_compra": D(2026, 9, 1), "descricao": "PNEU Z PARC 07/10", "valor": 150.0, "texto_fatura": ""},
             {"data_compra": D(2026, 9, 2), "descricao": "PNEU Z PARC 08/10", "valor": 150.0, "texto_fatura": ""},
             {"data_compra": D(2026, 9, 3), "descricao": "ASSAI", "valor": 10.0, "texto_fatura": ""}]
    g = agrupar(itens)
    assert [(x["descricao"], x["valor"]) for x in g] == [("PNEU Z", 300.0), ("ASSAI", 10.0)]


def _lanc(id_, data, desc, valor, conta="", banco="Santander"):
    return {"id": id_, "banco": banco, "data": data, "descricao": desc, "valor": valor, "conta": conta}


def test_achar_debito_e_aberta_a_mao():
    f = ler_fatura("f.pdf", texto=TEXTO)
    lancs = [_lanc("D1", D(2026, 10, 13), "DEBITO AUT. FAT.CARTAO MASTER CARD FINAL 0000", -1000.76),
             _lanc("D2", D(2026, 10, 30), "DEBITO AUT. FAT.CARTAO MASTER CARD FINAL 0000", -1000.76)]   # fora da janela
    assert [l["id"] for l in achar_debito(f, lancs)] == ["D1"]
    assert achar_debito(f, lancs, {"D1"}) == []                        # já aberta: não oferece de novo
    mao = [_lanc("A", D(2026, 10, 10), "ASSAI", -1000.0), _lanc("B", D(2026, 10, 10), "LISTENX", -0.76),
           _lanc("P", D(2026, 10, 10), "PIX ENVIADO X", -99.0)]       # PIX não entra na soma
    assert aberta_a_mao(f, mao)["data"] == D(2026, 10, 10)
    assert aberta_a_mao(f, mao[:1]) is None


def test_itens_viram_lancamentos_na_data_do_debito_e_classificam():
    f = ler_fatura("f.pdf", texto=TEXTO)
    debito = {"id": "D1", "data": D(2026, 10, 13)}
    ls = itens_como_lancamentos(f["itens"], debito)
    assert {l["data"] for l in ls} == {D(2026, 10, 13)} and round(sum(l["valor"] for l in ls), 2) == -1000.76
    assert len({l["id"] for l in ls}) == len(ls)
    historico = [_lanc("H1", D(2026, 9, 10), "ASSAI ATACADISTA LJ246", -10.0, "FORNECEDOR EM GERAL"),
                 _lanc("H2", D(2026, 9, 10), "TOKIO MARINE AUTO07/D10", -10.0, "SEGURO DE VEÍCULOS DA EMPRESA"),
                 _lanc("H3", D(2026, 8, 10), "TOKIO MARINE*AUTO04D10", -10.0, "SEGURO DE VEÍCULOS DA EMPRESA")]
    itens = [{"descricao": "ASSAI ATACADISTA LJ246", "valor": 5.0}, {"descricao": "TOKIO MARINE*AUTO09D10", "valor": 5.0},
             {"descricao": "PAULISTAO ATACADISTA", "valor": 5.0}]
    classificar_itens(itens, historico, Classificador(historico))
    assert [(i["proposta"], i["regra"]) for i in itens] == [("FORNECEDOR EM GERAL", "exata"),
                                                             ("SEGURO DE VEÍCULOS DA EMPRESA", "estabelecimento"),
                                                             ("", "")]


def test_carteira_guarda_debitos_e_itens_de_faturas_abertas():
    c = Carteira(faturas=[{"id": "F1", "situacao": "aberta", "id_debito": "D1", "ids_itens": "A;B"},
                          {"id": "F2", "situacao": "desfeita", "id_debito": "D2", "ids_itens": "C"}])
    assert c.debitos_abertos() == {"D1"} and c.itens_de_fatura() == {"A", "B"}
