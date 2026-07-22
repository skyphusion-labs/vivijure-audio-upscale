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

class _HTTPAdapter:
    def __init__(self, *a, **k):
        pass

    def init_poolmanager(self, *a, **k):
        return None


class _Session:
    def __init__(self):
        self.last = None

    def mount(self, prefix, adapter):
        pass

    def request(self, method, url, **k):
        self.last = (method, url, k)
        return types.SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            iter_content=lambda n: [b"x"],
            __enter__=lambda self: self,
            __exit__=lambda *a: None,
        )


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


def test_pinned_https_connects_to_resolved_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)
    sess = _Session()
    # raising=False: sibling modules may have stubbed requests without Session first.
    monkeypatch.setattr(handler.requests, "Session", lambda: sess, raising=False)
    handler._pinned_https("GET", "https://bucket.example/obj", timeout=1, stream=True)
    method, url, k = sess.last
    assert method == "GET"
    assert url.startswith("https://8.8.8.8/")
    assert k["headers"]["Host"] == "bucket.example"
    assert k["allow_redirects"] is False


def test_presigned_rejects_bad_url_before_io(monkeypatch):
    called = {"pin": 0}

    def boom(*a, **k):
        called["pin"] += 1
        raise AssertionError("_pinned_https must not run for rejected URLs")

    monkeypatch.setattr(handler, "_pinned_https", boom)
    out = handler.handler({
        "input": {
            "audio_url": "http://169.254.169.254/latest",
            "output_url": "https://bucket.example/o",
        },
    })
    assert out["ok"] is False and "error" in out
    assert called["pin"] == 0
