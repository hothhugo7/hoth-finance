"""Tira a senha de abertura da planilha em uso e das versões do BKP e limpa senha_planilha nos hoth.json.

    .venv\\Scripts\\python.exe scripts\\remover_senha.py

A planilha precisa estar fechada. Antes, a versão atual vai para o BKP (e também fica sem senha).
"""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from hoth import config  # noqa: E402
from hoth.arquivo import protegida, senha  # noqa: E402
from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada, _substituir, excel  # noqa: E402


def main():
    cfg = config.carregar()
    pl = PlanilhaEmUso(cfg["planilha"], cfg["pasta_bkp"], cfg["manter_backups"])
    pw = senha()
    try:
        pl.verificar_livre()
    except PlanilhaOcupada as e:
        print(f"ERRO: {e}")
        sys.exit(2)
    bkp = pl.backup("remocao da senha")
    tmp = pl.caminho.with_name(f"~hoth_gravando_{pl.caminho.name}")
    alvos = [b for b in pl.listar_backups() if protegida(b)]
    with excel() as app:
        if protegida(pl.caminho):
            import shutil
            shutil.copy2(pl.caminho, tmp)
            wb = app.Workbooks.Open(Filename=str(tmp), Password=pw)
            wb.Password = ""
            pl._auditar(wb, "Senha removida", "Planilha deixou de exigir senha para abrir", 0, "", str(bkp))
            wb.Save()
            wb.Close(False)
        for b in alvos:
            wb = app.Workbooks.Open(Filename=str(b), Password=pw)
            wb.Password = ""
            wb.Save()
            wb.Close(False)
    if tmp.exists():
        _substituir(tmp, pl.caminho)

    arquivos = ([Path(os.environ["HOTH_CONFIG"])] if os.environ.get("HOTH_CONFIG")
                else [RAIZ / "hoth.json", RAIZ / "Pacote" / "Hoth Solutions" / "hoth.json"])
    for a in arquivos:
        if a.exists():
            d = json.loads(a.read_text(encoding="utf-8"))
            d.pop("senha_planilha", None)
            a.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    sem = [b.name for b in pl.listar_backups() if protegida(b)]
    print(f"Planilha com senha: {protegida(pl.caminho)} | versões ainda com senha: {len(sem)}")


if __name__ == "__main__":
    main()
