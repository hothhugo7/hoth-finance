import datetime as dt

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.classificador import Classificador, chave_nome  # noqa: E402
from hoth.comprovantes import Comprovante, casar, extrair  # noqa: E402
from hoth.leitores import ler_ofx_cora  # noqa: E402

OFX = """OFXHEADER:100
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><ACCTID>42905235</ACCTID></BANKACCTFROM><BANKTRANLIST>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20260930000000[0:GMT]</DTPOSTED>
<TRNAMT>-458.15</TRNAMT>
<FITID>e4be1f0e</FITID>
<MEMO>Transf Pix enviada - MARIA DA SILVA EXEMPLO - 123.456.789-09</MEMO>
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT</TRNTYPE>
<DTPOSTED>20260929000000[0:GMT]</DTPOSTED>
<TRNAMT>-100.00</TRNAMT>
<FITID>aa11</FITID>
<MEMO>Pgto QR Code Pix - AMBEV S.A. - CDD MOGIMIRIM - 07.526.557/0001-00</MEMO>
</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>4178.40</BALAMT></LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


def test_ofx_cora_monta_descricao_igual_ao_historico(tmp_path):
    f = tmp_path / "cora.ofx"
    f.write_text(OFX, encoding="utf-8")
    e = ler_ofx_cora(f)
    l1, l2 = e["lancamentos"]  # ordenados por data
    assert l2["descricao"] == "Transf Pix enviadaMARIA DA SILVA EXEMPLO" and l2["cpf_cnpj"] == "123.456.789-09"
    assert l1["descricao"] == "Pgto QR Code PixAMBEV S.A. - CDD MOGIMIRIM"  # nome com " - " no meio
    assert e["saldo_final"] == 4178.40 and l2["documento"] == "e4be1f0e"


def test_comprovante_individual_e_casamento_com_tarifa():
    texto = ("Pagamento realizado com sucesso.\nBeneficiario\nFRICARNE FRIGORIFICO\nData do pagamento\n13/10/2026\n"
             "Valor nominal\nR$ 3.068,77\nValor total a pagar\nR$ 3.068,77\n")
    (c,) = extrair(texto, "13.10.pdf")
    assert (c.favorecido, c.valor, c.data) == ("FRICARNE FRIGORIFICO", 3068.77, dt.date(2026, 10, 13))
    titulo = {"id": "T1", "data": dt.date(2026, 10, 14), "valor": -3070.42,
              "descricao": "PAGAMENTO DE TITULO 4204.4907055541"}
    r = casar([titulo], [c])["T1"]
    assert r["comprovante"] is c and r["regra"] == "valor + tarifa 1,65"


def test_casamento_ambiguo_nao_escolhe():
    a = Comprovante("x.pdf", "dda", dt.date(2026, 9, 15), "BRF SA", 100.0)
    b = Comprovante("y.pdf", "dda", dt.date(2026, 9, 15), "SOUZA CRUZ LTDA", 100.0)
    titulo = {"id": "T", "data": dt.date(2026, 9, 15), "valor": -100.0, "descricao": "PAGAMENTO DE TITULO 1"}
    r = casar([titulo], [a, b])["T"]
    assert r["comprovante"] is None and r["regra"] == "ambíguo" and len(r["candidatos"]) == 2


def _h(desc, valor, conta, banco="Santander"):
    return {"banco": banco, "descricao": desc, "valor": valor, "conta": conta}


def test_classificador_respeita_sentido_e_factoring():
    hist = ([_h("PIX RECEBIDO JOYCE CRISTINA", 10, "RECEITA")] +
            [_h("PIX ENVIADO JOYCE CRISTINA", -10, "TROCA DE CARTÃO")] * 3 +
            [_h("PAGAMENTO DE BOLETO OUTROS BANCOS PETRUS MULTICREDITO FU", -50, "FORNECEDOR EM GERAL")] * 5 +
            [_h(f"PIX RECEBIDO CLIENTE {i}", 5, "RECEITA") for i in range(60)])
    clf = Classificador(hist)
    r = clf.classificar(_h("PIX RECEBIDO JOYCE CRISTINA", 20, ""))
    assert r.conta == "RECEITA"
    titulo = _h("PAGAMENTO DE TITULO 4204", -70, "")
    r = clf.classificar(titulo, favorecido="PETRUS MULTICREDITO FUNDO DE INVESTIMENT")
    assert r.conta == "" and r.sugestoes and r.sugestoes[0][0] == "FORNECEDOR EM GERAL"


def test_chave_nome_tolera_corte_e_palavras_juntas():
    assert chave_nome("MARIA DE LOURDES FORTESBONIN") == chave_nome("MARIA DE LOURDES FORTES BONIN")
    assert chave_nome("ARTUR GUSTINELI JUNIOR LT")[:12] == chave_nome("ARTUR GUSTINELI JUNIOR LTDA")[:12]


def test_editor_plano_criar_renomear_mesclar():
    from hoth.estrutura import BANCOS_PADRAO, GRUPOS_PADRAO, Conta, Estrutura
    from hoth.plano import EditorPlano, ErroPlano
    from collections import Counter
    est = Estrutura(list(GRUPOS_PADRAO), [Conta("04.01", "EMBALAGENS", "04"), Conta("04.02", "ETIQUETAS", "04")],
                    list(BANCOS_PADRAO))
    ed = EditorPlano(est, Counter({"ETIQUETAS": 5}))
    ed.aplicar({"tipo": "criar_conta", "nome": "Energia solar", "grupo": "06", "ativa": True})
    assert any(c.nome == "ENERGIA SOLAR" and c.codigo == "06.01" for c in ed.est.contas)
    with pytest.raises(ErroPlano):
        ed.aplicar({"tipo": "excluir_conta", "codigo": "04.02"})  # tem lançamentos
    ed.aplicar({"tipo": "editar_conta", "codigo": "04.02", "nome": "Etiquetas e rótulos"})
    ed.aplicar({"tipo": "mesclar", "de": "04.02", "para": "04.01"})
    assert ed.renomeacoes == {"ETIQUETAS": "EMBALAGENS", "ETIQUETAS E RÓTULOS": "EMBALAGENS"}
    with pytest.raises(ErroPlano):
        ed.aplicar({"tipo": "criar_conta", "nome": "embalagens", "grupo": "04"})  # nome repetido
    with pytest.raises(ErroPlano):
        ed.aplicar({"tipo": "criar_conta", "nome": "X", "grupo": "04", "campo_que_nao_existe": 1})
