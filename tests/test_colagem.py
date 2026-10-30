import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.colagem import interpretar, registros, valor_br  # noqa: E402
from hoth.texto import id_lancamento  # noqa: E402

CONTAS = ["RECEITA DE VENDAS DE MERCADORIA", "PAGAMENTO DA TROCA DE CARTÃO", "FORNECEDOR EM GERAL"]
D = dt.date(2026, 9, 29)


def id_(desc, valor, oc=1):
    return id_lancamento("Caixa Loja", D, valor, desc, "", oc)


# Como o Excel (OneDrive) copia: tabulado, valores formatados, com MÊS e SALDO.
COLADO = "\r\n".join([
    "DATA\tMÊS\tDESCRIÇÃO\tPLANO DE CONTAS\tENTRADA\tSAÍDA\tSALDO",
    "29/09/2026\t9\ttroca cartao\tPAGAMENTO DA TROCA DE CARTÃO\t\tR$ 100,00\tR$ 1,00",
    "29/09/2026\t9\ttroca cartao\tPAGAMENTO DA TROCA DE CARTÃO\t\tR$ 100,00\tR$ 1,00",
    "29/09/2026\t9\tfechamento caixa 1\tRECEITA DE VENDAS DE MERCADORIA\tR$ 1.952,05\t\tR$ 1,00",
    "29/09/2026\t9\tRTM\t\t\tR$ 1.500,00\tR$ 1,00",
    "29/09/2026\t9\tpgto lotérica\t\t\tR$ 9.486,61\tR$ 1,00",
    "29/09/2026\t9\tdoces\tfechamento caixa 01\t\t378.10.\tR$ 1,00",
    "",
])


def test_valor_br():
    assert valor_br("R$ 1.952,05") == 1952.05
    assert valor_br("1952.05") == 1952.05
    assert valor_br("1.500") == 1500
    assert valor_br("R$           -") == 0
    assert valor_br("378.10.") is None


def test_interpreta_e_marca_o_que_ja_existe():
    ls = interpretar(COLADO, CONTAS, {id_("troca cartao", -100.0)})
    assert len(ls) == 6
    troca1, troca2, fech, rtm, lot, doces = ls
    assert troca1["ja_existe"] and not troca1["incluir"]
    assert not troca2["ja_existe"] and troca2["incluir"] and troca2["id"] == id_("troca cartao", -100.0, 2)
    assert fech["valor"] == 1952.05 and fech["conta"] == "RECEITA DE VENDAS DE MERCADORIA" and fech["incluir"]
    assert rtm["conta"] == "" and rtm["incluir"]          # sem plano: entra para revisar
    assert lot["loterica"] and not lot["incluir"]          # vem do RET
    assert not doces["incluir"] and any("conta não existe" in a for a in doces["avisos"])


def test_registros_respeitam_ocorrencia_e_repeticao_forcada():
    existentes = {id_("troca cartao", -100.0)}
    ls = interpretar(COLADO, CONTAS, existentes)
    regs = registros(ls, CONTAS, existentes)
    assert [r["descricao"] for r in regs] == ["troca cartao", "fechamento caixa 1", "RTM"]
    assert regs[0]["id"] == id_("troca cartao", -100.0, 2)  # não colide com o que já existe
    assert regs[2]["origem"].endswith("pendente de revisão")
    ls[0]["incluir"] = True                                  # usuário quer lançar de novo
    regs = registros(ls, CONTAS, existentes)
    assert len({r["id"] for r in regs}) == len(regs) and not {r["id"] for r in regs} & existentes


def test_registros_recusam_linha_invalida():
    ls = interpretar(COLADO, CONTAS, set())
    ls[5]["incluir"] = True
    ls[5]["conta"] = "CONTA INVENTADA"
    with pytest.raises(ValueError, match="linha 7"):
        registros(ls, CONTAS, set())


def test_aba_inteira_com_periodo_e_correcao():
    texto = "\n".join([
        "\t\t\t\t\tSALDO:\tR$ 20.000,00",
        "DATA\tMÊS\tDESCRIÇÃO\tPLANO DE CONTAS\tENTRADA\tSAÍDA\tSALDO",
        "01/01/2025\t1\tRetirada Joaquim\t\t\tR$ 2.000,00\tR$ 1,00",
        "26/o7/2025\t7\td,josefina\t\t\tR$ 200,00\tR$ 1,00",
        "28/08/2026\t8\tbatata\tFORNECEDOR EM GERAL\t\tR$ 55,00\tR$ 1,00",
        "29/09/2026\t9\tlandarini\tFORNECEDOR EM GERAL\t\tR$ 399,00\tR$ 1,00",
        "29/09/2026\t9\tclin. Longevidad cuidadores\tFORNECEDOR EM GERAL\t\tR$ 7.400,00\tR$ 1,00",
        "29/09/2026\t9\tfechamento caixa 5\tRECEITA DE VENDAS DE MERCADORIA\t\t\tR$ 1,00",
        "29/09/2026\t9\tfechamento caixa 1\tRECEITA DE VENDAS DE MERCADORIA\tR$ 1.952,05\t\tR$ 1,00",
        "\t\t\t\t\t\t",
    ])
    land = id_("landarini", -399.0)
    hoth = [{"id": "X", "data": D, "valor": -7400.0, "descricao": "clin. longevidad"},
            {"id": land, "data": D, "valor": -399.0, "descricao": "landarini"}]
    ls = interpretar(texto, CONTAS, {"X", land}, hoth, desde=dt.date(2026, 9, 1))
    assert [l["descricao"] for l in ls] == ["batata", "landarini", "clin. Longevidad cuidadores", "fechamento caixa 1"]
    batata, _, clin, fech = ls
    assert batata["fora_periodo"] and not batata["incluir"]
    assert clin["correcao_de"] == "clin. longevidad (-7400.00)" and not clin["incluir"]
    assert fech["incluir"]


def test_correcao_aponta_so_para_a_linha_mais_parecida():
    d = "01/10/2026"
    texto = "\n".join(f"{d}\t10\ttroca cartão\tPAGAMENTO DA TROCA DE CARTÃO\t\tR$ {v}\tR$ 1,00"
                      for v in ("100,00", "255,00", "500,00", "40,00"))
    ja = id_lancamento("Caixa Loja", dt.date(2026, 10, 1), -40.0, "troca cartão", "", 1)
    hoth = [{"id": "X", "data": dt.date(2026, 10, 1), "valor": -110.0, "descricao": "troca cartao"},
            {"id": "Y", "data": dt.date(2026, 10, 1), "valor": -255.0, "descricao": "00025 - BOLETO RET"},
            {"id": ja, "data": dt.date(2026, 10, 1), "valor": -40.0, "descricao": "troca cartão"}]
    ls = interpretar(texto, CONTAS, {"X", "Y", ja}, hoth, desde=dt.date(2026, 10, 1))
    assert [bool(l["correcao_de"]) for l in ls] == [True, False, False, False]
    assert [l["incluir"] for l in ls] == [False, True, True, False]
    # Colando só um trecho do dia (nada dele já gravado), não há como saber o que sumiu: sem alarme.
    parcial = interpretar(texto.split("\n")[0], CONTAS, {"X", "Y", ja}, hoth, desde=dt.date(2026, 10, 1))
    assert not parcial[0]["correcao_de"] and parcial[0]["incluir"]
