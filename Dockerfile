# vivijure-audio-upscale -- speech audio enhancement (CUDA), RunPod serverless image.
#
# Engine: resemble-enhance (denoise + restore + bandwidth-extend SPEECH) on PyTorch/CUDA. Runs on the
# per-shot dialogue track BEFORE MuseTalk so the lips sync to the cleaned audio. The transport contract
# and the {"selftest": true} harness mirror vivijure-upscale.
#
# Base: RunPod's torch 2.1.1 / py3.10 / CUDA 12.1.1 image -- resemble-enhance hard-pins torch==2.1.1
# (and py<3.12), so we base on its native stack rather than fight the newer torch-2.8 base used by
# vivijure-upscale. torch + torchaudio come from the base; requirements pull resemble-enhance.
FROM runpod/pytorch:2.1.1-py3.10-cuda12.1.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg ca-certificates curl git git-lfs && \
    git lfs install --system && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# resemble-enhance lists gradio (its demo UI); gradio's fastapi-cli chain sends pip into a
# backtracking storm on this base AND we serve no UI. So install resemble-enhance WITHOUT its deps
# and pin the inference runtime deps ourselves (requirements.txt, gradio dropped). torch/torchaudio/
# torchvision come from the base image and satisfy resemble-enhance's >=2.1.1 floors.
RUN pip install --no-cache-dir --no-deps resemble-enhance && \
    pip install --no-cache-dir -r /app/requirements.txt

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
