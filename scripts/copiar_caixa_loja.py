"""Piloto: copia os lançamentos da Caixa Loja de um mês da planilha antiga para a planilha Hoth.

    .venv\\Scripts\\python.exe scripts\\copiar_caixa_loja.py --mes 10 [--origem CAMINHO_DA_ANTIGA]

Enquanto as duas planilhas correm em paralelo, a Caixa Loja continua sendo digitada só na antiga.
Só entra o que ainda não está na Hoth (mesmo ID da migração), com backup antes. A planilha Hoth precisa
estar fechada.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.fechamento_antigo import LeitorFechamento  # noqa: E402
from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada  # noqa: E402

ORIGEM_PADRAO = r"\\servidor\financeiro\FECHAMENTO FINANCEIRO\2026\01. FECHAMENTO FINANCEIRO EXEMPLO - 2026.xlsx"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--origem", default=ORIGEM_PADRAO)
    a = ap.parse_args()
    cfg = config.carregar()
    pl = PlanilhaEmUso(cfg["planilha"], cfg["pasta_bkp"], cfg["manter_backups"])
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "antiga.xlsx"
        shutil.copy2(a.origem, copia)
        antiga = LeitorFechamento(str(copia)).ler()
    existentes = pl.ids_existentes()
    novos = [dict(l, origem="Caixa Loja copiada da planilha antiga (piloto)", referencia=l["referencia"])
             for l in antiga.lancamentos
             if l["banco"] == "Caixa Loja" and l["data"].month == a.mes and l["id"] not in existentes]
    if not novos:
        print("Nada novo: a Caixa Loja desse mês já está toda na planilha Hoth.")
        return
    try:
        info = pl.gravar_lancamentos(novos, acao="Cópia Caixa Loja (piloto)",
                                     detalhe=f"{len(novos)} lançamentos da Caixa Loja de {a.mes:02d} copiados da planilha antiga",
                                     arquivo=a.origem)
    except PlanilhaOcupada as e:
        print(f"ERRO: {e}")
        sys.exit(2)
    print(f"{info['gravados']} lançamentos copiados. Versão anterior: {info['backup']}")


if __name__ == "__main__":
    main()
