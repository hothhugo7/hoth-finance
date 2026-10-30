"""Piloto: compara um mês da planilha antiga (mantida em paralelo) com a planilha Hoth.

    .venv\\Scripts\\python.exe scripts\\conferir_piloto.py --mes 10 [--origem CAMINHO_DA_ANTIGA]

Compara, para o mês: quantidade e valor dos lançamentos por banco, cada conta da DFC e da DRE, e os resultados
(EBITDA, EBIT...). Gera Relatorios\\Piloto AAAA-MM.xlsx. Só lê as duas planilhas (a antiga é lida de uma cópia).
"""
import argparse
import shutil
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.arquivo import abrir_planilha  # noqa: E402
from hoth.conferencia import RESULTADOS_ANTIGOS  # noqa: E402
from hoth.fechamento_antigo import LeitorFechamento  # noqa: E402
from hoth.planilha_atual import ler  # noqa: E402
from hoth.texto import chave  # noqa: E402

ORIGEM_PADRAO = r"\\servidor\financeiro\FECHAMENTO FINANCEIRO\2026\01. FECHAMENTO FINANCEIRO EXEMPLO - 2026.xlsx"
TOL = 0.01


def valores_hoth(caminho, mes):
    """{(demonstrativo, código ou rótulo): valor do mês} lidos da planilha Hoth (valores calculados)."""
    wb = abrir_planilha(caminho, read_only=True, data_only=True)
    out = {}
    try:
        for aba in ("DFC", "DRE"):
            linhas = list(wb[aba].iter_rows(values_only=True))
            meses, cab = linhas[2], linhas[4]
            if aba == "DFC":
                col = next(i for i, v in enumerate(meses) if v == mes)
            else:
                col = next(i for i, v in enumerate(meses) if v == mes and cab[i] == "REAL")
            for r in linhas[5:]:
                cod, rot = r[1], (r[0] or "").strip()
                v = r[col] if isinstance(r[col], (int, float)) else 0.0
                if cod:
                    out[(aba, str(cod) if cod != "RES" else rot)] = v
                elif rot:
                    out[(aba, rot)] = v
    finally:
        wb.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--origem", default=ORIGEM_PADRAO)
    a = ap.parse_args()
    mes = a.mes
    cfg = config.carregar()

    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "antiga.xlsx"
        shutil.copy2(a.origem, copia)
        print("Lendo a planilha antiga…")
        antiga = LeitorFechamento(str(copia)).ler()
    print("Lendo a planilha Hoth…")
    hoth = ler(cfg["planilha"])
    nova = valores_hoth(cfg["planilha"], mes)
    codigo = {chave(c.nome): c.codigo for c in hoth.estrutura.contas}
    ano = hoth.estrutura.ano

    # Lançamentos por banco no mês
    bancos = []
    cont_a, cont_h = defaultdict(lambda: [0, 0.0]), defaultdict(lambda: [0, 0.0])
    for l in antiga.lancamentos:
        if l["data"].month == mes:
            cont_a[l["banco"]][0] += 1
            cont_a[l["banco"]][1] += l["valor"]
    for l in hoth.lancamentos:
        if l["data"] and l["data"].year == ano and l["data"].month == mes:
            cont_h[l["banco"]][0] += 1
            cont_h[l["banco"]][1] += l["valor"]
    for b in sorted(set(cont_a) | set(cont_h)):
        qa, va = cont_a[b]
        qh, vh = cont_h[b]
        bancos.append([b, qa, round(va, 2), qh, round(vh, 2), qh - qa, round(vh - va, 2)])

    # Contas
    linhas = []
    for demo, origem in (("DFC", antiga.dfc_antiga), ("DRE", antiga.dre_antiga)):
        for nome, serie in origem.items():
            cod = codigo.get(chave(nome))
            velho = serie.get(mes, 0.0)
            novo = nova.get((demo, cod)) if cod else None
            if novo is None and abs(velho) <= TOL:
                continue
            dif = None if novo is None else round(novo - velho, 2)
            if dif is None or abs(dif) > TOL:
                linhas.append([demo, cod or "", nome, velho, novo, dif,
                               "Conta sem linha na Hoth" if novo is None else ""])
    # Resultados da DRE
    resultados = []
    antigos = {chave(k): v for k, v in antiga.dre_antiga_totais.items()}
    for nome_novo, nome_antigo in RESULTADOS_ANTIGOS.items():
        velho = antigos.get(chave(nome_antigo), {}).get(mes)
        novo = nova.get(("DRE", nome_novo))
        if velho is not None or novo is not None:
            resultados.append([nome_novo, velho, novo, None if velho is None or novo is None else round(novo - velho, 2)])

    wb = openpyxl.Workbook()
    cab_font, cab_fill = Font(bold=True, color="C9CDD2"), PatternFill("solid", fgColor="1E1F22")

    def aba(ws, cab, dados, larguras):
        ws.append(cab)
        for c in ws[1]:
            c.font, c.fill = cab_font, cab_fill
        for d in dados:
            ws.append(d)
        for i, w in enumerate(larguras, start=1):
            ws.column_dimensions[L(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, float):
                    c.number_format = '#,##0.00;[Red]-#,##0.00'
        ws.freeze_panes = "A2"

    ws = wb.active
    ws.title = "Lançamentos por banco"
    aba(ws, ["Banco", "Qtd antiga", "Valor antiga", "Qtd Hoth", "Valor Hoth", "Dif. qtd", "Dif. valor"], bancos,
        [18, 12, 16, 12, 16, 10, 16])
    aba(wb.create_sheet("Contas com diferença"),
        ["Demonstrativo", "Código", "Conta", "Planilha antiga", "Planilha Hoth", "Diferença", "Observação"], linhas,
        [12, 9, 46, 16, 16, 14, 30])
    aba(wb.create_sheet("Resultados"), ["Resultado", "Planilha antiga", "Planilha Hoth", "Diferença"], resultados,
        [44, 18, 18, 14])
    saida = RAIZ / "Relatorios" / f"Piloto {ano}-{mes:02d}.xlsx"
    wb.save(saida)

    print(f"\nMês {mes:02d}/{ano}")
    for b in bancos:
        print(f"  {b[0]:<18} antiga {b[1]:>5} lanç. ({b[2]:>14,.2f})  Hoth {b[3]:>5} ({b[4]:>14,.2f})  dif. {b[5]:>+4} / {b[6]:>+12,.2f}")
    print(f"  Contas com diferença: {len(linhas)}")
    for r in resultados:
        print(f"  {r[0]:<40} antiga {r[1] if r[1] is not None else '-':>14}  Hoth {r[2] if r[2] is not None else '-':>14}")
    print(f"Relatório: {saida}")


if __name__ == "__main__":
    main()
