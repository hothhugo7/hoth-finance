import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.gravacao import PlanilhaEmUso, PlanilhaOcupada, _excel_data  # noqa: E402


def test_data_vira_numero_de_serie_do_excel_sem_fuso():
    assert _excel_data(dt.date(2026, 9, 30)) == 46295.0
    assert _excel_data(dt.datetime(2026, 9, 30, 12, 0)) == 46295.5
    assert _excel_data("texto") == "texto"


def test_backup_e_limite_de_versoes(tmp_path):
    planilha = tmp_path / "p.xlsx"
    planilha.write_bytes(b"x")
    pl = PlanilhaEmUso(planilha, tmp_path / "BKP", manter_backups=2)
    for i in range(4):
        (tmp_path / "BKP").mkdir(exist_ok=True)
        (tmp_path / "BKP" / f"2026-10-0{i + 1}_000000_antes_teste.xlsx").write_bytes(b"x")
    pl._limpar_backups()
    assert [b.name[:10] for b in pl.listar_backups()] == ["2026-10-04", "2026-10-03"]
    b = pl.backup("importação Cora/teste")
    assert b.exists() and "/" not in b.name and b.read_bytes() == b"x"


def test_planilha_aberta_bloqueia(tmp_path):
    planilha = tmp_path / "p.xlsx"
    planilha.write_bytes(b"x")
    (tmp_path / "~$p.xlsx").write_bytes(b"")
    with pytest.raises(PlanilhaOcupada):
        PlanilhaEmUso(planilha, tmp_path / "BKP").verificar_livre()
