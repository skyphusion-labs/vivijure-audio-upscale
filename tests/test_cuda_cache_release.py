"""Behavioural coverage for the VRAM release in `_enhance_file` (fc#1592).

This repo had no torch stubs and its only handler test was an AST parse, so the shipped GPU path
was untested. An AST or grep assertion would prove a STRING is present, not that the call happens
on the paths that matter -- and the path that matters most is the one where the job RAISES.

Stub pattern copied from `vivijure-upscale/tests/test_sidecar.py`, which already proves it works
in-estate: the heavy deps import at module load, so they are stubbed before `import handler`.
"""

import sys
import types

import pytest


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


CALLS = []


class _FakeCuda:
    available = True

    @staticmethod
    def is_available():
        return _FakeCuda.available

    @staticmethod
    def empty_cache():
        CALLS.append("empty_cache")

    @staticmethod
    def get_device_name(_i):
        return "stub-gpu"


_stub("torch", __version__="0-stub", cuda=_FakeCuda)


class _FakeWav:
    def mean(self, **_k):
        return self

    def unsqueeze(self, _d):
        return self

    def cpu(self):
        return self


def _load(_src):
    CALLS.append("load")
    return _FakeWav(), 16000


def _save(_dst, _wav, _sr):
    CALLS.append("save")


_stub("torchaudio", load=_load, save=_save)
_stub("boto3", client=lambda *a, **k: None)
_stub("requests")
_runpod = _stub("runpod")
_runpod.serverless = types.SimpleNamespace(start=lambda *a, **k: None)

# resemble_enhance is imported INSIDE _enhance_file, so the stub must satisfy that deferred import.
_pkg = _stub("resemble_enhance")
_enh = _stub("resemble_enhance.enhancer")
_inf = _stub("resemble_enhance.enhancer.inference")
_pkg.enhancer = _enh
_enh.inference = _inf


def _enhance_ok(dwav, _sr, _device, **_k):
    CALLS.append("enhance")
    return dwav, 44100


def _denoise_ok(dwav, sr, _device):
    CALLS.append("denoise")
    return dwav, sr


_inf.enhance = _enhance_ok
_inf.denoise = _denoise_ok

import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import handler  # noqa: E402


@pytest.fixture(autouse=True)
def _reset():
    CALLS.clear()
    _FakeCuda.available = True
    _inf.enhance = _enhance_ok
    yield


def test_cache_is_released_after_a_successful_enhance():
    sr = handler._enhance_file("in.wav", "out.wav")
    assert sr == 44100
    assert "empty_cache" in CALLS, CALLS


def test_the_release_happens_AFTER_the_output_is_written():
    """Order, not just presence. Releasing before the output is saved would be a different change
    with a different risk, and 'empty_cache was called' cannot tell the two apart."""
    handler._enhance_file("in.wav", "out.wav")
    assert CALLS.index("save") < CALLS.index("empty_cache"), CALLS


def test_cache_is_released_even_when_the_enhance_RAISES():
    """The path that matters most, and the one a trailing-line implementation silently fails.

    An exception mid-job would otherwise keep the WHOLE job's cache for the life of the resident
    process -- the exact defect this change removes, surviving on the error path.
    """
    def _boom(*_a, **_k):
        CALLS.append("enhance")
        raise RuntimeError("CUDA OOM, say")

    _inf.enhance = _boom
    with pytest.raises(RuntimeError):
        handler._enhance_file("in.wav", "out.wav")
    assert "empty_cache" in CALLS, CALLS


def test_no_release_attempted_when_cuda_is_unavailable():
    """The guard is real: on a CPU-only box `empty_cache()` is meaningless, and calling it anyway
    would be a lie about what the code checked."""
    _FakeCuda.available = False
    handler._enhance_file("in.wav", "out.wav")
    assert "empty_cache" not in CALLS, CALLS


def test_the_stub_can_observe_a_missing_release():
    """POSITIVE CONTROL for the harness itself: with the helper neutered, the assertions above
    MUST be able to fail. Without this, a broken recorder would make every test above vacuous."""
    original = handler._release_cuda_cache
    try:
        handler._release_cuda_cache = lambda: None
        handler._enhance_file("in.wav", "out.wav")
        assert "empty_cache" not in CALLS, "recorder is broken: it logged a call that never happened"
    finally:
        handler._release_cuda_cache = original
