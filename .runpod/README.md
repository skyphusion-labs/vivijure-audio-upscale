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

Third-party model inventory: [THIRD_PARTY_MODELS.md](../THIRD_PARTY_MODELS.md).
