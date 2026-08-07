#!/usr/bin/env python3
"""Homelab HTTP entry for speech audio-upscale on a LOCAL_FINISH_* URL (fc#1592 lane B).

Model residency: resemble-enhance's own `load_enhancer()` (enhancer/inference.py) is
`functools.cache`-decorated on (run_dir, device), and `handler.py` always calls it with
`run_dir=None` and a constant per-process `device`. Since this process stays up (unlike the
serverless worker, which is one job per cold start), the first request pays the checkpoint
load + GPU transfer and every later request in this process reuses the cached module -- no
code here needs its own cache; the residency comes from the library's decorator plus this
server's long-lived process. See CLAUDE.md for the measured proof.
"""
import os

from handler import handler
from runpod_http_serve import run_serve

if __name__ == "__main__":
    run_serve(
        handler,
        service="vivijure-audio-upscale-finish-speech-upscale",
        port=int(os.environ.get("PORT", "8013") or "8013"),
    )
