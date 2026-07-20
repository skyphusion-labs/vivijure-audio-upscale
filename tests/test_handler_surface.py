"""Tests for build-time patches and handler surface."""

import ast
from pathlib import Path


def test_handler_parses():
    source = Path("handler.py").read_text(encoding="utf-8")
    ast.parse(source)


def test_numpy2_fsolve_patch_anchors_present():
    """Patch script must match upstream cfm.py line until PyPI ships a fixed wheel."""
    source = Path("scripts/patch_resemble_enhance_numpy2.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "scipy.optimize.fsolve" in source
    assert "x0=0)[0]" in source
