# Third-Party Notices -- vivijure-audio-upscale

The wrapper code in this repository (the RunPod handler and Dockerfile) is licensed under
**AGPL-3.0** (see `LICENSE`).

The Docker image this repository builds **incorporates and redistributes** the following
third-party software and pretrained model weights, each under its own license. None carries a
non-commercial restriction.

| Component | Author / Source | License | Notes |
|---|---|---|---|
| resemble-enhance (code + weights) | Resemble AI -- https://github.com/resemble-ai/resemble-enhance | MIT | Speech enhancement engine; weights baked (HF ResembleAI/resemble-enhance, License: mit). |
| PyTorch | https://github.com/pytorch/pytorch | BSD-3-Clause | Provided by the base image. |
| torchaudio | https://github.com/pytorch/audio | BSD-2-Clause | Audio I/O + transforms. |
| FFmpeg | https://ffmpeg.org | LGPL-2.1 / GPL-2.0 | Audio decode/encode; invoked as a subprocess. |

resemble-enhance pulls additional permissive Python dependencies (e.g. librosa -- ISC; numpy,
omegaconf -- BSD/MIT); their licenses live at their respective project pages. The authoritative
copyright line and full license for each component live at its source URL above. Full license texts:
AGPL-3.0 -> `LICENSE`. The MIT and BSD templates that govern the components above are reproduced
below (each component retains its own upstream copyright notice).

---

## MIT License

```
MIT License

Copyright (c) 2023 Resemble AI (resemble-enhance), retaining its own notice.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## BSD Licenses (PyTorch -- BSD-3-Clause; torchaudio -- BSD-2-Clause)

```
Copyright (c) the PyTorch and torchaudio authors, each retaining its own upstream notice.

Redistribution and use in source and binary forms, with or without modification, are permitted
provided that the conditions of the respective BSD license (3-Clause for PyTorch, 2-Clause for
torchaudio) are met, including retention of the above copyright notice, this list of conditions,
and the following disclaimer.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
IMPLIED WARRANTIES ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES HOWEVER CAUSED
AND ON ANY THEORY OF LIABILITY ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE.
```
