import datetime as dt
import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.estrutura import BANCOS_PADRAO, GRUPOS_PADRAO, Conta, Estrutura  # noqa: E402
from hoth.modelo import GeradorPlanilha  # noqa: E402
from hoth.texto import chave, id_lancamento  # noqa: E402


def test_chave_ignora_acento_caixa_e_espacos():
    assert chave("  Despesas  bancárias ") == chave("DESPESAS BANCARIAS")
    assert chave(None) == ""


def test_id_lancamento_estavel_e_diferencia_ocorrencias():
    d = dt.date(2026, 9, 30)
    a = id_lancamento("Cora", d, -458.15, "Transf Pix enviada", "", 1)
    assert a == id_lancamento("cora", d, -458.15, "TRANSF  PIX ENVIADA", "", 1)
    assert a != id_lancamento("Cora", d, -458.15, "Transf Pix enviada", "", 2)


def _estrutura():
    contas = [
        Conta("01.01", "RECEITA DE VENDAS DE MERCADORIA", "01", entra_dre=False, ordem=1),
        Conta("01.02", "FATURAMENTO - VENDAS REALIZADAS", "01", entra_dfc=False, ordem=2),
        Conta("02.01", "ICMS", "02", ordem=3),
        Conta("09.01", "DEVOLUÇÃO DE VALOR", "09", grupo_dre="01", ordem=4),
        Conta("12.01", "APLICAÇÃO", "12", entra_dre=False, ordem=5),
        Conta("07.01", "PROLABORE SÓCIOS JOSÉ", "07", dre_manual=True, ordem=6),
    ]
    return Estrutura(grupos=list(GRUPOS_PADRAO), contas=contas, bancos=list(BANCOS_PADRAO))


def test_gera_planilha_com_tabelas_e_linhas_do_plano(tmp_path):
    caminho = tmp_path / "hoth.xlsx"
    lanc = [{"id": "X1", "banco": "Cora", "data": dt.date(2026, 1, 5), "descricao": "venda", "documento": "",
             "valor": 100.0, "conta": "RECEITA DE VENDAS DE MERCADORIA", "origem": "teste", "referencia": "",
             "observacao": ""}]
    ajustes = [{"ano": 2026, "mes": 1, "conta": "FATURAMENTO - VENDAS REALIZADAS", "tipo": "SUBSTITUI",
                "valor": 1000.0, "motivo": "teste"}]
    manual = [{"ano": 2026, "mes": 3, "conta": "PROLABORE SÓCIOS JOSÉ", "valor": -12000.0}]
    pos = GeradorPlanilha(_estrutura()).gerar(caminho, lancamentos=lanc, ajustes=ajustes, orcamento=[],
                                              saldos=[], auditoria=[[dt.datetime(2026, 1, 1), "t", "", 0, "", ""]],
                                              dre_manual=manual)
    wb = openpyxl.load_workbook(caminho)
    assert wb.sheetnames[:4] == ["Capa", "Lançamentos", "DFC", "DRE"]
    tabelas = {t for ws in wb.worksheets for t in ws.tables}
    assert {"tbLanc", "tbPlano", "tbGrupos", "tbBancos", "tbSaldos", "tbAjustes", "tbOrc", "tbAuditoria"} <= tabelas
    assert {"AnoBase", "lstContas", "MesesFechados"} <= set(wb.defined_names.keys())

    dfc_codigos = {wb["DFC"].cell(r, 2).value for r in range(1, wb["DFC"].max_row + 1)}
    assert "01.01" in dfc_codigos and "01.02" not in dfc_codigos  # conta só da DRE não aparece na DFC
    dre = wb["DRE"]
    linhas_dre = {dre.cell(r, 2).value: r for r in range(6, dre.max_row + 1)}
    assert "01.01" not in linhas_dre                      # conta só de caixa não aparece na DRE
    assert linhas_dre["09.01"] < linhas_dre["02"]          # Grupo DRE diferente: devolução fica no faturamento
    assert pos["dre_base"] == linhas_dre["01"]

    real_jan = dre.cell(linhas_dre["01.02"], pos["dre_col_mes"][1] + 1).value
    assert 'tbAjustes[Tipo],"SUBSTITUI"' in real_jan and "tbLanc[Valor]" in real_jan

    calc = {c.name: c.calculatedColumnFormula for c in wb["Lançamentos"].tables["tbLanc"].tableColumns}
    assert calc["Código"] is not None and calc["Ano"] is not None
    assert wb["Lançamentos"]["A2"].value == "X1"

    pl = dre.cell(linhas_dre["07.01"], pos["dre_col_mes"][3] + 1).value
    assert "'DRE Manual'!" in pl and "tbLanc" not in pl   # pró-labore vem só do valor digitado
    grade = wb["DRE Manual"]
    assert grade["A6"].value == "07.01" and grade["F6"].value == -12000.0  # março = coluna F


def test_corrige_acentos_corrompidos_do_csv():
    from hoth.texto import limpar
    assert limpar("Transf Pix enviadaMaÃ­ra AraÃºjo Moraes") == "Transf Pix enviadaMaíra Araújo Moraes"
    assert limpar("AÇOUGUE") == "AÇOUGUE"
    assert chave("PatrÃ­cia") == chave("Patrícia")
