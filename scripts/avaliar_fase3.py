"""Mede a Fase 3 com dados reais, sem gravar nada na planilha.

1. Leitores: o extrato do Santander (01–13/10) e o OFX da Cora (setembro) já estão na planilha;
   todos os lançamentos devem ser reconhecidos como existentes (mesmo ID).
2. Comprovantes: quantos PAGAMENTO DE TITULO do extrato são identificados pelos PDFs.
3. Classificação: aprende com jan–ago e classifica setembro como se fosse novo; compara com a conta real.
"""
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth.classificador import Classificador  # noqa: E402
from hoth.comprovantes import casar, eh_titulo, ler_pasta  # noqa: E402
from hoth.importacao import PASTA_COMPROVANTES, carregar_lancamentos, titulos_identificados  # noqa: E402
from hoth.leitores import ler_extrato  # noqa: E402

from hoth import config  # noqa: E402

PLANILHA = Path(config.carregar()["planilha"])
EXTRATOS = [r"C:\Users\usuario\Desktop\Santander 01-10 a 13-10.xlsx",
            r"\\servidor\financeiro\FECHAMENTO FINANCEIRO\2026\09. Setembro\Cora\Extrato Cora - Setembro.ofx"]
CORTE = dt.date(2026, 9, 1)
FIM = dt.date(2026, 10, 1)


def main():
    hist = carregar_lancamentos(PLANILHA)
    ids = {l["id"] for l in hist}
    resumo = []

    for ext in EXTRATOS:
        lido = ler_extrato(ext)
        L_ = lido["lancamentos"]
        existentes = sum(1 for l in L_ if l["id"] in ids)
        resumo.append((f"Leitor {lido['banco']}: {Path(ext).name}",
                       f"{len(L_)} lidos, {existentes} já estão na planilha, {len(L_) - existentes} novos"))

    comps, nao_lidos = ler_pasta(PASTA_COMPROVANTES)
    resumo.append(("Comprovantes lidos dos PDFs", f"{len(comps)} pagamentos; arquivos não lidos: {len(nao_lidos)}"))
    inicio_comp = min(c.data for c in comps)
    san = [l for l in hist if l["banco"] == "Santander" and l["data"] >= inicio_comp]
    casados = casar(san, comps)
    tit = [l for l in san if l["valor"] < 0 and eh_titulo(l["descricao"])]
    regras = Counter(r["regra"] for r in casados.values())
    resumo.append((f"PAGAMENTO DE TITULO desde {inicio_comp:%d/%m}",
                   f"{len(tit)} no extrato; identificados: {sum(1 for r in casados.values() if r['comprovante'])} "
                   f"({', '.join(f'{k}: {v}' for k, v in regras.items())})"))

    # Classificação de setembro aprendendo só com o que veio antes
    treino = [l for l in hist if l["data"] < CORTE]
    teste = [l for l in hist if CORTE <= l["data"] < FIM and l["banco"] in ("Santander", "Cora") and l["conta"]]
    tit_treino = titulos_identificados(treino, [c for c in comps if c.data < CORTE])
    clf = Classificador(treino, tit_treino)
    casados_teste = casar([l for l in teste if l["banco"] == "Santander"], comps)
    linhas, stats = [], Counter()
    for l in teste:
        c = casados_teste.get(l["id"], {})
        fav = c["comprovante"].favorecido if c.get("comprovante") else ""
        r = clf.classificar(l, fav)
        grupo = (l["banco"], "título" if eh_titulo(l["descricao"]) else "demais")
        stats[grupo + ("total",)] += 1
        if r.conta:
            ok = r.conta == l["conta"]
            stats[grupo + ("auto certo" if ok else "auto errado",)] += 1
            situacao = "Automático certo" if ok else "Automático ERRADO"
        else:
            na_sugestao = l["conta"] in [s[0] for s in r.sugestoes]
            stats[grupo + ("pendente (sugestão certa)" if na_sugestao else "pendente",)] += 1
            situacao = "Pendente - sugestão certa" if na_sugestao else "Pendente"
        linhas.append([l["banco"], l["data"], l["descricao"], l["valor"], fav, l["conta"], r.conta, r.regra,
                       r.confianca, "; ".join(f"{s[0]} ({s[1]})" for s in r.sugestoes), situacao])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resumo"
    for k, v in resumo:
        ws.append([k, v])
    ws.append([])
    ws.append(["Classificação de setembro (aprendendo com jan–ago)", "Total", "Automático certo",
               "Automático errado", "Pendente com sugestão certa", "Pendente", "% automático", "% acerto do automático"])
    for banco in ("Santander", "Cora"):
        for tipo in ("demais", "título"):
            g = (banco, tipo)
            tot = stats[g + ("total",)]
            if not tot:
                continue
            certo, errado = stats[g + ("auto certo",)], stats[g + ("auto errado",)]
            ws.append([f"{banco} - {'PAGAMENTO DE TITULO' if tipo == 'título' else 'demais lançamentos'}", tot,
                       certo, errado, stats[g + ("pendente (sugestão certa)",)], stats[g + ("pendente",)],
                       round((certo + errado) / tot, 3), round(certo / (certo + errado), 3) if certo + errado else None])
    ws.column_dimensions["A"].width = 60
    ws.column_dimensions["B"].width = 70
    for c in "CDEFGH":
        ws.column_dimensions[c].width = 16

    det = wb.create_sheet("Setembro detalhado")
    cab = ["Banco", "Data", "Descrição", "Valor", "Favorecido (comprovante)", "Conta real", "Conta automática",
           "Regra", "Confiança", "Sugestões", "Situação"]
    det.append(cab)
    for c in det[1]:
        c.font, c.fill = Font(bold=True, color="C9CDD2"), PatternFill("solid", fgColor="1E1F22")
    for l in sorted(linhas, key=lambda x: (x[10] != "Automático ERRADO", x[10].startswith("Automático"))):
        det.append(l)
    for i, w in enumerate([11, 11, 52, 12, 34, 36, 36, 11, 10, 70, 24], start=1):
        det.column_dimensions[L(i)].width = w
    det.freeze_panes = "A2"
    det.auto_filter.ref = f"A1:K{len(linhas) + 1}"

    cp = wb.create_sheet("Comprovantes não lidos")
    cp.append(["Arquivo"])
    for a in nao_lidos:
        cp.append([a])
    cp.column_dimensions["A"].width = 80
    saida = RAIZ / "Relatorios" / "Avaliacao Fase 3.xlsx"
    wb.save(saida)
    for k, v in resumo:
        print(f"{k}: {v}")
    for row in ws.iter_rows(min_row=len(resumo) + 3, values_only=True):
        print(row)
    print(f"Relatório: {saida}")


if __name__ == "__main__":
    main()
