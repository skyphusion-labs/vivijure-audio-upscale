# Changelog -- vivijure-audio-upscale

The image ships as a git-tag-driven release (`v<X.Y.Z>`; CI publishes GHCR on tag push). Each tag
builds the consumer image. This file records the why behind each release; the tag is the version of
record. Newest first.

## Unreleased

- **docs(hub):** add `.runpod/hub.json` + `tests.json`, Hub badge, `THIRD_PARTY_MODELS.md`, and
  Hub R2 env notes (`R2_ENDPOINT_URL`) for RunPod Hub publish (audio-upscale#62).

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
