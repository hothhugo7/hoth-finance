import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.classificador import Classificador, chave_regra_descricao  # noqa: E402
from hoth.importacao import arquivo_regras_fixas, carregar_regras_fixas, salvar_regra_fixa  # noqa: E402


def lanc(descricao, conta="", banco="Santander", valor=-10.0):
    return {"banco": banco, "descricao": descricao, "valor": valor, "conta": conta}


def test_regra_por_descricao_vale_antes_do_aprendizado_e_do_fornecedor():
    historico = [lanc("ASSAI ATACADISTA LJ246", "FORNECEDOR EM GERAL")] * 5 + [
        lanc("00487 - DEQUERO", "FORNECEDOR EM GERAL", "Caixa Loja")] * 3
    regras = {chave_regra_descricao("assai atacadista lj246"): "FORNECEDOR DE HORTIFRUTI",
              "00487": "FORNECEDOR DE HORTIFRUTI", chave_regra_descricao("00487 - DEQUERO"): ""}
    clf = Classificador(historico, regras_fixas=regras)
    r = clf.classificar(lanc("ASSAI ATACADISTA LJ246"))
    assert (r.conta, r.regra) == ("FORNECEDOR DE HORTIFRUTI", "fixa")
    # a descrição "sempre revisar" ganha da regra do fornecedor; o aprendido vira sugestão
    r = clf.classificar(lanc("00487 - DEQUERO", banco="Caixa Loja"))
    assert r.conta == "" and r.sugestoes[0][0] == "FORNECEDOR EM GERAL"
    assert Classificador(historico).classificar(lanc("ASSAI ATACADISTA LJ246")).conta == "FORNECEDOR EM GERAL"


def test_salvar_e_tirar_regra_no_arquivo(tmp_path):
    planilha = tmp_path / "planilha.xlsx"
    arq = arquivo_regras_fixas(planilha)
    arq.write_text(json.dumps({"00487": {"fornecedor": "DEQUERO", "conta": "FORNECEDOR DE HORTIFRUTI"}}), encoding="utf-8")
    k = chave_regra_descricao("TARIFA PIX")
    salvar_regra_fixa(planilha, k, "TARIFA PIX", "DESPESAS BANCÁRIAS")
    assert carregar_regras_fixas(planilha) == {"00487": "FORNECEDOR DE HORTIFRUTI", k: "DESPESAS BANCÁRIAS"}
    assert json.loads(arq.read_text(encoding="utf-8"))[k]["descricao"] == "TARIFA PIX"
    assert arq.with_name(arq.name + ".bak").exists()                      # versão anterior guardada
    salvar_regra_fixa(planilha, "00487", "DEQUERO", None)
    assert carregar_regras_fixas(planilha) == {k: "DESPESAS BANCÁRIAS"}
