"""Refaz a planilha em uso com o visual atual do gerador, preservando todos os dados.

Lê a planilha (lançamentos, ajustes, orçamento, saldos, DRE Manual, plano, auditoria), gera de novo as abas,
aplica o acabamento no Excel e troca o arquivo. A versão anterior vai para o BKP. A planilha precisa estar fechada.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth import config  # noqa: E402
from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada  # noqa: E402
from hoth.planilha_atual import ler  # noqa: E402


def main():
    cfg = config.carregar()
    pl = PlanilhaEmUso(cfg["planilha"], cfg["pasta_bkp"], cfg["manter_backups"])
    try:
        cont = ler(pl.caminho)
        bkp = pl.reconstruir(cont, "Atualização do visual", "Capa, DFC, DRE, RESUMO e Faturamento com o visual novo; "
                                                            "dados preservados", motivo="atualizacao do visual")
    except PlanilhaOcupada as e:
        print(f"ERRO: {e}")
        sys.exit(2)
    print(f"Planilha atualizada: {len(cont.lancamentos)} lançamentos preservados. Versão anterior: {bkp}")


if __name__ == "__main__":
    main()
