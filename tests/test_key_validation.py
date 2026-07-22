"""Project-scoped R2 key gate (no GPU / network).

Shared-bucket R2 mode must refuse cross-project keys. Heavy deps are stubbed so the
routing under test is pure control flow.
"""

import os
import sys
import types


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
        raise AssertionError("network must not run in key-validation tests")


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


def test_key_error_rejects_traversal():
    assert handler._key_error("", "audio_key")
    assert handler._key_error("/renders/p/x", "audio_key")
    assert handler._key_error("renders/../x", "audio_key")
    assert handler._key_error("projects/p/x", "audio_key")


def test_scoped_rejects_missing_project():
    err = handler._scoped_key_error("renders/neon/dialogue/s.wav", "audio_key", project="")
    assert err and "project is required" in err


def test_scoped_rejects_cross_project():
    err = handler._scoped_key_error(
        "renders/victim/dialogue/s.wav", "audio_key", project="attacker")
    assert err and "must be under renders/attacker/" in err


def test_scoped_accepts_matching_project():
    assert handler._scoped_key_error(
        "renders/neon/dialogue/s.wav", "audio_key", project="neon") is None


def test_scoped_rejects_flat_audio_prefix():
    err = handler._scoped_key_error(
        "audio/uuid.wav", "audio_key", project="neon")
    assert err and "must be under audio/neon/" in err


def test_scoped_accepts_project_scoped_audio_prefix():
    assert handler._scoped_key_error(
        "audio/neon/uuid.wav", "audio_key", project="neon") is None


def test_upscale_r2_refuses_cross_project_before_io(monkeypatch):
    class Boom:
        def download_file(self, *a, **k):
            raise AssertionError("must not touch R2 for rejected keys")

        def upload_file(self, *a, **k):
            raise AssertionError("must not touch R2 for rejected keys")

    monkeypatch.setattr(handler, "_r2", lambda: Boom())
    out = handler._upscale_r2({
        "project": "attacker",
        "audio_key": "renders/victim/dialogue/s.wav",
    })
    assert out["ok"] is False
    assert "must be under renders/attacker/" in out["error"]


def test_upscale_r2_refuses_missing_project(monkeypatch):
    monkeypatch.setattr(handler, "_r2", lambda: None)
    out = handler._upscale_r2({"audio_key": "renders/neon/dialogue/s.wav"})
    assert out["ok"] is False
    assert "project is required" in out["error"]
