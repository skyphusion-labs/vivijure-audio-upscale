# CLAUDE.md

Guidance for Claude Code (and the crew) working in this repo.

## What this is

**The CUDA speech-enhancement backend for Vivijure's audio finish path.** A single RunPod serverless
image that cleans + restores + bandwidth-extends SPEECH with
[resemble-enhance](https://github.com/resemble-ai/resemble-enhance) (denoise -> restore -> 16 kHz ->
44.1 kHz). It runs on a shot's **dialogue** track **before** MuseTalk, so the lip-sync follows the
cleaned audio and thin / auto-generated TTS (Aura-1) comes out full and natural. Speech only: music /
score beds bypass it and take the CPU `audio-mix` path (ffmpeg DSP), cost-aware routing -- GPU only
when there is speech.

This repo is the image + the RunPod handler; the studio-side audio-finish module worker (thin module on
`vivijure-cf` / `vivijure-local`, types from `vivijure-core`) is what calls this endpoint. Image:
`ghcr.io/skyphusion-labs/vivijure-audio-upscale`. Pin by versioned tag from git tags / GHCR; do not
freeze a single version here as current forever. GPU `{"selftest": true}` is spend-gated on a real
endpoint / SecurePod before prod pin.

## The Vivijure constellation

```
   vivijure-cf / vivijure-local  (panels; core: vivijure-core)
            |
            v
   vivijure-backend + finish satellites
            |
     musetalk | upscale | audio-upscale (THIS) | wan-train | local-12/16gb
```

## Handler contract (the job, `handler.py`)

One typed in / one typed out, three dispatch modes (`handler(job)` branches on the input keys). It is
**audio in, audio out**:

- **R2 finish-chain mode** (the endpoint reads/writes the shared bucket itself, no creds on the wire):
  `{ audio_key, output_key?, denoise?, nfe?, lambd?, tau?, solver? }`.
- **Presigned mode** (credentialless: the caller presigns R2): `{ audio_url, output_url, output_key? }`.
- **Selftest:** `{ "selftest": true }` confirms CUDA, loads the model, generates a tiny noisy
  speech-band clip and enhances it end to end. Doubles as the health check (endpoint-gated, see above).

Success returns `{ ok, output_key, bytes, sr, applied:["speech-upscale:resemble-enhance"] }`. The
inference knobs (`nfe` diffusion steps, `lambd` denoise strength, `tau` prior temperature, `solver` ODE
solver) are resemble-enhance's documented defaults, overridable per job.

**Degrade policy lives in the orchestrator, NOT here.** Unlike the video finish modules, this handler
**surfaces** failure (returns `ok:false`) rather than passing the original through; the `applied` tag is
set ONLY on a real enhance, and the router / orchestrator owns any soft-degrade decision (the #249
silent-degrade discipline: a degrade is a decision someone makes explicitly, never a swallowed miss).

## Commands

This is a Python / RunPod image, NOT an npm package. There is no local test suite; verification is the
build-time model-load fail-fast plus the GPU-gated selftest.

```bash
# Build the image locally (CI does this on push). The build FAILS if the resemble-enhance weights do not
# bake or the model does not load on CPU (a build-time fail-fast).
docker build -t vivijure-audio-upscale:dev .

# Lint the handler without a GPU.
python -m py_compile handler.py

# GPU verify (once the endpoint is pinned -- spend-gated): send {"selftest": true} and assert ok:true.
```

**Release / deploy mechanics.** `.github/workflows/build-image.yml` builds + pushes to GHCR on a push to
`main` (touching the build inputs) as a `sha-<short>` smoke image only (no `:latest` contract); a
pushed SemVer tag ALSO publishes the pinnable release image tagged `<version>` + `<major>.<minor>` +
`sha-<short>`. PUBLIC repo; CI on GitHub-hosted `ubuntu-latest`. Operator sets endpoint image tag,
GPU type, and R2 env (**never freeze endpoint IDs here**). Registry-auth is MCP/API-manageable
(`containerRegistryAuthId` on template).

## Architecture

- **Baked weights, no network volume.** resemble-enhance's ~713MB checkpoints are baked at build via a
  `git-lfs` clone of the `ResembleAI/resemble-enhance` HF repo into the package's `model_repo`; runtime
  is `HF_HUB_OFFLINE=1`, so a cold worker never re-downloads. The GPU-rationing thesis: scale-to-zero,
  no cold-pull.
- **`--no-deps` install is deliberate.** resemble-enhance pins `torch==2.1.1` and lists `gradio` (its
  demo UI). We install it `--no-deps` and pin the inference runtime ourselves (`requirements.txt`,
  gradio dropped): torch/torchaudio come from the cu128/torch-2.8 base, so the pin does NOT bind and
  inference runs on torch 2.8. This is why the worker survives a RunPod card swap to Blackwell (sm_120)
  -- the older torch-2.1.1/cu121 build crash-looped ("no kernel image for the device") on that swap.
- **No `TORCH_CUDA_ARCH_LIST`.** Nothing compiles from source here; torch kernels come from the base.

## Verifying changes

After any handler or Dockerfile change: build clean (the model-load on CPU is a build-time fail-fast),
then run the **pre-prod GPU gate** below and confirm `ok:true` with a non-zero `output_bytes` before
cutting a release tag / repinning prod. Verify the **artifact**, not only CI.

## Pre-prod GPU test spend (Conrad, 2026-08-06) -- do not thrift here

**Never hold back RunPod spend when proving an image before it is production-pinned.** A green bake is
not a proven enhance. Pre-prod verification is **expected spend**, not an escalation. Community pods
are not the gate.

Pick **one** of these for the gate (either is fine; pick what fits the change):

| Path | How | When |
| --- | --- | --- |
| **SecurePod** | Spin a SecurePod (or equivalent dedicated pod) on the candidate image; run `{"selftest": true}` (and a real short job if needed); verify the **artifact** (`ok:true`, non-zero `output_bytes`). | Prefer for isolated image proof without touching prod traffic. |
| **Serverless endpoint** | Deploy/pin the candidate image on the audio-upscale serverless endpoint, set **active workers (min idle / `workersMin`) to 1** so cold-start does not fake a hang or a false timeout, run the same selftest / short job, verify the artifact. | Prefer when the proof needs the real endpoint shape (env, network, R2). |

### HARD: restore workers after serverless test

If you raised the serverless endpoint's active / min workers **above 0** for testing, **bring it
back to 0 when the test is done** (same session, before you walk away). Leaving `workersMin` /
active workers at 1+ burns idle GPU money with no proof benefit. Max workers can stay at the
prod pin; the restore rule is about the **floor that keeps a warm worker** (min/active = 0 in
steady state unless Conrad ruled otherwise for prod capacity).

Do **not** skip the restore because "we might test again tomorrow." Re-raise to 1 at the next
test if needed. Document the before/after values in the PR or runlog when you change them.

Never trust: CI green alone or bake green alone.

## Conventions

- **No em-dashes (U+2014) or en-dashes (U+2013) anywhere.** Use commas, semicolons, parentheses, or `--`.
- Handle / username is `skyphusion` across all services.
- **This handler surfaces failure (`ok:false`); it never silently passes the original through.** The
  `applied` tag is success-only. Soft-degrade is the orchestrator's call (the #249 discipline).
- Speech only by design (music takes the CPU `audio-mix` path); keep the cost-aware routing intact.
- Minimal deps; the `--no-deps` pin set is load-bearing (see Architecture). Justify + re-validate changes.
- resemble-enhance (MIT) + PyTorch/torchaudio (BSD) + FFmpeg are listed in `THIRD_PARTY_NOTICES.md`;
  keep it current.

## Crew + identity

- The FIRST command in any op is the member's own login shell: `sudo -u <member> bash -lc '<ops>'`
  (loads their `$HOME`, their `~/dev/vivijure-audio-upscale` clone, their gh / RunPod / R2 creds).
  Commits and PRs land under the member's `skyphusion-<member>` identity, never Conrad's.
- **Pre-prod GPU proof spend is authorized** (SecurePod or serverless workersMin=1). Do not thrift
  out of the proof. **Serverless min/active workers back to 0 when the test ends.**
- Operating memory for the vivijure family lives in the per-project memory under
  `~/.claude/projects/-home-conrad-dev-vivijure/memory/` (`seg-vivijure-modules`); load it before acting.
- **HARD AUP line:** the CSAM bright line is absolute. Non-negotiable.
- **Ignore Cursor `AGENTS.md`.** No endpoint-ID freezes.

## Commits & versioning

Conventional Commits (`feat(scope):`, `fix(scope):`, `docs:`); body explains the why. SemVer-style
`0.MINOR.PATCH` while pre-1.0 (PATCH for fixes / backend tweaks, MINOR for features). A release is a
pushed `vMAJOR.MINOR.PATCH` git tag (CI publishes the matching immutable image tag the endpoint pins to).

## Release / deploy

**Tag-gated production deploy.** Merges to `main` run CI only; they do not ship production.
Cut an annotated SemVer tag on `main` to release (`git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`).
Deploy workflows assert the tag commit is an ancestor of `origin/main`.
