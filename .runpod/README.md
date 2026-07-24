# RunPod Hub -- Vivijure Audio Upscale

Hub listing config for the Vivijure speech-cleanup finish satellite.

## Required environment (finish-chain / R2 mode)

| Env key | What to put |
| --- | --- |
| `R2_ENDPOINT_URL` | `https://<account-id>.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | Public half of an R2 API token |
| `R2_SECRET_ACCESS_KEY` | Secret half of that token |
| `R2_BUCKET` | Bucket shared with Vivijure Studio (default `vivijure`) |

**Name check:** this worker reads `R2_ENDPOINT_URL`. The main `vivijure-backend` listing uses
`R2_ENDPOINT` (no `_URL`).

## Hub test

`.runpod/tests.json` sends `{ "selftest": true }` (tiny noisy speech clip, enhance end to end).
No R2 credentials required. Pin **Blackwell** or **Hopper** (CUDA 12.8 image).

## GPU and disk (source of truth: the production endpoint)

`hub.json` mirrors what the Vivijure production endpoint actually runs (`sj0btgpjdtswa7`, running `ghcr.io/skyphusion-labs/vivijure-audio-upscale:1.0.7`,
read from the RunPod API on 2026-07-25), so a Hub deployer gets the configuration we ourselves
prove every day:

- `gpuIds`: `BLACKWELL_96,HOPPER_141,BLACKWELL_180`. `BLACKWELL_96` (RTX PRO 6000) is the pool production uses; the larger pools stay
  listed as fallbacks for availability. The earlier config excluded `BLACKWELL_96` outright, which
  pushed Hub deployers onto B200 and H200 class cards at roughly two to three times the hourly cost
  for the same job.
- `containerDiskInGb`: `40` (raised from 20, which could not hold the image uncompressed). The image is 12.3 GB compressed.
- `tests.json` pins `NVIDIA RTX PRO 6000 Blackwell Server Edition`: the card production runs on, so a
  green Hub test means the same thing our own endpoint means.

Repin this section together with `hub.json` whenever the production endpoint moves pools or image.

Third-party model inventory: [THIRD_PARTY_MODELS.md](../THIRD_PARTY_MODELS.md).
