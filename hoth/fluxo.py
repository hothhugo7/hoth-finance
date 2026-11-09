"""Fluxo de caixa projetado: quanto sai e quanto entra, dia a dia, a partir do contas a pagar.

Sem data de corte: cada título entra no dia em que o dinheiro sai (ou vai sair):
- pago (conferido, provável, com diferença, fora): na data do pagamento, pelo valor pago — realizado;
- no malote: na data de envio do malote (o dinheiro saiu do cofre) — realizado;
- baixado no RET sem prova: no vencimento — realizado, sem prova;
- em aberto vencido: hoje — projetado (o vencimento original fica registrado);
- em aberto a vencer e aguardando fatura: no vencimento — projetado;
- cancelado: fora do fluxo.
Entradas são digitadas no app. O saldo é a variação acumulada a partir de zero (os saldos dos bancos ainda não
estão conferidos).

A planilha (`Hoth - Fluxo de Caixa Projetado 2026.xlsx`) é gerada com valores, não fórmulas, para o Power BI ler
os números sem precisar do Excel recalcular. Ela é refeita a cada atualização: o que se digita é no app.
"""
import datetime as dt
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.table import Table, TableStyleInfo

from .conciliacao import PAGOS
from .texto import chave

NOME_ARQUIVO = "Hoth - Fluxo de Caixa Projetado 2026.xlsx"
SEM_CATEGORIA = "SEM CATEGORIA"
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def movimentos(titulos: list[dict], resultado: dict, categorias: dict, envio_malote: dict,
               hoje: dt.date | None = None) -> list[dict]:
    """Uma saída por título, na data em que o dinheiro sai. `categorias` = {código do fornecedor: categoria}."""
    hoje = hoje or dt.date.today()
    saida = []
    for t in titulos:
        if not isinstance(t.get("vencimento"), dt.date):
            continue
        r = resultado.get(t["id"], {})
        sit = r.get("situacao", "")
        if sit == "cancelado":
            continue
        valor, tipo = float(t["valor"] or 0), "projetado"
        if sit in PAGOS and isinstance(r.get("data_pagamento"), dt.date):
            data, valor, tipo = r["data_pagamento"], float(r.get("valor_pago") or valor), "realizado"
        elif sit == "no_malote" and isinstance(envio_malote.get(r.get("malote")), dt.date):
            data, tipo = envio_malote[r["malote"]], "realizado"
        elif sit == "baixado_sem_prova":
            data, tipo = t["vencimento"], "realizado sem prova"
        elif sit == "vencido":
            data = hoje
        else:
            data = t["vencimento"]
        saida.append({"data": data, "valor": round(valor, 2), "tipo": tipo, "situacao": sit,
                      "categoria": categorias.get(str(t.get("codigo"))) or SEM_CATEGORIA,
                      "fornecedor": t["fornecedor"], "documento": t["documento"], "vencimento": t["vencimento"],
                      "codigo": t.get("codigo", ""), "id": t["id"]})
    return saida


def calcular(movs: list[dict], entradas: list[dict], de: dt.date, ate: dt.date, categorias: list[str],
             hoje: dt.date | None = None) -> dict:
    """Dia a dia de `de` a `ate`: entradas, saídas por categoria, resultado e acumulado (a partir de zero)."""
    hoje = hoje or dt.date.today()
    cats = list(categorias) + ([SEM_CATEGORIA] if any(m["categoria"] == SEM_CATEGORIA for m in movs) else [])
    cats += sorted({m["categoria"] for m in movs} - set(cats))
    saidas = defaultdict(lambda: defaultdict(float))
    for m in movs:
        if de <= m["data"] <= ate:
            saidas[m["data"]][m["categoria"]] += m["valor"]
    ent = defaultdict(float)
    for e in entradas:
        if isinstance(e.get("data"), dt.date) and de <= e["data"] <= ate:
            ent[e["data"]] += float(e.get("valor") or 0)
    dias, acumulado = [], 0.0
    d = de
    while d <= ate:
        por_cat = {c: round(saidas[d].get(c, 0.0), 2) for c in cats}
        total_saida = round(sum(por_cat.values()), 2)
        resultado = round(ent[d] - total_saida, 2)
        acumulado = round(acumulado + resultado, 2)
        dias.append({"data": d, "dia": DIAS[d.weekday()], "entradas": round(ent[d], 2), "saidas_categoria": por_cat,
                     "saidas": total_saida, "resultado": resultado, "acumulado": acumulado,
                     "tipo": "realizado" if d < hoje else ("hoje" if d == hoje else "projetado")})
        d += dt.timedelta(days=1)
    totais = {"entradas": round(sum(x["entradas"] for x in dias), 2), "saidas": round(sum(x["saidas"] for x in dias), 2),
              "por_categoria": {c: round(sum(x["saidas_categoria"][c] for x in dias), 2) for c in cats}}
    totais["resultado"] = round(totais["entradas"] - totais["saidas"], 2)
    menor = min(dias, key=lambda x: x["acumulado"]) if dias else None
    return {"de": de, "ate": ate, "categorias": cats, "dias": dias, "totais": totais,
            "menor_acumulado": {"data": menor["data"], "valor": menor["acumulado"]} if menor else None}


def por_mes(dias: list[dict], categorias: list[str]) -> list[dict]:
    meses = {}
    for x in dias:
        k = (x["data"].year, x["data"].month)
        m = meses.setdefault(k, {"ano": k[0], "mes": k[1], "rotulo": f"{MESES[k[1] - 1]}/{k[0]}", "entradas": 0.0,
                                 "saidas": 0.0, "por_categoria": defaultdict(float), "fim": 0.0})
        m["entradas"] += x["entradas"]
        m["saidas"] += x["saidas"]
        for c in categorias:
            m["por_categoria"][c] += x["saidas_categoria"][c]
        m["fim"] = x["acumulado"]
    saida = []
    for m in meses.values():
        m["resultado"] = round(m["entradas"] - m["saidas"], 2)
        m["por_categoria"] = {c: round(v, 2) for c, v in m["por_categoria"].items()}
        m["entradas"], m["saidas"] = round(m["entradas"], 2), round(m["saidas"], 2)
        saida.append(m)
    return saida


def sugestao_entradas(lancamentos: list[dict], hoje: dt.date | None = None, semanas: int = 8) -> dict:
    """Média de vendas por dia da semana nas últimas `semanas` (conta Receita de Vendas), só como sugestão."""
    hoje = hoje or dt.date.today()
    inicio = hoje - dt.timedelta(weeks=semanas)
    soma, dias = defaultdict(float), defaultdict(set)
    for l in lancamentos:
        d = l.get("data")
        if isinstance(d, dt.date) and inicio <= d < hoje and (l.get("valor") or 0) > 0 \
                and chave(l.get("conta")) == "RECEITA DE VENDAS DE MERCADORIA":
            soma[d.weekday()] += l["valor"]
            dias[d.weekday()].add(d)
    por_dia = {DIAS[w]: round(soma[w] / len(dias[w]), 2) if dias[w] else 0.0 for w in range(7)}
    return {"semanas": semanas, "por_dia_semana": por_dia, "media_diaria": round(sum(soma.values()) / max(1, len(
        {d for s in dias.values() for d in s})), 2)}


# ------------------------------------------------------------------------------------------- planilha
ESCURO, PRATA, CLARO = "1B1D21", "E6E8EB", "F2F3F5"
F_CAB = Font(bold=True, color=PRATA)
P_CAB = PatternFill("solid", fgColor=ESCURO)
P_PROJ = PatternFill("solid", fgColor="FFF8E1")
NUM = '#,##0.00;[Red]-#,##0.00;"-"'


def _cabecalho(ws, linha, titulos, larguras=None):
    for i, t in enumerate(titulos, start=1):
        c = ws.cell(linha, i, t)
        c.font, c.fill = F_CAB, P_CAB
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if larguras:
            ws.column_dimensions[L(i)].width = larguras[i - 1]


def _tabela(ws, nome, primeira, ultima_col, ultima_linha):
    if ultima_linha <= primeira:
        return
    t = Table(displayName=nome, ref=f"A{primeira}:{L(ultima_col)}{ultima_linha}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(t)


def gerar_planilha(caminho, *, calculo: dict, movs: list[dict], entradas: list[dict], empresa: str,
                   gerado_em: dt.datetime, conferencia: list[tuple]):
    wb = Workbook()
    cats = calculo["categorias"]
    meses = por_mes(calculo["dias"], cats)

    # Painel
    ws = wb.active
    ws.title = "Painel"
    ws["A1"], ws["A1"].font = "Fluxo de Caixa Projetado", Font(size=16, bold=True)
    ws["A2"] = (f"{empresa} · Hoth Finance · de {calculo['de']:%d/%m/%Y} a {calculo['ate']:%d/%m/%Y} · "
                f"gerado em {gerado_em:%d/%m/%Y %H:%M} pelo app (não digite aqui)")
    ws["A2"].font = Font(size=9, color="6B6F76")
    ws["A3"] = "Saldo = variação acumulada a partir de zero (saldos dos bancos ainda não conferidos)."
    ws["A3"].font = Font(size=9, italic=True, color="6B6F76")
    cab = ["Mês", "Entradas"] + [c.title() for c in cats] + ["Saídas", "Resultado", "Acumulado no fim do mês"]
    _cabecalho(ws, 5, cab, [12, 15] + [15] * len(cats) + [15, 15, 18])
    for i, m in enumerate(meses, start=6):
        vals = [m["rotulo"], m["entradas"]] + [m["por_categoria"].get(c, 0) for c in cats] + [m["saidas"], m["resultado"],
                                                                                            m["fim"]]
        for j, v in enumerate(vals, start=1):
            c = ws.cell(i, j, v)
            if j > 1:
                c.number_format = NUM
    fim = 5 + len(meses)
    tot = ["Total", calculo["totais"]["entradas"]] + [calculo["totais"]["por_categoria"][c] for c in cats] + [
        calculo["totais"]["saidas"], calculo["totais"]["resultado"], None]
    for j, v in enumerate(tot, start=1):
        c = ws.cell(fim + 1, j, v)
        c.font = Font(bold=True)
        if j > 1:
            c.number_format = NUM
    if meses:
        g = BarChart()
        g.title, g.height, g.width = "Entradas × saídas por mês", 7.5, 18
        g.add_data(Reference(ws, min_col=2, min_row=5, max_row=fim), titles_from_data=True)
        g.add_data(Reference(ws, min_col=3 + len(cats), min_row=5, max_row=fim), titles_from_data=True)
        g.set_categories(Reference(ws, min_col=1, min_row=6, max_row=fim))
        ws.add_chart(g, f"A{fim + 4}")
    ws.freeze_panes = "B6"

    # Fluxo Diário
    wd = wb.create_sheet("Fluxo Diário")
    cab = ["Data", "Dia", "Tipo", "Entradas"] + [c.title() for c in cats] + ["Saídas", "Resultado do dia", "Acumulado"]
    _cabecalho(wd, 1, cab, [11, 6, 11, 14] + [14] * len(cats) + [14, 14, 15])
    for i, x in enumerate(calculo["dias"], start=2):
        vals = [x["data"], x["dia"], x["tipo"], x["entradas"]] + [x["saidas_categoria"][c] for c in cats] + [
            x["saidas"], x["resultado"], x["acumulado"]]
        for j, v in enumerate(vals, start=1):
            c = wd.cell(i, j, v)
            c.number_format = "DD/MM/YYYY" if j == 1 else (NUM if j > 3 else "General")
            if x["tipo"] != "realizado":
                c.fill = P_PROJ
    _tabela(wd, "tbFluxoDiario", 1, len(cab), len(calculo["dias"]) + 1)
    wd.freeze_panes = "D2"
    if calculo["dias"]:
        g = LineChart()
        g.title, g.height, g.width = "Acumulado dia a dia", 7.5, 22
        g.add_data(Reference(wd, min_col=len(cab), min_row=1, max_row=len(calculo["dias"]) + 1), titles_from_data=True)
        g.set_categories(Reference(wd, min_col=1, min_row=2, max_row=len(calculo["dias"]) + 1))
        ws.add_chart(g, f"A{fim + 20}")

    # Base (títulos)
    wbase = wb.create_sheet("Base")
    cab = ["Data no fluxo", "Tipo", "Vencimento", "Fornecedor", "Documento", "Valor", "Categoria", "Situação"]
    _cabecalho(wbase, 1, cab, [12, 16, 12, 44, 18, 13, 16, 22])
    for i, m in enumerate(sorted(movs, key=lambda m: (m["data"], m["fornecedor"])), start=2):
        vals = [m["data"], m["tipo"], m["vencimento"], m["fornecedor"], m["documento"], m["valor"], m["categoria"],
                m["situacao"]]
        for j, v in enumerate(vals, start=1):
            c = wbase.cell(i, j, v)
            c.number_format = "DD/MM/YYYY" if j in (1, 3) else (NUM if j == 6 else ("@" if j == 5 else "General"))
    _tabela(wbase, "tbBaseFluxo", 1, len(cab), len(movs) + 1)
    wbase.freeze_panes = "A2"

    # Entradas
    we = wb.create_sheet("Entradas")
    _cabecalho(we, 1, ["Data", "Descrição", "Valor", "Forma"], [12, 40, 14, 16])
    for i, e in enumerate(sorted(entradas, key=lambda e: e["data"]), start=2):
        for j, v in enumerate([e["data"], e.get("descricao", ""), e.get("valor"), e.get("forma", "")], start=1):
            c = we.cell(i, j, v)
            c.number_format = "DD/MM/YYYY" if j == 1 else (NUM if j == 3 else "General")
    _tabela(we, "tbEntradasFluxo", 1, 4, len(entradas) + 1)

    # Conferência
    wc = wb.create_sheet("Conferência")
    _cabecalho(wc, 1, ["Verificação", "Valor", "Situação"], [48, 16, 14])
    for i, (nome, valor, ok) in enumerate(conferencia, start=2):
        wc.cell(i, 1, nome)
        wc.cell(i, 2, valor).number_format = NUM if isinstance(valor, float) else "General"
        wc.cell(i, 3, "OK" if ok else "Verificar")
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
