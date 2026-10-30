"""Aplica a senha de abertura (senha_planilha do hoth.json) na planilha em uso e nas versões do BKP.

    .venv\\Scripts\\python.exe scripts\\aplicar_senha.py

A planilha precisa estar fechada. A planilha passa pelo fluxo normal de gravação (backup antes, cópia temporária,
troca no fim) e fica registrada na Auditoria. As versões do BKP são regravadas com a mesma senha, sem mudar o
conteúdo. Depois disso, gravações e restaurações feitas pelo app mantêm a senha.
"""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.arquivo import protegida, senha  # noqa: E402
from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada, _abrir, _salvar, excel  # noqa: E402


def main():
    if not senha():
        print("ERRO: defina 'senha_planilha' no hoth.json antes.")
        sys.exit(1)
    cfg = config.carregar()
    pl = PlanilhaEmUso(cfg["planilha"], cfg["pasta_bkp"], cfg["manter_backups"])
    try:
        if not protegida(pl.caminho):
            pl._trocar(lambda wb, bkp: pl._auditar(wb, "Senha de abertura", "Planilha passou a exigir senha para abrir",
                                                   0, "", str(bkp)), "senha de abertura")
        print(f"Planilha protegida: {protegida(pl.caminho)}")
    except PlanilhaOcupada as e:
        print(f"ERRO: {e}")
        sys.exit(2)
    pendentes = [b for b in pl.listar_backups() if not protegida(b)]
    with excel() as app:
        for b in pendentes:
            wb = _abrir(app, b)
            _salvar(wb)
            wb.Close(False)
    restantes = [b.name for b in pl.listar_backups() if not protegida(b)]
    print(f"Versões do BKP protegidas agora: {len(pendentes) - len(restantes)} (sem senha: {len(restantes)})")


if __name__ == "__main__":
    main()
