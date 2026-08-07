# Changelog -- vivijure-audio-upscale

The image ships as a git-tag-driven release (`v<X.Y.Z>`; CI publishes GHCR on tag push). Each tag
builds the consumer image. This file records the why behind each release; the tag is the version of
record. Newest first.

## v1.1.1

- **fix(gpu): release torch's cached VRAM after every enhance (fc#1592).** Follows
  `vivijure-upscale`'s handler, which calls `torch.cuda.empty_cache()` after its GPU phase for the
  same reason. **Model weights are ALLOCATED, not cached, so residency survives** -- the warm model
  this serve overlay exists to keep is unaffected; only the job's scratch blocks go back.
  **Measured, which is why this is a fix and not a tidy-up** (RTX 4000 SFF Ada, 20475 MiB,
  2026-08-07): without it a resident door's footprint is a **high-water mark of the largest job it
  has ever served, and it only rises**. Two boxes running this identical image but different job
  histories sat at **1930 MiB** (1s selftests only) and **12390 MiB** (one 30s clip), and the
  second never came back down. That is not a ceiling anyone can plan against. The consequence
  reaches past this process: on a card co-tenanted with the video upscale door, that door's NVENC
  encoder is a SEPARATE CUDA context which cannot use torch's reserved pool, and
  `vivijure-upscale`'s own handler records `CreateInputBuffer failed: out of memory` as exactly
  what happens then. Concurrent peak with both doors working measured **18797 of 20475 MiB**.
- **Placed at the single choke point, and in a `finally`.** `_enhance_file` is the one function
  every mode goes through (R2, presigned and selftest all call it), so one release covers all three
  rather than three call sites that drift apart. It is in a `finally` rather than on a trailing
  line because an exception would otherwise keep the whole job's cache for the life of the resident
  process -- the exact defect being fixed, surviving on the error path. References are dropped
  first, since `empty_cache()` only returns blocks nothing still holds.
- **test: the GPU path had no behavioural coverage at all** -- this repo carried no torch stubs and
  its only handler test was an AST parse. `tests/test_cuda_cache_release.py` (stub pattern taken
  from `vivijure-upscale`'s proven one) covers release on success, release **on the raise path**,
  the ORDER (release after the output is written, since presence alone cannot tell that from a
  release before it), the no-CUDA guard, and a positive control proving the recorder can observe a
  MISSING release -- without which every other assertion in the file would be vacuous.
- **Mutation-tested, checked for the right red.** Deleting the call reddens three tests by name;
  **the naive implementation -- a trailing line instead of a `finally` -- reddens ONLY the raise
  test**, which is what proves the `finally` is load-bearing rather than decorative; dropping the
  `is_available()` guard reddens the no-CUDA test. Restoring returns 19/19 green. The harness
  refused to run at all on its first attempt because its scratch baseline was red (an incomplete
  copy), which is the guard working: mutation results against a red baseline are uninterpretable.

## v1.1.0

- **ci(serve): publish the `*-serve` overlay to GHCR on every release tag (fc#1592,
  vivijure-upscale#89 item 1).** Nothing built a serve image and nothing would have: GHCR
  carried 28 tags for this package and **zero** `*-serve` tags (measured with a positive
  control -- the same query returns `1.0.8`, so the zero is a real absence and not a blind
  one). Every resident door on the fleet therefore ran a HAND-BUILT local tag, which our own
  standing rule forbids: evidence has to be about a SHA, and a locally-built tag cannot be
  re-pulled, re-verified or rolled back by anyone else. `build-image.yml` now builds and pushes
  `<version>-serve`, `<major>.<minor>-serve` and `sha-<short>-serve` from the SAME job as the
  release image, gated identically (a bare merge to main smoke-builds and does not publish).
  Same job because the overlay's `FROM` is the release image, so the ordering is not optional
  and the base is already in the local daemon -- one thin layer instead of a second tens-of-GB
  pull, and the published overlay and its base always come from one source tree. The step
  carries two controls (the resolved base must be one of the tags this job built, whole-line
  matched, and it must already exist LOCALLY so docker cannot silently pull a same-named stale
  tag) and prints `derived N serve tags of M release tags` with a floor, so a zero is a harness
  failure rather than a silent pass.
- **fix(serve): `AUDIO_UPSCALE_IMAGE` no longer carries a default (fc#1592,
  vivijure-upscale#89 item 2).** It pinned the literal `:1.0.7`, which is a hand copy of
  something the artifact already knows: it drifts one release at a time and its failure mode is
  a door that WORKS on a stale base, which is the failure nobody investigates. CI now passes the
  tag it just built; a hand build must pass the arg. Proved with a control pair on real docker:
  no arg -> `rc=1`, `base name (${AUDIO_UPSCALE_IMAGE}) should not be blank`, refused at parse
  before any pull; `--build-arg AUDIO_UPSCALE_IMAGE=busybox:latest` -> `rc=0`, so the refusal is
  the missing arg and not a malformed Dockerfile. The resulting `InvalidDefaultArgInFrom` build
  warning is the intended shape and is documented as such in `CLAUDE.md` so nobody "fixes" it
  back into a default.
- **docs: `CLAUDE.md` gains a homelab serve-overlay section.** `serve.py`'s own docstring said
  "See CLAUDE.md for the measured proof" and `CLAUDE.md` carried no serve, residency or homelab
  content whatsoever -- a pointer at a document that did not hold the thing. It now records the
  published tag shape, the required build arg, port 8013 (8012 is the video door, so both can be
  resident on one card), the env the door needs, why `/health` is a control and the forwarded
  selftest is the measurement, and the dated residency measurement with an explicit instruction
  to re-measure rather than carry it forward.
- Carries the previously-unreleased serve overlay work below, which had merged to `main` with no
  release tag and therefore no published artifact of any kind.

- **fix(serve): forward `selftest` to the wrapped handler instead of intercepting it
  (fc#1592 lane B review, vivijure-upscale#88).** The overlay's `POST /run` originally
  answered `{"selftest": true}` with a liveness-only shortcut, copied verbatim from
  `vivijure-upscale`. `handler.py`'s own docstring calls that key the deploy-verification
  GPU check; answering it before reaching the handler made the documented check
  structurally incapable of failing. Now forwarded like any other job (submit -> poll
  `/status/<id>`), so it genuinely loads the model and runs a real enhance. `/health`
  remains the fast auth-free liveness probe -- unchanged. Re-verified on a fresh SecurePod:
  `ok: true`, real `gpu` field, `output_bytes: 88278` matching the serverless control;
  residency re-confirmed through the real HTTP path (model-download log line appears once
  across two sequential selftest jobs).
- **feat(serve): add the `Dockerfile.serve` overlay for resident homelab deployment (fc#1592
  lane B, fc#1488).** Mirrors `vivijure-upscale`'s proven pattern: `serve.py` +
  `runpod_http_serve.py` (copied verbatim from `vivijure-upscale`, the more hardened of the two
  siblings -- it carries a `MAX_HTTP_BODY_BYTES` cap `vivijure-musetalk`'s copy does not yet have)
  layer a RunPod-compatible `/run` + `/status` HTTP server on top of the existing serverless
  image, so the resemble-enhance model can stay resident on our own GPU boxes instead of paying
  serverless cold start per job. `Dockerfile.serve` pins the base to the actual production tag
  `:1.0.7` (not `:1.0.8`, which the v1.0.8 entry above says is docs-only and deliberately not
  repinned).
- **fix(handler): guard `runpod.serverless.start()` behind `if __name__ == "__main__":` (fc#1592
  lane B).** It was a bare module-level call, unlike the identical line in `vivijure-upscale` and
  `vivijure-musetalk`'s handler.py, both of which already guard it. Importing `handler` from
  `serve.py` (`from handler import handler`) ran the serverless worker's own local-dev loop at
  import time, which found no `test_input.json` and exited before `serve.py`'s own HTTP server
  ever started -- the serve overlay could not run at all without this fix. No behavior change for
  the existing serverless CMD path (`python handler.py` already runs as `__main__`).
- **Measured on an on-demand RunPod SecurePod (RTX PRO 6000 Blackwell, 2026-08-07):** model
  residency proven via `resemble_enhance.enhancer.inference.load_enhancer`'s own
  `functools.cache` -- 1 cache miss (one real weight load) across 5 sequential enhance/denoise
  calls in one long-lived process, 7 subsequent cache hits, `nvidia-smi` memory.used flat at
  3117 MiB across calls 2-4. `torch.cuda.max_memory_allocated()` peak 2132.9 MiB. Fits alongside
  `vivijure-upscale`'s measured ~5933 MiB (fc#1488) with headroom on the 20475 MiB target card.
  The unmodified serverless `{"selftest": true}` path was re-verified on a separate serverless
  endpoint the same session (`ok: true`, `output_bytes: 88278`, matching fc#1488 exactly) as the
  control that this change did not touch the shipped path.

## v1.0.8

- **fix(hub): align the Hub listing GPU pools and disk with the production endpoint (#77).** The
  listing advertised `BLACKWELL_180,HOPPER_141` and explicitly negated the three RTX PRO 6000 cards
  by name. Those cards ARE the `BLACKWELL_96` pool, which is the pool production endpoint
  `sj0btgpjdtswa7` actually runs this worker on, so the listing excluded the one configuration we
  prove daily and left a Hub deployer on B200 or H200 class hardware at roughly two to three times
  the hourly cost for the same job. `gpuIds` is now `BLACKWELL_96,HOPPER_141,BLACKWELL_180`
  (production pool first, larger pools kept as availability fallbacks; no unproven pool added), and
  `tests.json` runs the Hub smoke on `NVIDIA RTX PRO 6000 Blackwell Server Edition`, the card
  production runs on.
- **fix(hub): raise `containerDiskInGb` from 20 to 40.** The image is 12.3 GB COMPRESSED, so a 20 GB
  container disk cannot hold it uncompressed; production uses 40. As listed, a Hub deploy could fail
  on a demo-facing page. `.runpod/README.md` records the provenance and the repin rule.
- **Docs and listing metadata only.** The tag still bakes a consumer image (`build-image.yml` fires
  on `v*.*.*` tags), and `:1.0.8` is functionally identical to `:1.0.7`. Production stays pinned to
  `:1.0.7` on purpose; **no repin**.

## v1.0.7

- **fix(security): project-scoped R2 + SSRF DNS pin, baked (#68, #70, #71, #72) with the CI bake fix
  (#73).** Same handler content the failed v1.0.6 intended: project scope on `audio/<project>/`,
  presigned URL SSRF gate with DNS-pinned HTTPS, allowlist sync hardened, plus newline-safe docker
  meta tags so the bake completes. **This is the prod pin:** `:1.0.7`.
  (Backfilled 2026-07-25 from the v1.0.7 GitHub release; the row was missing from this file.)

## v1.0.6

- **Bake FAILED; do not pin `:1.0.6`.** The `build-image` run died before push (newline-separated
  docker meta tags broke bash, fixed in #73). The tag and GitHub release exist, the image does not.
  Use v1.0.7, which carries the same security content.
  (Backfilled 2026-07-25 from the v1.0.6 GitHub release; the row was missing from this file.)

## v1.0.5

- **docs(hub): RunPod Hub publish surface (audio-upscale#62).** `.runpod/hub.json` + `tests.json`
  (`{"selftest": true}`), `.runpod/README.md` with the R2 env names (`R2_ENDPOINT_URL`),
  `THIRD_PARTY_MODELS.md`, and the Hub badge. Docs-only patch cut so Hub, which indexes releases and
  not commits, could index a release tree containing `.runpod/`. No handler or image-recipe change;
  runtime remained the v1.0.4 NumPy/fsolve fix.
  (Backfilled 2026-07-25: this entry sat under Unreleased, but `git tag --contains` puts the commit
  in v1.0.5 through v1.0.7, so it shipped in v1.0.5.)

## v1.0.4

- **fix(build): patch resemble-enhance fsolve for NumPy 2.x (PR #55).** Build-time patch
  (`scripts/patch_resemble_enhance_numpy2.py`) fixes upstream `cfm.py` calling
  `float(scipy.optimize.fsolve(...))` on a 1-d ndarray; NumPy 2.x raises
  `TypeError: only 0-dimensional arrays can be converted to Python scalars`. Upstream fix:
  [resemble-ai/resemble-enhance#74](https://github.com/resemble-ai/resemble-enhance/pull/74) (index
  `[0]` before `float()`). Prod validated on RunPod (`{"selftest": true}` + film speech-upscale path).
  **Pin this tag for prod.**

## v1.0.3

- **fix(deps): pin numpy under numba 0.66 ceiling (PR #54).** Dependabot #53 had bumped `numpy` to
  `>=2.5.1`, which broke pip resolution against numba's `numpy<2.5` constraint and left v1.0.2's
  image bake red. This release restores `numpy>=2.2.0,<2.5` so the image builds and publishes to
  GHCR. **Runtime still broken on RunPod:** resemble-enhance hits the NumPy 2.x `float(fsolve(...))`
  scalar bug (fixed in v1.0.4); enhance jobs fail with the same TypeError. Tag exists; **no GitHub
  release** (do not pin for prod).

## v1.0.2

- **deps: Dependabot numpy bump (PR #53).** Raised `numpy` from `<2.5,>=2.2.0` to `>=2.5.1,<2.6`.
  **Image bake failed:** pip resolution is impossible (`numpy>=2.5.1` vs numba 0.66 requiring
  `numpy<2.5`). Tag exists; CI `build-image` run failed; **no GitHub release.** Image may not have
  shipped to GHCR as a consumable release tag.

## v1.0.1

- **fix(build): restore image build on Python 3.12 base (#42, PRs #43-#45).** Patch release so prod
  could pin a SemVer tag again after main image builds were red: ignore resemble-enhance
  `Requires-Python <3.12`, pin numba/llvmlite for Python 3.12, align `numpy<2.5` with numba, and
  install deepspeed with base torch visible. Keeps the Blackwell-capable RunPod cu128 / Python 3.12.3
  base (no separate 3.11 interpreter).

## v1.0.0

- **First stable release of the speech / audio-upscale finish module.** The audio-upscale satellite
  in the Vivijure constellation, ran clean in the Studio v1.0.0 shakedown. Ships on top of v0.1.0:
  docs discoverability + SEO metadata (#31), corpus-sync dispatch to search-mcp (#30), and build/deps
  floor bumps (#21-#28). Part of the constellation-wide v1.0.0 milestone. The `v1.0.0` tag builds +
  publishes the consumer image.
