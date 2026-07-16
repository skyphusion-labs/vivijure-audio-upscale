# vivijure-audio-upscale -- speech audio enhancement (CUDA), RunPod serverless image.
#
# Engine: resemble-enhance (denoise + restore + bandwidth-extend SPEECH) on PyTorch/CUDA. Runs on the
# per-shot dialogue track BEFORE MuseTalk so the lips sync to the cleaned audio. The transport contract
# and the {"selftest": true} harness mirror vivijure-upscale.
#
# Base: RunPod's torch 2.8 / CUDA 12.8.1 image (same as the sibling vivijure-upscale/musetalk images).
# cu128/torch-2.8 ships Blackwell (sm_120) kernels, so the worker runs on ANY card RunPod substitutes
# -- the older torch-2.1.1/cu121 build crash-looped when RunPod swapped our L4/L40S for a Blackwell
# (sm_120) GPU (_cuda_init_check: no kernel image for the device). resemble-enhance pins torch==2.1.1
# but we install it --no-deps (below), so the pin doesn't bind and its inference path runs on torch 2.8.
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404

ENV DEBIAN_FRONTEND=noninteractive

# Drop NVIDIA's CUDA apt source before `apt-get update`: we only need ffmpeg/git/git-lfs from the
# standard Ubuntu repos, and NVIDIA's mirror periodically fails update mid-sync ("File has unexpected
# size"). torch + CUDA are already baked into the base, so the cuda apt repo is unneeded here.
RUN rm -f /etc/apt/sources.list.d/*cuda*.list /etc/apt/sources.list.d/*nvidia*.list && \
    apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg ca-certificates curl git git-lfs && \
    git lfs install --system && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# resemble-enhance lists gradio (its demo UI); gradio's fastapi-cli chain sends pip into a
# backtracking storm on this base AND we serve no UI. So install resemble-enhance WITHOUT its deps
# and pin the inference runtime deps ourselves (requirements.txt, gradio dropped). torch/torchaudio/
# torchvision come from the base image and satisfy resemble-enhance's >=2.1.1 floors.
#
# Base image Python is 3.12.3 (Ubuntu 24.04); resemble-enhance still declares Requires-Python
# <3.12 even though we install --no-deps and run inference on the base torch 2.8 stack.
# --ignore-requires-python keeps the Blackwell-capable cu128 base (pinning a separate 3.11
# interpreter would not inherit those CUDA wheels). See #42.
RUN pip install --no-cache-dir --no-deps --ignore-requires-python resemble-enhance && \
    pip install --no-cache-dir --ignore-requires-python -r /app/requirements.txt

# Bake the model weights into the image (no network volume). resemble-enhance's download() git-clones
# the ResembleAI/resemble-enhance HF repo into <pkg>/model_repo (LFS weights); we pre-clone it here
# with git-lfs so the real 713MB checkpoint is baked. At runtime download() then sees model_repo/.git
# and does a cheap `git pull` (LFS-skip) instead of re-fetching the weights. Verify the model loads
# on CPU -- a build-time fail-fast.
RUN PKG="$(python -c 'import resemble_enhance, os; print(os.path.dirname(resemble_enhance.__file__))')" && \
    rm -rf "$PKG/model_repo" && \
    git clone "https://huggingface.co/ResembleAI/resemble-enhance" "$PKG/model_repo" && \
    git -C "$PKG/model_repo" lfs pull && \
    test -s "$PKG/model_repo/enhancer_stage2/ds/G/default/mp_rank_00_model_states.pt" && \
    python -c "from resemble_enhance.enhancer.inference import load_enhancer; load_enhancer(None, 'cpu'); print('resemble-enhance weights baked + model loads')"

# Weights are baked -> go offline at runtime (no surprise HF fetch mid-job).
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY handler.py /app/handler.py
WORKDIR /app
CMD ["python", "handler.py"]
