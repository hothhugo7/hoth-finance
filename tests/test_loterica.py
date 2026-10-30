import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.leitores import ler_ret_loterica  # noqa: E402
from hoth.texto import id_lancamento  # noqa: E402

CAB = ["Pago", "Vencimento", "Documento", "Par", "Duplicata", "Fornecedor", "Compra", "Devido R$", "Juros R$",
       "Desc R$", "Pago R$"]


def linha(doc, fornecedor, pago):
    return ["23/09/2026", "25/09/2026", doc, 1.0, 1.0, fornecedor, "10/09/2026", pago, 0.0, 0.0, pago]


def test_ret_vira_saidas_da_caixa_loja():
    r = ler_ret_loterica("loterica.xls", [
        CAB,
        linha(429686.0, "00025 - DISTRIBUIDORA ALFA LTDA", 573.32),
        linha("002207399", "00726 - COOPERATIVA CENTRAL AURORA ", 365.75),
        linha("002207400", "00726 - COOPERATIVA CENTRAL AURORA ", 365.75),
        ["", "", "", "", "", "", "", "", "", "", ""],
    ])
    l = r["lancamentos"]
    assert r["banco"] == "Caixa Loja" and len(l) == 3
    assert l[0]["data"] == dt.date(2026, 9, 23) and l[0]["valor"] == -573.32
    assert l[0]["documento"] == "429686" and l[1]["documento"] == "002207399"
    assert l[1]["descricao"] == "00726 - COOPERATIVA CENTRAL AURORA"
    # Mesmo ID do histórico migrado (sem documento); boletos iguais no dia separados pela ocorrência.
    assert l[0]["id"] == id_lancamento("Caixa Loja", dt.date(2026, 9, 23), -573.32,
                                       "00025 - DISTRIBUIDORA ALFA LTDA", "", 1)
    assert l[1]["id"] != l[2]["id"]


def test_ret_recusa_outro_relatorio():
    with pytest.raises(ValueError, match="RET"):
        ler_ret_loterica("outro.xls", [["Data", "Histórico"]])


def test_regras_fixas_por_codigo_de_fornecedor():
    from hoth.classificador import Classificador

    def lanc(descricao, conta=""):
        return {"banco": "Caixa Loja", "descricao": descricao, "valor": -100.0, "conta": conta}

    historico = [lanc("00487 - IRMAOS DEQUERO", "FORNECEDOR EM GERAL")] * 3 + [
        lanc("00487 - IRMAOS DEQUERO", "FORNECEDOR DE HORTIFRUTI")] * 2 + [
        lanc("00747 - TELEFONICA BRASIL", "TELEFONIA FIXA")] * 3
    clf = Classificador(historico, regras_fixas={"00487": "FORNECEDOR DE HORTIFRUTI", "00747": ""})
    r = clf.classificar(lanc("00487 - IRMAOS DEQUERO COMERCIO E"))
    assert (r.conta, r.regra) == ("FORNECEDOR DE HORTIFRUTI", "fixa")
    # "Sempre revisar": histórico consistente vira só sugestão.
    r = clf.classificar(lanc("00747 - TELEFONICA BRASIL"))
    assert r.conta == "" and r.sugestoes[0][0] == "TELEFONIA FIXA"
    assert Classificador(historico).classificar(lanc("00747 - TELEFONICA BRASIL")).conta == "TELEFONIA FIXA"


def test_previa_revisada_nao_e_sobrescrita(tmp_path):
    import openpyxl
    from hoth.importacao import salvar_previa

    p = {"banco": "Caixa Loja", "conta_bancaria": "", "extrato": "x.xls", "sha256": "", "lidos": 1, "ja_existem": 0,
         "novos": [{"id": "A1", "data": dt.date(2026, 10, 1), "descricao": "00014 - X", "valor": -10.0, "proposta": "",
                    "regra": "", "confianca": "", "favorecido": "", "comprovante": "", "sugestoes": [],
                    "candidatos": []}]}
    caminho = tmp_path / "previa.xlsx"
    salvar_previa(p, caminho, ["FORNECEDOR EM GERAL"])
    salvar_previa(p, caminho, ["FORNECEDOR EM GERAL"])   # sem revisão: pode gerar de novo
    wb = openpyxl.load_workbook(caminho)
    wb["Prévia"]["E2"] = "FORNECEDOR EM GERAL"
    wb.save(caminho)
    with pytest.raises(ValueError, match="revisada"):
        salvar_previa(p, caminho, ["FORNECEDOR EM GERAL"])
