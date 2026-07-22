"""Presigned URL SSRF gate (no GPU / network)."""

import os
import socket
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
_stub("requests")
_runpod = _stub("runpod")
_runpod.serverless = types.SimpleNamespace(start=lambda *a, **k: None)

os.environ.setdefault("R2_ENDPOINT_URL", "https://stub.r2")
os.environ.setdefault("R2_ACCESS_KEY_ID", "stub")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "stub")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handler  # noqa: E402


def _public_addrinfo(host, port, *a, **k):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]


def test_url_error_rejects_http_and_private(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))])
    assert handler._url_error("http://evil.example/x", "audio_url")
    assert "blocked" in handler._url_error("https://loop.example/x", "audio_url")


def test_url_error_accepts_public_https(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)
    assert handler._url_error("https://bucket.example/obj", "audio_url") is None


def test_presigned_rejects_bad_url_before_io(monkeypatch):
    called = {"get": 0}

    def boom(*a, **k):
        called["get"] += 1
        raise AssertionError("requests.get must not run for rejected URLs")

    monkeypatch.setattr(handler.requests, "get", boom, raising=False)
    out = handler.handler({
        "input": {
            "audio_url": "http://169.254.169.254/latest",
            "output_url": "https://bucket.example/o",
        },
    })
    assert out["ok"] is False and "error" in out
    assert called["get"] == 0
