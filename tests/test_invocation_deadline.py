"""Per-invocation wall-clock guard (core#223). No GPU / network.

A test that only asserts a fast job still succeeds passes identically with and without the
guard, so it cannot see this change. The tests that CAN see it are the ones where the guard
FIRES, where it is asked NOT to fire, and where a subprocess is actually bounded.
"""

import ast
import os
import sys
import time
import types
from pathlib import Path

import pytest


def _stub(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


_stub("torch", cuda=types.SimpleNamespace(is_available=lambda: False), __version__="0-stub")
_stub("torchaudio")
_stub("boto3", client=lambda *a, **k: None)


class _HTTPAdapter:
    def __init__(self, *a, **k):
        pass

    def init_poolmanager(self, *a, **k):
        return None


class _Session:
    def mount(self, *a, **k):
        pass

    def request(self, *a, **k):
        raise AssertionError("network must not run in deadline tests")


_adapters = types.ModuleType("requests.adapters")
_adapters.HTTPAdapter = _HTTPAdapter
sys.modules["requests.adapters"] = _adapters
_requests = _stub("requests", Session=_Session)
_requests.adapters = _adapters
_runpod = _stub("runpod")
_runpod.serverless = types.SimpleNamespace(start=lambda *a, **k: None)

os.environ.setdefault("R2_ENDPOINT_URL", "https://stub.r2")
os.environ.setdefault("R2_ACCESS_KEY_ID", "stub")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "stub")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handler  # noqa: E402

# Another test module may have imported handler first without R2 env; the name is bound at import.
if not handler.R2_ENDPOINT:
    handler.R2_ENDPOINT = "https://stub.r2"

REFERENCE_EXECUTION_TIMEOUT_S = 600   # deploy.sh EXECUTION_TIMEOUT_MS default 600000
PHASE_HARD_DEADLINE_S = 5400          # vivijure-core PHASE_HARD_DEADLINE_SECONDS
FINISH_STEP_MAX_ATTEMPTS = 3
RUNPOD_COLD_GRACE_S = 900             # speech-upscale RUNPOD_COLD_GRACE_MS

R2_JOB = {"project": "neon", "audio_key": "renders/neon/dialogue/s.wav"}
PRESIGNED_JOB = {
    "audio_url": "https://bucket.example/in.wav",
    "output_url": "https://bucket.example/out.wav",
    "output_key": "renders/neon/dialogue/s_enh.wav",
}


class _FakeS3:
    def download_file(self, _bucket, _key, dst):
        open(dst, "wb").write(b"in")

    def upload_file(self, *_a, **_k):
        pass


def _enhance_ok(src, dst, **_k):
    open(dst, "wb").write(b"out")
    return 44100


def _handler_source():
    return Path("handler.py").read_text(encoding="utf-8")


def test_source_refuses_non_positive_budget_at_import():
    src = _handler_source()
    assert "MAX_INVOCATION_SECONDS <= 0" in src
    assert 'raise ValueError("MAX_INVOCATION_SECONDS must be a positive number of seconds")' in src


def test_exactly_one_subprocess_run_site_and_it_is_guarded():
    tree = ast.parse(_handler_source())
    sites = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
             and isinstance(n.func.value, ast.Name) and n.func.value.id == "subprocess"]
    assert len(sites) == 1, (
        f"expected exactly 1 subprocess.run site (all compute goes through _run_guarded), "
        f"found {len(sites)}")
    kwargs = [k.arg for k in sites[0].keywords]
    assert "timeout" in kwargs, f"the single subprocess.run site must carry timeout=, got {kwargs}"


def test_selftest_ffmpeg_goes_through_the_guard():
    tree = ast.parse(_handler_source())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == "_run_guarded"]
    assert len(calls) == 1, f"expected 1 guarded subprocess site (ffmpeg-gen), found {len(calls)}"


def test_default_budget_fits_under_the_platform_kill_and_the_phase_ceiling():
    g = handler.MAX_INVOCATION_SECONDS
    assert g < REFERENCE_EXECUTION_TIMEOUT_S, (
        f"a guard at or above the reference deployment execution timeout "
        f"({REFERENCE_EXECUTION_TIMEOUT_S}s) can never fire: the platform kills the worker first. "
        f"Got {g}s.")
    worst = FINISH_STEP_MAX_ATTEMPTS * g + RUNPOD_COLD_GRACE_S + FINISH_STEP_MAX_ATTEMPTS * 60
    assert worst < PHASE_HARD_DEADLINE_S, (
        f"worst case {FINISH_STEP_MAX_ATTEMPTS} * {g}s plus cold start plus queue wait = {worst}s, "
        f"which must stay under the {PHASE_HARD_DEADLINE_S}s phase ceiling.")


def test_deadline_reason_names_the_guard_and_the_elapsed_seconds():
    dl = handler._Deadline()
    reason = dl.reason("enhance")
    assert "MAX_INVOCATION_SECONDS" in reason
    assert "enhance" in reason
    assert "after" in reason
    assert len(reason) <= 120, f"reason is {len(reason)} chars and would be truncated: {reason}"


def test_check_passes_while_budget_remains_and_raises_once_it_is_spent(monkeypatch):
    clock = {"t": 100.0}
    monkeypatch.setattr(handler, "time", types.SimpleNamespace(monotonic=lambda: clock["t"]))
    dl = handler._Deadline(seconds=60)
    dl.check("enhance")
    clock["t"] += 59.0
    dl.check("enhance")
    clock["t"] += 2.0
    with pytest.raises(handler.SoftDegrade):
        dl.check("enhance")


def test_run_guarded_kills_a_child_that_outlives_the_budget():
    t0 = time.monotonic()
    with pytest.raises(handler.SoftDegrade) as exc:
        handler._run_guarded(["sleep", "30"], handler._Deadline(seconds=1), "sleep")
    elapsed = time.monotonic() - t0
    assert elapsed < 5, f"child was not bounded; took {elapsed:.1f}s"
    assert "MAX_INVOCATION_SECONDS" in str(exc.value)
    assert "sleep" in str(exc.value)


def test_run_guarded_converts_timeout_expired(monkeypatch):
    def _timeout(cmd, *a, **k):
        raise handler.subprocess.TimeoutExpired(cmd, k.get("timeout", 1))

    monkeypatch.setattr(handler.subprocess, "run", _timeout)
    with pytest.raises(handler.SoftDegrade) as exc:
        handler._run_guarded(["ffmpeg"], handler._Deadline(seconds=600), "ffmpeg-gen")
    assert "ffmpeg-gen" in str(exc.value)


def _guard_expiry(*_a, **_k):
    raise handler.SoftDegrade(handler._Deadline().reason("enhance"))


def test_guard_fires_inside_r2_after_a_slow_download(monkeypatch):
    clock = {"t": 5000.0}
    monkeypatch.setattr(handler, "time", types.SimpleNamespace(monotonic=lambda: clock["t"]))

    class _SlowS3:
        def download_file(self, _bucket, _key, dst):
            open(dst, "wb").write(b"in")
            clock["t"] += 10000.0

        def upload_file(self, *_a, **_k):
            raise AssertionError("must not upload after expiry")

    monkeypatch.setattr(handler, "_r2", lambda: _SlowS3())
    monkeypatch.setattr(handler, "_enhance_file", _enhance_ok)
    out = handler._upscale_r2(dict(R2_JOB))
    assert out["ok"] is False
    assert "error" in out and "detail" not in out
    assert "applied" not in out
    assert "MAX_INVOCATION_SECONDS" in out["error"]
    assert "enhance" in out["error"]
    assert "after 10000.0s" in out["error"]


def test_expiry_reaches_the_r2_door_as_error(monkeypatch):
    monkeypatch.setattr(handler, "_r2", lambda: _FakeS3())
    monkeypatch.setattr(handler, "_enhance_file", _guard_expiry)
    out = handler._upscale_r2(dict(R2_JOB))
    assert out["ok"] is False
    assert "error" in out and "detail" not in out
    assert "applied" not in out
    assert "MAX_INVOCATION_SECONDS" in out["error"]
    assert len(out["error"]) <= 120


class _FakeResp:
    def raise_for_status(self):
        pass

    def iter_content(self, _n):
        return [b"audio"]

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


def test_expiry_reaches_the_presigned_door_as_error(monkeypatch):
    monkeypatch.setattr(handler, "_url_error", lambda *_a, **_k: None)
    monkeypatch.setattr(handler, "_pinned_https", lambda *_a, **_k: _FakeResp())
    monkeypatch.setattr(handler, "_enhance_file", _guard_expiry)
    out = handler.handler({"input": dict(PRESIGNED_JOB)})
    assert out["ok"] is False
    assert "error" in out and "detail" not in out
    assert "applied" not in out
    assert "MAX_INVOCATION_SECONDS" in out["error"]


def test_expiry_never_escapes_the_door_as_an_exception(monkeypatch):
    monkeypatch.setattr(handler, "_r2", lambda: _FakeS3())
    monkeypatch.setattr(handler, "_url_error", lambda *_a, **_k: None)
    monkeypatch.setattr(handler, "_pinned_https", lambda *_a, **_k: _FakeResp())
    monkeypatch.setattr(handler, "_enhance_file", _guard_expiry)
    assert isinstance(handler.handler({"input": dict(R2_JOB)}), dict)
    assert isinstance(handler.handler({"input": dict(PRESIGNED_JOB)}), dict)


def test_a_normal_job_does_not_trip_the_guard(monkeypatch):
    monkeypatch.setattr(handler, "_r2", lambda: _FakeS3())
    monkeypatch.setattr(handler, "_enhance_file", _enhance_ok)
    out = handler._upscale_r2(dict(R2_JOB))
    assert out["ok"] is True
    assert out["applied"] == ["speech-upscale:resemble-enhance"]
    assert "error" not in out
