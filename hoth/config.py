"""Caminhos do Hoth. Valores padrão podem ser trocados em `hoth.json` na raiz do projeto."""
import json
import os
import sys
from pathlib import Path

# No pacote (PyInstaller) a raiz é a pasta do executável; no código-fonte, a pasta do projeto.
RAIZ = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

PADRAO = {
    "planilha": str(RAIZ / "Planilha" / "Hoth - Fechamento Financeiro Exemplo 2026.xlsx"),
    "pasta_bkp": str(RAIZ / "BKP"),
    "manter_backups": 60,
    "pasta_comprovantes": r"\\servidor\financeiro\FECHAMENTO FINANCEIRO\Comprovantes de pagamento Santander",
    "pasta_faturas": r"\\servidor\financeiro\Faturas",
}


def carregar() -> dict:
    """Padrão < `hoth.padrao.json` (vai no pacote: pasta e senha das faturas) < `hoth.json` (deste computador)."""
    cfg = dict(PADRAO)
    for arquivo in (RAIZ / "hoth.padrao.json", Path(os.environ.get("HOTH_CONFIG", RAIZ / "hoth.json"))):
        if arquivo.exists():   # HOTH_CONFIG: usado nos testes
            cfg.update(json.loads(arquivo.read_text(encoding="utf-8")))
    return cfg
