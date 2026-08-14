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
#
# The purge is the #103 / fc#754 fix, and it belongs HERE because this is the earliest layer we
# control: the base image is where the bad copy comes from, so the pip layer below can only ever be
# the SECOND copy unless the first one is gone before it runs.
#
# Ubuntu 24.04 ships cryptography 41.0.7 as the dpkg package python3-cryptography, and that package
# owns ELEVEN metadata paths -- BOTH `cryptography-41.0.7.dist-info` (which has no RECORD) and
# `cryptography.egg-info`. Measured on the pristine base
# (runpod/pytorch@sha256:0a360022...): 2 metadata entries, neither carrying a RECORD.
# `runpod` requires cryptography>=50.0.0, so pip MUST replace 41.0.7; with no RECORD it cannot
# enumerate the files and errors `uninstall-no-record-file`.
#
# That is why #103 looked INTERMITTENT and was not. importlib picks whichever of the two metadata
# dirs the filesystem hands it first: land on the RECORD-less `.dist-info` and pip 25.2 raises and
# the build dies; land on `.egg-info` and pip logs "Can't uninstall ... No files were found to
# uninstall" and CONTINUES -- installing 50.0.0 into /usr/local/lib/python3.12/dist-packages while
# 41.0.7 stays in /usr/lib/python3/dist-packages. So the coin flip was never build-fails versus
# build-fine; it was build-fails LOUDLY versus build-ships-two-copies QUIETLY, and the published
# v1.1.2 image is the quiet one: measured 2 cryptography package trees and 3 metadata entries on
# ghcr.io/skyphusion-labs/vivijure-audio-upscale:1.1.2-serve, with 50.0.0 winning only on sys.path
# order and a 2023 crypto library still resident behind it.
#
# Purged rather than worked around. `--ignore-installed` and `--force-reinstall` both turn the loud
# case into the quiet case, which is not a fix, it is the defect with the alarm switched off; the
# same reasoning is why vivijure-musetalk#52 reverted `--ignore-installed` six minutes after merging
# it. The fleet's own remedy, prep-runpod-base-for-pip-builds.sh (fc#754), deletes only the
# `.dist-info` and so also lands on the two-copy state, and it is a /usr/local/sbin script on the
# Plane C bake hosts that DOES NOT EXIST on the GitHub-hosted runner this repo builds on. dpkg owns
# both metadata dirs, so purging the package takes both and leaves pip the sole owner.
#
# Measured cost of the purge on this exact base: 6 packages removed -- python3-cryptography,
# python3-oauthlib, python3-launchpadlib, python3-lazr.restfulclient, python3-software-properties,
# software-properties-common. None is used by this image; it never calls add-apt-repository, and
# ffmpeg, git, git-lfs, curl, python3 and pip were all verified working after the purge.
RUN rm -f /etc/apt/sources.list.d/*cuda*.list /etc/apt/sources.list.d/*nvidia*.list && \
    apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg ca-certificates curl git git-lfs && \
    git lfs install --system && \
    apt-get purge -y python3-cryptography && \
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
#
# deepspeed is sdist-only: install it with the base torch visible (--no-build-isolation) and
# skip native ops (inference path does not need them). Keeps a resolver hiccup from burning
# the build on ModuleNotFoundError: torch inside pip's isolated env.
RUN pip install --no-cache-dir --no-deps --ignore-requires-python resemble-enhance && \
    DS_BUILD_OPS=0 pip install --no-cache-dir --no-build-isolation "deepspeed>=0.15.0" && \
    pip install --no-cache-dir --ignore-requires-python -r /app/requirements.txt

# GUARD -- exactly ONE cryptography on disk, and it is the pip-managed one (#103, fc#754).
#
# This asserts the SHIPPED STATE, not the exit status of the install above, because the install
# above returning 0 is exactly what the two-copy failure looks like. It is placed after the pip
# layer so it observes the artifact rather than the intent, and it fails the BUILD, so a regression
# cannot reach GHCR the way v1.1.2 did.
#
# The control runs FIRST and must come back POSITIVE in the same command as the claim: if the
# finder cannot see pip's own metadata, a cryptography count of zero is blindness, not absence.
RUN set -eu; \
    ctl="$(find /usr -maxdepth 6 \( -type d -o -type f \) -name 'pip-*.dist-info' | wc -l)"; \
    echo "control: pip metadata entries visible to this finder = ${ctl}"; \
    [ "${ctl}" -ge 1 ] || { echo "FATAL: finder sees no pip metadata, so a cryptography zero would be blindness"; exit 1; }; \
    pkgs="$(find /usr -maxdepth 6 -type d -name cryptography)"; \
    np="$(printf '%s\n' "${pkgs}" | grep -c . || true)"; \
    meta="$(find /usr -maxdepth 6 \( -type d -o -type f \) \( -name 'cryptography-*.dist-info' -o -name 'cryptography*.egg-info' \))"; \
    nm="$(printf '%s\n' "${meta}" | grep -c . || true)"; \
    echo "cryptography package trees = ${np}"; printf '%s\n' "${pkgs}"; \
    echo "cryptography metadata entries = ${nm}"; printf '%s\n' "${meta}"; \
    [ "${np}" -eq 1 ] || { echo "FATAL: expected 1 cryptography package tree, found ${np} -- a second copy is #103 returning silently"; exit 1; }; \
    [ "${nm}" -eq 1 ] || { echo "FATAL: expected 1 cryptography metadata entry, found ${nm} -- an OS-managed copy survived the purge"; exit 1; }; \
    [ -f "${meta}/RECORD" ] || { echo "FATAL: ${meta} carries no RECORD, so pip does not own the surviving copy"; exit 1; }; \
    python -c "import cryptography; print('cryptography', cryptography.__version__, 'at', cryptography.__file__)"

# resemble-enhance cfm.py uses float(fsolve(...)) without [0]; NumPy 2.x raises TypeError at enhance()
# runtime (build-time load_enhancer alone does not hit this path). Patch upstream #74 locally until PyPI
# ships a fixed wheel. See scripts/patch_resemble_enhance_numpy2.py.
COPY scripts/patch_resemble_enhance_numpy2.py /app/scripts/patch_resemble_enhance_numpy2.py
RUN python /app/scripts/patch_resemble_enhance_numpy2.py

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
