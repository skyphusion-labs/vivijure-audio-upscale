# Changelog -- vivijure-audio-upscale

The image ships as a git-tag-driven release (`v<X.Y.Z>`; CI publishes GHCR on tag push). Each tag
builds the consumer image. This file records the why behind each release; the tag is the version of
record. Newest first.

## Unreleased

- Nothing yet.

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
