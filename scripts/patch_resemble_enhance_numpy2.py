"""Patch resemble-enhance for NumPy 2.x scalar conversion (upstream cfm.py fsolve bug).

resemble-enhance 0.0.1 (PyPI) does:
    a = float(scipy.optimize.fsolve(...))
fsolve returns a 1-d ndarray; NumPy 2.x raises TypeError on float(ndarray_1d).
Upstream fix (resemble-ai/resemble-enhance#74): index [0] before float().

Run once at image build after `pip install --no-deps resemble-enhance`.
"""

from __future__ import annotations

import sys
from pathlib import Path

OLD = "a = float(scipy.optimize.fsolve(lambda a: h(1 / n, a) - 0.5, x0=0))"
NEW = "a = float(scipy.optimize.fsolve(lambda a: h(1 / n, a) - 0.5, x0=0)[0])"


def main() -> int:
    import resemble_enhance

    cfm = Path(resemble_enhance.__file__).resolve().parent / "enhancer" / "lcfm" / "cfm.py"
    if not cfm.is_file():
        print(f"patch_resemble_enhance_numpy2: missing {cfm}", file=sys.stderr)
        return 1

    text = cfm.read_text(encoding="utf-8")
    if NEW in text:
        print(f"patch_resemble_enhance_numpy2: already patched ({cfm})")
        return 0
    if OLD not in text:
        print(
            "patch_resemble_enhance_numpy2: fsolve anchor not found; "
            "resemble-enhance layout may have changed",
            file=sys.stderr,
        )
        return 1

    cfm.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    print(f"patch_resemble_enhance_numpy2: patched fsolve scalar in {cfm}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
