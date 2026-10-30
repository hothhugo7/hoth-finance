import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.conciliacao import conciliar  # noqa: E402
from hoth.consulta import candidatos_malote  # noqa: E402
from hoth.titulos import (ArquivoTitulos, Carteira, aplicar_importacao, comparar_importacao,  # noqa: E402
                          ler_ret_abertos)

CAB = ["Vencto", "Atraso", "Documento", "Par", "Duplicata", "Fornecedor", "Compra", "Loja", "A Pagar R$", "Cobrança",
       "Banco", "Cheque"]
D = dt.date


def linha(venc, doc, fornecedor, valor, par=1.0, dup=1.0, compra="01/10/2026", banco="SANTA"):
    return [venc, "", doc, par, dup, fornecedor, compra, 0.0, valor, "BANCO", banco, ""]


def ret(*linhas):
    return ler_ret_abertos("ret.xls", [CAB, *linhas, ["", "", "", "", "", "", "", "", "", "", "", ""]])


def lanc(id_, banco, data, descricao, valor, documento=""):
    return {"id": id_, "banco": banco, "data": data, "descricao": descricao, "valor": valor, "documento": documento}


def test_le_ret_e_id_estavel_com_repeticao():
    r = ret(linha("20/10/2026", 62052.0, "00487 - IRMAOS DEQUERO ", 461.0),
            linha("20/10/2026", "CONTA AGUA ", "01522 - BRK AMBIENTAL", 50.0, par=10.0, dup="/10"),
            linha("20/10/2026", "CONTA AGUA ", "01522 - BRK AMBIENTAL", 60.0, par=10.0, dup="/10"))
    t = r["titulos"]
    assert [x["codigo"] for x in t] == ["00487", "01522", "01522"]
    assert t[0]["documento"] == "62052" and t[0]["vencimento"] == D(2026, 10, 20)
    assert t[1]["id"] != t[2]["id"]                       # mesma chave no relatório: ocorrência separa
    assert ret(linha("20/10/2026", 62052.0, "00487 - X", 999.0))["titulos"][0]["id"] == t[0]["id"]  # valor fora do ID
    with pytest.raises(ValueError, match="RET"):
        ler_ret_abertos("x.xls", [["Pago", "Vencimento"]])


def test_reimportar_atualiza_e_marca_quem_saiu_so_dentro_do_periodo():
    c = Carteira()
    aplicar_importacao(c, ret(linha("10/10/2026", "1", "00001 - A", 100.0), linha("20/10/2026", "2", "00002 - B", 200.0),
                              linha("30/12/2026", "3", "00003 - C", 300.0)), hoje=D(2026, 10, 14))
    novo = ret(linha("12/10/2026", "1", "00001 - A", 110.0), linha("15/10/2026", "4", "00004 - D", 50.0))
    cmp = comparar_importacao(c, novo)
    assert len(cmp["novos"]) == 1 and len(cmp["mudaram"]) == 1
    assert [t["documento"] for t in cmp["sairam"]] == []    # "2" vence 20/10, fora do período 12–15/10
    aplicar_importacao(c, novo, hoje=D(2026, 10, 19))
    a = next(t for t in c.titulos if t["documento"] == "1")
    assert a["valor"] == 110.0 and "valor 100.0 -> 110.00" in a["historico"]
    assert len(c.titulos) == 4                              # nada é apagado
    aplicar_importacao(c, ret(linha("01/10/2026", "4", "00004 - D", 50.0), linha("31/12/2026", "9", "00009 - Z", 1.0)),
                       hoje=D(2026, 10, 26))
    assert {t["documento"]: t["no_ret"] for t in c.titulos} == {"1": "Não", "2": "Não", "3": "Não", "4": "Sim", "9": "Sim"}


def _carteira(*linhas, hoje=D(2026, 10, 14)):
    c = Carteira()
    aplicar_importacao(c, ret(*linhas), hoje=hoje)
    return c


def test_conciliacao_regras():
    c = _carteira(linha("10/10/2026", "111", "00025 - ACUCAREIRA", 573.32),        # lotérica com documento
                  linha("10/10/2026", "222", "00089 - HOLAMBRA", 162.16),           # lotérica pelo valor
                  linha("10/10/2026", "333", "00008 - BRF S.A", 2453.27),           # comprovante (nome curto)
                  linha("10/10/2026", "444", "00500 - FULANO", 777.77),             # só valor -> provável
                  linha("10/10/2026", "555", "00600 - CICLANO", 50.0),              # dois candidatos
                  linha("10/10/2026", "666", "00700 - BELTRANO", 88.0),             # sem prova, vencido
                  linha("10/10/2026", "777", "00800 - CARTAO", 564.47),             # aguardando fatura
                  linha("30/12/2026", "888", "00900 - FUTURO", 10.0))               # a vencer
    c.titulos[6]["marca"] = "aguardando_fatura"
    lancs = [lanc("L1", "Caixa Loja", D(2026, 10, 12), "00025 - DISTRIBUIDORA ALFA", -580.0, "000111"),
             lanc("L2", "Caixa Loja", D(2026, 10, 9), "00089 - COOPERATIVA HOLAMBRA", -162.16),
             lanc("L3", "Santander", D(2026, 10, 13), "PAGAMENTO DE TITULO", -2453.27),
             lanc("L4", "Cora", D(2026, 10, 11), "Pix enviado fulano", -777.77),
             lanc("L5", "Santander", D(2026, 10, 10), "PIX", -50.0), lanc("L6", "Caixa Loja", D(2026, 10, 11), "troca", -50.0),
             lanc("L7", "Santander", D(2026, 10, 10), "PIX", -564.47)]
    r = conciliar(c.titulos, lancs, {"L3": "BRF SA"}, c, hoje=D(2026, 10, 26))
    sit = {t["documento"]: r[t["id"]]["situacao"] for t in c.titulos}
    assert sit == {"111": "pago_diferenca", "222": "pago_conferido", "333": "pago_conferido", "444": "pago_provavel",
                   "555": "vencido", "666": "vencido", "777": "aguardando_fatura", "888": "a_vencer"}
    assert len(r[c.titulos[4]["id"]]["candidatos"]) == 2
    # confirmar um dos candidatos
    c.titulos[4].update(marca="confirmado", lancamento_confirmado="L6")
    r = conciliar(c.titulos, lancs, {"L3": "BRF SA"}, c, hoje=D(2026, 10, 26))
    assert r[c.titulos[4]["id"]]["situacao"] == "pago_conferido" and r[c.titulos[4]["id"]]["id_lancamento"] == "L6"


def test_baixado_sem_prova_e_malote():
    c = _carteira(linha("20/10/2026", "1", "00001 - A", 326.46), linha("20/10/2026", "2", "00002 - B", 351.84))
    c.titulos[1]["no_ret"] = "Não"
    c.malotes.append({"id": "M20261026-1", "envio": D(2026, 10, 26)})
    c.malote_valores.append({"malote": "M20261026-1", "ordem": 1, "valor": 326.46, "titulo": c.titulos[0]["id"]})
    r = conciliar(c.titulos, [], {}, c, hoje=D(2026, 10, 26))
    assert r[c.titulos[0]["id"]]["situacao"] == "no_malote" and r[c.titulos[1]["id"]]["situacao"] == "baixado_sem_prova"
    # o retorno da lotérica fecha o malote
    lancs = [lanc("L1", "Caixa Loja", D(2026, 10, 29), "00001 - A LTDA", -326.46, "1")]
    r = conciliar(c.titulos, lancs, {}, c, hoje=D(2026, 10, 30))
    assert r[c.titulos[0]["id"]]["situacao"] == "pago_conferido" and r[c.titulos[0]["id"]]["malote"] == "M20261026-1"


def test_candidatos_do_malote_pelo_valor():
    c = _carteira(linha("20/10/2026", "1", "00001 - A", 741.87), linha("27/10/2026", "2", "00001 - A", 741.87, par=2.0),
                  linha("27/10/2026", "3", "00002 - B", 10.0))
    r = conciliar(c.titulos, [], {}, c, hoje=D(2026, 10, 26))
    cands = candidatos_malote(741.87, D(2026, 10, 26), c.titulos, r)
    assert [x["documento"] for x in cands] == ["2", "1"]                 # vencimento mais próximo primeiro
    assert [x["documento"] for x in candidatos_malote(741.87, D(2026, 10, 26), c.titulos, r, {cands[0]["id"]})] == ["1"]
    assert candidatos_malote(99.0, D(2026, 10, 26), c.titulos, r) == []


def test_sem_candidato_nao_pede_para_escolher():
    c = _carteira(linha("10/10/2026", "1", "00014 - GERAL", 564.47))
    r = conciliar(c.titulos, [], {}, c, hoje=D(2026, 10, 26))[c.titulos[0]["id"]]
    assert r["situacao"] == "vencido" and r["prova"] == "" and "candidatos" not in r


def test_arquivo_de_titulos_grava_le_e_faz_backup(tmp_path):
    arq = ArquivoTitulos(tmp_path / "titulos.xlsx", tmp_path / "bkp")
    c = _carteira(linha("20/10/2026", 62052.0, "00487 - DEQUERO", 461.0))
    c.malotes.append({"id": "M1", "envio": D(2026, 10, 26), "total_fita": 461.0, "observacao": "",
                      "criado_em": dt.datetime(2026, 10, 26, 18, 0)})
    c.malote_valores.append({"malote": "M1", "ordem": 1, "valor": 461.0, "titulo": c.titulos[0]["id"], "observacao": ""})
    assert arq.gravar(c, "Importação RET", "teste") is None          # primeira vez: nada para guardar
    lida = arq.ler()
    t = lida.titulos[0]
    assert (t["documento"], t["vencimento"], t["valor"], t["no_ret"]) == ("62052", D(2026, 10, 20), 461.0, "Sim")
    assert lida.malote_valores[0]["titulo"] == t["id"] and lida.auditoria[0]["acao"] == "Importação RET"
    assert arq.gravar(lida, "Malote", "teste 2") is not None and len(arq.ler().auditoria) == 2
    assert len(list((tmp_path / "bkp").glob("*_antes_*.xlsx"))) == 1


def test_caixa_loja_sem_codigo_casa_pelo_nome_do_fornecedor():
    import datetime as dt
    from hoth.conciliacao import conciliar
    venc = dt.date(2026, 10, 10)
    titulo = {"id": "T1", "codigo": "01526", "fornecedor": "01526 - VIGILANTE DE RUA (GUARDA)", "valor": 100.0,
              "vencimento": venc, "documento": "MENSALIDADE"}
    lancs = [{"id": f"L{i}", "banco": "Santander", "data": venc, "descricao": f"PIX ENVIADO {i}", "valor": -100.0}
             for i in range(9)]
    lancs.append({"id": "V", "banco": "Caixa Loja", "data": venc, "descricao": "vigilante de rua", "valor": -100.0})
    r = conciliar([titulo], lancs, hoje=dt.date(2026, 10, 27))["T1"]
    assert (r["situacao"], r["id_lancamento"]) == ("pago_provavel", "V")
