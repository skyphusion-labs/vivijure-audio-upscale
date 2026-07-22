"""RunPod serverless handler -- speech audio-upscale (CUDA) for Vivijure's audio finish path.

Cleans + restores + bandwidth-extends SPEECH with resemble-enhance (denoise -> enhance). Runs on the
per-shot dialogue track BEFORE MuseTalk, so the lips sync to the cleaned audio. Thin/auto-generated
TTS (Aura-1) comes out full and natural. Speech only -- music goes through the CPU audio-mix path.

The transport contract + the {"selftest": true} GPU harness mirror vivijure-upscale exactly, so the
studio router dispatches both the same way.

Job input (one of three modes):
  R2 mode (finish-chain module contract -- the endpoint reads/writes the shared bucket itself):
    { "project": "<project>", "audio_key": "renders/<project>/dialogue/<shot>.wav",
      "output_key"?: "...", "denoise"?: true,
      "nfe"?: 64, "solver"?: "midpoint", "lambd"?: 0.9, "tau"?: 0.5 }
    `project` is required and scopes every renders/ key to renders/<project>/ (shared-bucket tenancy).
  Presigned mode (credentialless -- the caller presigns R2):
    { "audio_url": "<presigned GET>", "output_url": "<presigned PUT>", "output_key"?: "..." }
  Self-test (no R2 -- confirms CUDA + loads the model + enhances a generated clip end to end):
    { "selftest": true }

Returns: { ok, output_key, bytes, sr, applied: ["speech-upscale:resemble-enhance"] } on success;
         { ok: false, error } on failure. The handler SURFACES failure (returns ok:false) -- it never
         swallows it or silently passes the original through (cf. the #249 silent-degrade bug). The
         `applied` tag is set ONLY on success. The orchestrator/router owns any soft-degrade policy.
"""

import ipaddress
import os
import shutil
import socket
import subprocess
import tempfile
from urllib.parse import urlparse, urlunparse

import boto3
import requests
import runpod
import torch
import torchaudio

# resemble-enhance loads its checkpoints from a path inside the installed package; the image bakes
# them there at build (see Dockerfile), so enhance()/denoise() never fetch at runtime.
DOWNLOAD_TIMEOUT = 900
UPLOAD_TIMEOUT = 900

# Optional pin for presigned hosts (e.g. ".r2.cloudflarestorage.com"). Empty = skip host-suffix check.
R2_URL_HOST_SUFFIX = os.environ.get("R2_URL_HOST_SUFFIX", "").strip().lower()


def _ip_blocked(ip):
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _resolve_public_ips(host):
    """Resolve host; return public IPs or raise ValueError with a job-facing message."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"URL host does not resolve: {e}") from e
    public, blocked = [], False
    for _fam, _type, _proto, _canon, sockaddr in infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if _ip_blocked(ip):
            blocked = True
        else:
            public.append(str(ip))
    if blocked or not public:
        raise ValueError("URL resolves to a blocked address")
    return public


def _url_error(url, what):
    """Refuse non-https / private / link-local / loopback / optional non-R2 host. Returns err str or None.

    Presigned mode otherwise lets any job submitter drive GET/PUT from the GPU worker (SSRF). Resolve
    the hostname and reject blocked address classes; callers must also pass allow_redirects=False and
    connect to a pre-validated IP (see _pinned_https) so DNS cannot rebind between check and fetch."""
    try:
        p = urlparse(str(url or ""))
    except Exception:  # noqa: BLE001 -- malformed URL is a job error, not a crash
        return f"{what}: malformed URL"
    if p.scheme != "https" or not p.hostname:
        return f"{what}: URL must be https with a hostname"
    host = p.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        return f"{what}: URL host is blocked"
    if R2_URL_HOST_SUFFIX:
        suffix = R2_URL_HOST_SUFFIX if R2_URL_HOST_SUFFIX.startswith(".") else f".{R2_URL_HOST_SUFFIX}"
        bare = suffix.lstrip(".")
        if host != bare and not host.endswith(suffix):
            return f"{what}: URL host must end with {R2_URL_HOST_SUFFIX}"
    try:
        _resolve_public_ips(host)
    except ValueError as e:
        return f"{what}: {e}"
    return None


def _pinned_https(method, url, *, timeout, headers=None, data=None, stream=False):
    """HTTPS GET/PUT that resolves once, rejects private addrs, and connects to that IP (DNS-rebinding safe)."""
    from requests.adapters import HTTPAdapter  # deferred: keeps CPU test stubs light

    class _SniAdapter(HTTPAdapter):
        """Keep TLS SNI / hostname verify on the original host while connecting to a pinned IP."""

        def __init__(self, server_hostname, **kwargs):
            self._server_hostname = server_hostname
            super().__init__(**kwargs)

        def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
            pool_kwargs["assert_hostname"] = self._server_hostname
            pool_kwargs["server_hostname"] = self._server_hostname
            return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    p = urlparse(str(url or ""))
    if p.scheme != "https" or not p.hostname:
        raise ValueError("URL must be https with a hostname")
    host = p.hostname.lower()
    ip = _resolve_public_ips(host)[0]
    netloc_host = f"[{ip}]" if ":" in ip else ip
    netloc = f"{netloc_host}:{p.port}" if p.port else netloc_host
    pinned = urlunparse((p.scheme, netloc, p.path or "/", p.params, p.query, ""))
    hdrs = dict(headers or {})
    hdrs["Host"] = host if not p.port else f"{host}:{p.port}"
    session = requests.Session()
    session.mount("https://", _SniAdapter(host))
    return session.request(method, pinned, timeout=timeout, headers=hdrs, data=data,
                           stream=stream, allow_redirects=False)

# resemble-enhance defaults (overridable per job): nfe = diffusion steps, lambd = denoise strength,
# tau = prior temperature, solver = ODE solver. The package's documented inference knobs.
DEFAULTS = {"nfe": 64, "solver": "midpoint", "lambd": 0.9, "tau": 0.5}


def _device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def _enhance_file(src, dst, *, denoise_first=False, **knobs):
    """Load src (any torchaudio-readable audio), run resemble-enhance, write dst as 44.1k wav.
    Returns the output sample rate. Heavy import is deferred so the module stays import-light."""
    from resemble_enhance.enhancer.inference import denoise, enhance  # deferred

    dwav, sr = torchaudio.load(src)
    dwav = dwav.mean(dim=0)  # mix to mono 1-D, what resemble-enhance expects
    device = _device()
    if denoise_first:
        dwav, sr = denoise(dwav, sr, device)
    k = {**DEFAULTS, **{n: knobs[n] for n in DEFAULTS if knobs.get(n) is not None}}
    wav, out_sr = enhance(dwav, sr, device, nfe=int(k["nfe"]), solver=str(k["solver"]),
                          lambd=float(k["lambd"]), tau=float(k["tau"]))
    torchaudio.save(dst, wav.unsqueeze(0).cpu(), out_sr)
    return out_sr


def _selftest(inp):
    """Self-contained GPU verification -- NO R2. Confirms CUDA, loads the model, generates a tiny noisy
    speech-band clip and actually enhances it end to end. Doubles as a health check."""
    out = {"ok": False, "selftest": True, "torch_version": torch.__version__,
           "cuda_available": torch.cuda.is_available()}
    work = tempfile.mkdtemp(prefix="selftest-")
    src, dst = os.path.join(work, "in.wav"), os.path.join(work, "out.wav")
    try:
        if torch.cuda.is_available():
            out["gpu"] = torch.cuda.get_device_name(0)
        # A 1s 16k mono tone + noise stands in for a thin TTS clip (we only prove the pipe runs).
        gen = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
             "-i", "sine=frequency=220:duration=1:sample_rate=16000",
             "-f", "lavfi", "-i", "anoisesrc=d=1:c=pink:r=16000:a=0.1",
             "-filter_complex", "[0:a][1:a]amix=inputs=2", "-ac", "1", "-ar", "16000", src],
            capture_output=True, text=True)
        if gen.returncode != 0:
            out["error"] = f"ffmpeg gen failed: {(gen.stderr or '')[-500:]}"
            return out
        out["input_sr"] = 16000
        out["sr"] = _enhance_file(src, dst, denoise_first=bool(inp.get("denoise")))
        if not os.path.exists(dst) or os.path.getsize(dst) == 0:
            out["error"] = "no output produced"
            return out
        out["output_bytes"] = os.path.getsize(dst)
        out["applied"] = ["speech-upscale:resemble-enhance"]
        out["ok"] = True
        return out
    except Exception as e:  # noqa: BLE001 -- a job error is data, returned to the caller
        out["error"] = str(e)[:800]
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --- R2 mode (the finish-chain module contract) -------------------------------------------------
R2_ENDPOINT = os.environ.get("R2_ENDPOINT_URL", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "vivijure")


def _r2():
    return boto3.client(
        "s3", endpoint_url=R2_ENDPOINT, region_name="auto",
        aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY", ""),
    )


def _enhanced_key(audio_key, output_key):
    if output_key:
        return output_key
    name = audio_key.rsplit("/", 1)[-1]
    return (f"{audio_key.rsplit('.', 1)[0]}_enh.wav" if "." in name else f"{audio_key}_enh.wav")


def _key_error(key, what, prefixes=("renders/",)):
    """Validate a job-supplied R2 key against the render key map BEFORE any bucket I/O. Every key
    this module reads or writes lives inside the studio's render tree (see the module docstring),
    so an absolute key, a `..` segment, a backslash, or an out-of-prefix key is a malformed job.
    Refused as data (this handler reports errors, it does not raise): returns the error string,
    or None when the key is fine."""
    k = str(key or "")
    ok = (bool(k) and k == k.strip() and not k.startswith("/") and "\\" not in k
          and ".." not in k.split("/") and k.startswith(tuple(prefixes)))
    return None if ok else f"{what}: R2 key {k!r} must be a plain relative key under {' or '.join(prefixes)}"


def _project_prefix(project):
    """Trusted project segment for shared-bucket tenancy. Mirrors studio dialogue keys
    (`renders/${project}/...`) -- reject slash/backslash/whitespace so the field cannot widen the prefix."""
    raw = str(project or "")
    p = raw.strip()
    if not p or p != raw or "/" in p or "\\" in p or any(c.isspace() for c in p):
        return None
    return f"renders/{p}/"


def _scoped_key_error(key, what, *, project, prefixes=("renders/", "audio/")):
    """Prefix-check plus project tenancy. renders/ and audio/ keys must both sit under
    renders/<project>/ or audio/<project>/ (no flat audio/ exemption -- that was a cross-tenant read)."""
    err = _key_error(key, what, prefixes=prefixes)
    if err:
        return err
    pref = _project_prefix(project)
    if not pref:
        return f"{what}: project is required for R2 mode"
    p = pref[len("renders/"):].rstrip("/")  # validated project segment
    k = str(key)
    if k.startswith("audio/"):
        audio_pref = f"audio/{p}/"
        if not k.startswith(audio_pref):
            return f"{what}: R2 key must be under {audio_pref}"
        return None
    if not k.startswith(pref):
        return f"{what}: R2 key must be under {pref}"
    return None


def _upscale_r2(inp):
    """R2 mode: download audio_key, enhance, upload output_key in the shared bucket; return the new key."""
    audio_key = inp.get("audio_key")
    project = inp.get("project")
    # dialogue tracks live under renders/; a staged bed lives under audio/ -- both are in-map
    err = _scoped_key_error(audio_key, "audio_key", project=project)
    if err:
        return {"ok": False, "error": err}
    output_key = _enhanced_key(audio_key, inp.get("output_key"))
    err = _scoped_key_error(output_key, "output_key", project=project)
    if err:
        return {"ok": False, "error": err}
    if not (R2_ENDPOINT and os.environ.get("R2_ACCESS_KEY_ID")):
        return {"ok": False, "error": "R2 mode needs R2_ENDPOINT_URL + R2_ACCESS_KEY_ID/SECRET in the endpoint env"}
    work = tempfile.mkdtemp(prefix="enh-")
    src, dst = os.path.join(work, "in.wav"), os.path.join(work, "out.wav")
    try:
        s3 = _r2()
        s3.download_file(R2_BUCKET, audio_key, src)
        sr = _enhance_file(src, dst, denoise_first=bool(inp.get("denoise")),
                           nfe=inp.get("nfe"), solver=inp.get("solver"),
                           lambd=inp.get("lambd"), tau=inp.get("tau"))
        if not os.path.getsize(dst):
            return {"ok": False, "error": "enhance produced no output"}
        s3.upload_file(dst, R2_BUCKET, output_key, ExtraArgs={"ContentType": "audio/wav"})
        return {"ok": True, "output_key": output_key, "audio_key": output_key,
                "bytes": os.path.getsize(dst), "sr": sr,
                "applied": ["speech-upscale:resemble-enhance"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:500]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def handler(job):
    inp = (job or {}).get("input") or {}
    if inp.get("selftest"):
        return _selftest(inp)
    if inp.get("audio_key"):
        return _upscale_r2(inp)
    audio_url = inp.get("audio_url")
    output_url = inp.get("output_url")
    output_key = inp.get("output_key", "")
    if not audio_url or not output_url:
        return {"ok": False, "error": "input needs presigned audio_url + output_url"}
    for u, name in ((audio_url, "audio_url"), (output_url, "output_url")):
        err = _url_error(u, name)
        if err:
            return {"ok": False, "error": err}
    work = tempfile.mkdtemp(prefix="enh-")
    src, dst = os.path.join(work, "in.wav"), os.path.join(work, "out.wav")
    try:
        with _pinned_https("GET", audio_url, timeout=DOWNLOAD_TIMEOUT, stream=True) as r:
            r.raise_for_status()
            with open(src, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        sr = _enhance_file(src, dst, denoise_first=bool(inp.get("denoise")),
                           nfe=inp.get("nfe"), solver=inp.get("solver"),
                           lambd=inp.get("lambd"), tau=inp.get("tau"))
        size = os.path.getsize(dst)
        if not size:
            return {"ok": False, "error": "enhance produced no output"}
        with open(dst, "rb") as f:
            put = _pinned_https(
                "PUT", output_url, timeout=UPLOAD_TIMEOUT, data=f,
                headers={"content-type": "audio/wav", "content-length": str(size)})
        put.raise_for_status()
        return {"ok": True, "output_key": output_key, "bytes": size, "sr": sr,
                "applied": ["speech-upscale:resemble-enhance"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:500]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


runpod.serverless.start({"handler": handler})
