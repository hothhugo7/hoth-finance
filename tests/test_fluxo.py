import datetime as dt
import sqlite3
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.fluxo import SEM_CATEGORIA, calcular, gerar_planilha, movimentos, por_mes, sugestao_entradas  # noqa: E402
from hoth.titulos import (ArquivoTitulos, Carteira, cadastro_base, criar_categoria,  # noqa: E402
                          definir_categorias)

D = dt.date
HOJE = D(2026, 10, 26)


def titulo(id_, codigo, venc, valor):
    return {"id": id_, "codigo": codigo, "fornecedor": f"{codigo} - F", "documento": id_, "vencimento": venc,
            "valor": valor}


def test_movimentos_sem_data_de_corte():
    ts = [titulo("pago", "001", D(2026, 10, 10), 100.0), titulo("malote", "002", D(2026, 10, 30), 50.0),
          titulo("venc", "001", D(2026, 10, 20), 30.0), titulo("futuro", "003", D(2026, 11, 5), 70.0),
          titulo("canc", "001", D(2026, 11, 5), 999.0), titulo("sem", "002", D(2026, 10, 15), 20.0)]
    r = {"pago": {"situacao": "pago_conferido", "data_pagamento": D(2026, 10, 12), "valor_pago": 101.65},
         "malote": {"situacao": "no_malote", "malote": "M1"}, "venc": {"situacao": "vencido"},
         "futuro": {"situacao": "a_vencer"}, "canc": {"situacao": "cancelado"}, "sem": {"situacao": "baixado_sem_prova"}}
    m = {x["id"]: x for x in movimentos(ts, r, {"001": "MERCADORIA", "002": "DESPESA"}, {"M1": D(2026, 10, 26)}, HOJE)}
    assert "canc" not in m
    assert (m["pago"]["data"], m["pago"]["valor"], m["pago"]["tipo"]) == (D(2026, 10, 12), 101.65, "realizado")
    assert (m["malote"]["data"], m["malote"]["tipo"]) == (D(2026, 10, 26), "realizado")   # saiu do cofre no envio
    assert m["venc"]["data"] == HOJE and m["venc"]["tipo"] == "projetado"
    assert m["futuro"]["data"] == D(2026, 11, 5) and m["futuro"]["categoria"] == SEM_CATEGORIA
    assert m["sem"]["tipo"] == "realizado sem prova"


def test_calcular_periodo_e_meses():
    movs = [{"data": D(2026, 10, 31), "valor": 100.0, "categoria": "MERCADORIA"},
            {"data": D(2026, 11, 2), "valor": 40.0, "categoria": "DESPESA"},
            {"data": D(2026, 12, 1), "valor": 999.0, "categoria": "DESPESA"}]           # fora do período
    entradas = [{"data": D(2026, 11, 2), "valor": 60.0}]
    c = calcular(movs, entradas, D(2026, 10, 30), D(2026, 11, 3), ["MERCADORIA", "DESPESA", "FINANCEIRO"], HOJE)
    assert len(c["dias"]) == 5 and c["totais"] == {"entradas": 60.0, "saidas": 140.0, "resultado": -80.0,
                                                   "por_categoria": {"MERCADORIA": 100.0, "DESPESA": 40.0, "FINANCEIRO": 0.0}}
    assert c["dias"][-1]["acumulado"] == -80.0 and c["menor_acumulado"]["valor"] == -100.0
    meses = por_mes(c["dias"], c["categorias"])
    assert [(m["rotulo"], m["saidas"], m["entradas"]) for m in meses] == [("Out/2026", 100.0, 0.0), ("Nov/2026", 40.0, 60.0)]


def test_sugestao_de_entradas_pela_receita():
    lanc = [{"data": D(2026, 10, 19), "valor": 1000.0, "conta": "RECEITA DE VENDAS DE MERCADORIA"},
            {"data": D(2026, 10, 12), "valor": 500.0, "conta": "Receita de vendas de mercadoria"},
            {"data": D(2026, 10, 19), "valor": -50.0, "conta": "RECEITA DE VENDAS DE MERCADORIA"},
            {"data": D(2026, 10, 20), "valor": 9999.0, "conta": "OUTRA"}]
    s = sugestao_entradas(lanc, HOJE)
    assert s["por_dia_semana"]["Seg"] == 750.0 and s["por_dia_semana"]["Ter"] == 0.0


def test_categorias_e_cadastro_base(tmp_path):
    c = Carteira()
    assert c.nomes_categorias() == ["MERCADORIA", "DESPESA", "FINANCEIRO"]
    assert criar_categoria(c, "impostos") == "IMPOSTOS"
    with pytest.raises(ValueError, match="já existe"):
        criar_categoria(c, "Impostos")
    definir_categorias(c, [{"codigo": "001", "fornecedor": "A", "categoria": "mercadoria"}])
    definir_categorias(c, [{"codigo": "001", "fornecedor": "A", "categoria": "IMPOSTOS"}])
    assert c.categoria_por_codigo() == {"001": "IMPOSTOS"}
    with pytest.raises(ValueError, match="não existe"):
        definir_categorias(c, [{"codigo": "002", "categoria": "INVENTADA"}])
    banco = tmp_path / "c.sqlite3"
    con = sqlite3.connect(banco)
    con.execute("create table fornecedores (codigo text, nome_referencia text, categoria text, atualizado_em text)")
    con.execute("insert into fornecedores values ('00008', 'BRF', 'MERCADORIA', '')")
    con.commit()
    con.close()
    assert cadastro_base(banco) == {"00008": "MERCADORIA"} and cadastro_base(tmp_path / "nao.sqlite3") == {}
    arq = ArquivoTitulos(tmp_path / "t.xlsx", tmp_path / "bkp")          # categorias e entradas ficam no arquivo
    c.entradas.append({"id": "E1", "data": D(2026, 10, 27), "descricao": "Vendas", "valor": 10.0, "forma": "Pix"})
    arq.gravar(c, "teste", "teste")
    lida = arq.ler()
    assert lida.nomes_categorias()[-1] == "IMPOSTOS" and lida.categoria_por_codigo() == {"001": "IMPOSTOS"}
    assert lida.entradas[0]["data"] == D(2026, 10, 27)


def test_planilha_do_fluxo(tmp_path):
    movs = [{"data": D(2026, 10, 27), "valor": 100.0, "tipo": "projetado", "situacao": "a_vencer", "categoria": "MERCADORIA",
             "fornecedor": "X", "documento": "1", "vencimento": D(2026, 10, 27), "codigo": "001", "id": "A"}]
    c = calcular(movs, [], D(2026, 10, 1), D(2026, 11, 30), ["MERCADORIA", "DESPESA"], HOJE)
    caminho = tmp_path / "fluxo.xlsx"
    gerar_planilha(caminho, calculo=c, movs=movs, entradas=[], empresa="SUPERMERCADO EXEMPLO", gerado_em=dt.datetime(2026, 10, 26, 18),
                   conferencia=[("Títulos", 1, True)])
    wb = openpyxl.load_workbook(caminho)
    assert wb.sheetnames == ["Painel", "Fluxo Diário", "Base", "Entradas", "Conferência"]
    assert wb["Painel"]["A6"].value == "Out/2026" and wb["Painel"]["C6"].value == 100.0     # valores, não fórmulas
    assert wb["Fluxo Diário"].max_row == 62 and "tbFluxoDiario" in wb["Fluxo Diário"].tables
