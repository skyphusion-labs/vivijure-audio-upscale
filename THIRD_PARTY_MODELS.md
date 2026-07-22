# Third-party models (Hub / baked image)

The `ghcr.io/skyphusion-labs/vivijure-audio-upscale` image bakes resemble-enhance checkpoints so a
worker runs without a network pull. This is the Hub-facing summary. Full copyright and license text:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

| Role | Component | License | Source |
| --- | --- | --- | --- |
| Speech enhance | resemble-enhance (code + weights) | MIT | https://github.com/resemble-ai/resemble-enhance |
| Runtime | PyTorch | BSD-3-Clause | https://github.com/pytorch/pytorch |
| Audio I/O | torchaudio | BSD-2-Clause | https://github.com/pytorch/audio |
| Encode / decode | FFmpeg | LGPL-2.1 / GPL-2.0 | https://ffmpeg.org |

Wrapper code in this repository is **AGPL-3.0** (see `LICENSE`). None of the baked models carries a
non-commercial restriction.
