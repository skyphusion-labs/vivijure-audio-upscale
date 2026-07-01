# Deploy the audio cleanup finish engine

This page walks you through standing up `vivijure-audio-upscale` on your own. When you finish, you
will have a RunPod endpoint that cleans up spoken dialogue so voices sound clear and full
(resemble-enhance), and an endpoint id you paste into your Vivijure Studio to turn it on.

New here? The one-page picture of how the parts fit together is in
[constellation.md](constellation.md). This engine is one box on that map.

## What this one does (and does not) do

It cleans **speech** only. Music and score beds do **not** go through it; they take the studio's CPU
audio path instead. The idea is cost-aware: only spend GPU time when there is actually a voice to
clean. It runs on a shot's dialogue track **before** lip-sync, so the mouth follows the cleaned audio.

## What you need first

- A **RunPod** account, and an **API key** from it (runpod.io, then Settings, then API Keys).
  RunPod is where the GPU runs.
- **Docker** on your computer, so you can build the image.
- A **registry** to push the image to, and to be logged in to it (for example GitHub Container
  Registry, `ghcr.io`).
- Optional, for the studio's normal mode: **R2 storage keys** (Cloudflare R2). The endpoint reads the
  dialogue track from R2 and writes the cleaned result back to R2.

## The short path

```bash
cp deploy.env.example deploy.env   # then open deploy.env and fill in your keys
./deploy.sh                        # safe to re-run
```

The script builds the image, pushes it, creates the RunPod endpoint, and prints the endpoint id. It
stops on the first error, so you never end up half-deployed.

## What the script does, step by step

1. **Builds** the Docker image from this repo.
2. **Pushes** it to your registry.
3. **Creates a RunPod template and endpoint** (or reuses them if they already exist), pinned to the
   GPU you chose, set to scale to zero.
4. **Prints the endpoint id** and reminds you how to wire it into the studio.

## Every setting you can set

All settings live in `deploy.env`. The example file has them all with comments; here is what each one
means and why.

### The keys you must set

- **`RUNPOD_API_KEY`** -- your RunPod API key. Why: the script talks to RunPod for you to make the
  endpoint. Example: `RUNPOD_API_KEY=rpa_XXXX...`.
- **`IMAGE`** -- the image name to build and run. Why: it is both where the script pushes the image
  and what the endpoint pulls. Point it at your own registry. Example:
  `IMAGE=ghcr.io/yourname/vivijure-audio-upscale:latest`.
- **`ENDPOINT_NAME`** -- a label for the endpoint. Why: the script finds and reuses an endpoint by
  this name, so re-running is safe. Example: `ENDPOINT_NAME=vivijure-audio-upscale`.
- **`GPU_TYPE_IDS`** -- which GPU cards RunPod may use, separated by commas. Why: this image is built
  for **CUDA 12.8**, which needs a card on a **new driver**. Pin it to **Blackwell (RTX PRO 6000)** or
  **Hopper (H100 / H200)** cards, which are always on new drivers. The job is short and light on VRAM,
  so a scale-to-zero endpoint on these cards still costs pennies. Example:
  `GPU_TYPE_IDS=NVIDIA RTX PRO 6000 Blackwell Server Edition,NVIDIA H100 80GB HBM3`.

### The knobs you usually leave alone

- **`CONTAINER_DISK_GB`** (default `20`) -- how much disk the container gets. Why: resemble-enhance
  bakes about 713MB of weights, so 20 is plenty. Example: `CONTAINER_DISK_GB=20`.
- **`WORKERS_MIN`** (default `0`) -- the fewest workers kept running. Why: `0` means scale to zero, so
  you pay nothing when no one is rendering.
- **`WORKERS_MAX`** (default `2`) -- the most workers that can run at once. Why: caps parallel jobs and
  your spend.
- **`IDLE_TIMEOUT`** (default `5`) -- seconds a worker stays warm after a job before it shuts down.
  Why: a small warm window avoids a cold start if a second shot arrives right away.
- **`EXECUTION_TIMEOUT_MS`** (default `600000`) -- the longest a single job may run, in milliseconds
  (600000 = 10 minutes). Why: a stuck job is cut off instead of billing forever.
- **`CONTAINER_REGISTRY_AUTH_ID`** (default empty) -- a RunPod credential id for a **private** image.
  Why: if your image is private, RunPod needs a login to pull it. Make one in the RunPod console
  (Settings, then Container Registry Auth) and paste its id here. Leave blank for a public image.
- **`REGISTRY_USER`** / **`REGISTRY_TOKEN`** (default empty) -- a login for your registry, used to push
  the image. Leave blank if you already ran `docker login`.
- **`SKIP_BUILD`** (default `0`) -- set `1` to skip build and push and reuse an image already pushed.
  **`SKIP_ENDPOINT`** (default `0`) -- set `1` to stop after pushing the image (no endpoint).

### The endpoint's own settings (R2 mode)

The studio's normal mode is "finish-chain" mode: the endpoint reads and writes your R2 bucket by key,
so no audio passes through the studio. Set these four to turn it on. Leave them blank to use only the
presigned-URL mode, where the studio hands the endpoint short-lived links instead.

- **`R2_ENDPOINT_URL`** -- your R2 S3 address (looks like `https://<account>.r2.cloudflarestorage.com`).
- **`R2_BUCKET`** (default `vivijure`) -- the bucket name the audio lives in.
- **`R2_ACCESS_KEY_ID`** / **`R2_SECRET_ACCESS_KEY`** -- an R2 key pair scoped to that bucket. Make a
  key just for this engine so its reach is small.

## What the endpoint expects as a job

You do not call this by hand in normal use; the studio does. But so you know exactly what it does,
here is the contract.

- **R2 finish-chain mode:** `{ "audio_key": "...", "output_key": "...", "denoise": true, "nfe": 64,
  "lambd": 0.9, "tau": 0.5, "solver": "midpoint" }`. The endpoint reads the audio from R2 and writes
  the cleaned track to `output_key`.
- **Presigned mode:** `{ "audio_url": "...", "output_url": "...", "output_key": "..." }`. The studio
  presigns the links; the endpoint holds no keys.
- **Self-test:** `{ "selftest": true }`. Enhances a generated clip end to end. Use it to prove a fresh
  endpoint works.

The cleanup knobs you can pass (all optional; the defaults are tuned):

- **`denoise`** (default off) -- run a denoise pass first. Why: turn it on for noisy or hissy source
  audio; leave it off for already-clean TTS. Example: `denoise: true`.
- **`nfe`** (default `64`) -- how many refinement steps the model takes. Why: more steps means a
  cleaner result but a slower job. Example: `nfe: 64`.
- **`lambd`** (default `0.9`) -- how strongly to lean on the denoiser (0 to 1). Why: higher removes more
  noise but can sound over-processed. Example: `lambd: 0.9`.
- **`tau`** (default `0.5`) -- a "temperature" that trades a smoother result against a more detailed
  one. Example: `tau: 0.5`.
- **`solver`** (default `midpoint`) -- the math method the model steps with (`midpoint`, `rk4`, or
  `euler`). Why: `midpoint` is a good balance of quality and speed. Example: `solver: "midpoint"`.

The result is `{ ok, output_key, bytes, sr, applied: ["speech-upscale:resemble-enhance"] }` on
success, or `{ ok: false, error }` on failure. Unlike the video engines, this one **surfaces** a
failure (returns `ok:false`) rather than passing the original through: the studio's router owns the
soft-degrade decision, and the `applied` tag is set only on real success, so a miss is never hidden.

## Turn it on in the studio

This engine powers the studio's **speech-upscale** module (an opt-in tier). Unlike the video finish
engines, its endpoint id is a **per-module secret**, not an account secret. To turn it on:

1. Copy the endpoint id the script printed.
2. In your studio folder, run:
   `npx wrangler secret put RUNPOD_ENDPOINT_ID -c modules/speech-upscale/wrangler.toml`
   and paste the endpoint id when asked.
3. Keep the `speech-upscale` (`MODULE_SPEECH_UPSCALE`) binding on and deploy the studio.

Full context on the tiers is in the studio's `docs/opt-in-tiers.md` (the "speech-upscale" entry).

## Re-running and fixing things

- Re-running `./deploy.sh` is safe. It reuses the template and endpoint it already made.
- To change the endpoint's GPU or scaling after it exists, use the RunPod console; RunPod does not let
  the API re-pin an endpoint's GPU list after creation.
- If a push fails, make sure you ran `docker login` for your registry and that the repo exists there.
- If the endpoint's workers never start, check the GPU pin: a cu128 image on an old-driver host will
  refuse to boot. Pin Blackwell or Hopper.
