"""Abre o app Hoth (mesmo que `python -m hoth.web.servidor`, mas pode ser chamado de qualquer pasta)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoth.web.servidor import main  # noqa: E402

if __name__ == "__main__":
    main()
