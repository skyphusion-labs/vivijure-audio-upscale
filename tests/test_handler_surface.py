"""CPU-only surface tests (no GPU deps)."""

import ast
from pathlib import Path


def test_handler_parses():
    source = Path("handler.py").read_text(encoding="utf-8")
    ast.parse(source)
