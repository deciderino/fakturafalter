# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Fakturafalter-Mitwirkende
"""Einstieg für die gebündelten Programme (PyInstaller): ruft fakturafalter.cli.main auf."""
import os
import sys

# Windows-Fensterprogramm (console=False): kein stdout/stderr -> Ausgaben verwerfen statt abstürzen
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from fakturafalter.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
