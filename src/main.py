"""Point d'entrée top-level (src/main.py).

Permet de lancer l'application depuis la racine du projet sans installation :
    PYTHONPATH=src python3 src/main.py
"""

from __future__ import annotations

from openrunner55.ui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
