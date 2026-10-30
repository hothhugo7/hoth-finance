"""Importa extratos para a planilha em uso.

    importar.py previa "C:\\caminho\\extrato.xlsx|.ofx"
        Gera Relatorios\\Previa importacao.xlsx. Abra, confira a coluna "Conta (confirme ou corrija)" e salve.
    importar.py gravar [--previa CAMINHO]
        Grava a prévia revisada na planilha em uso. Antes, a versão atual vai para o BKP.
    importar.py backups
        Lista as versões guardadas no BKP.
    importar.py restaurar "ARQUIVO DO BKP"
        Volta a planilha para aquela versão (a atual também vai para o BKP antes).
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada  # noqa: E402
from hoth.importacao import importar, previa, salvar_previa  # noqa: E402

PREVIA = RAIZ / "Relatorios" / "Previa importacao.xlsx"


def planilha_em_uso() -> PlanilhaEmUso:
    cfg = config.carregar()
    return PlanilhaEmUso(cfg["planilha"], cfg["pasta_bkp"], cfg["manter_backups"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("previa")
    s.add_argument("extrato")
    s.add_argument("--saida", default=str(PREVIA))
    s = sub.add_parser("gravar")
    s.add_argument("--previa", default=str(PREVIA))
    sub.add_parser("backups")
    s = sub.add_parser("restaurar")
    s.add_argument("arquivo")
    a = ap.parse_args()
    cfg = config.carregar()
    pl = planilha_em_uso()
    try:
        if a.cmd == "previa":
            p = previa(a.extrato, pl.caminho, cfg["pasta_comprovantes"])
            salvar_previa(p, a.saida, pl.contas())
            auto = sum(1 for l in p["novos"] if l["proposta"])
            print(f"{p['banco']}: {p['lidos']} lidos, {p['ja_existem']} já estão na planilha, {len(p['novos'])} novos "
                  f"({auto} com conta proposta, {len(p['novos']) - auto} para revisar)")
            print("Regras:", dict(Counter(l["regra"] or "pendente" for l in p["novos"])))
            for sd in p["saldos"]:
                print(f"Saldo do extrato: {sd['banco']} início de {sd['mes']:02d}/{sd['ano']} = {sd['saldo']:.2f}")
            if p["comprovantes_nao_lidos"]:
                print("Comprovantes não lidos:", "; ".join(p["comprovantes_nao_lidos"]))
            print(f"Revise e salve: {a.saida}")
            if os.environ.get("HOTH_ABRIR", "1") == "1" and sys.platform == "win32":
                os.startfile(a.saida)
        elif a.cmd == "gravar":
            info = importar(a.previa, pl, cfg["pasta_comprovantes"])
            print(info["detalhe"])
            if info["duplicados_ignorados"]:
                print(f"{info['duplicados_ignorados']} já estavam na planilha e foram ignorados")
            for m in info["saldos"]:
                print("Saldo:", m)
            if info["backup"]:
                print(f"Versão anterior guardada em: {info['backup']}")
        elif a.cmd == "backups":
            for b in pl.listar_backups():
                print(b.name)
        elif a.cmd == "restaurar":
            arq = Path(a.arquivo)
            if not arq.is_absolute():
                arq = pl.pasta_bkp / arq
            bkp = pl.restaurar(arq)
            print(f"Planilha restaurada para {arq.name}. A versão que estava em uso foi guardada em {bkp.name}")
    except PlanilhaOcupada as e:
        print(f"ERRO: {e}")
        sys.exit(2)
    except (ValueError, FileNotFoundError) as e:
        print(f"ERRO: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
