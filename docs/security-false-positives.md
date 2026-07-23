# Security audit false positives

Documented dismissals for adversarial-audit (K2.7/K3) findings that are not actionable bugs in this repo's threat model.

## GPU operator trust boundary

RunPod/serverless workers run with operator-configured env, filesystem, and image layers. Findings that assume an external attacker can set bake-time env, modify the container, or swap weight paths are **out of scope**.

## Homelab supply chain at bake

Model weights cloned from Hugging Face at Docker build reflect the operator's chosen revision at bake time. Pinning is via Dockerfile ARG/SHA in deploy templates, not runtime attacker input.

## Record

| Date | Audit | Finding | Rationale |
| --- | --- | --- | --- |
| 2026-07-23 | K3 repo | HF weights cloned without pin at build | Operator bake-time choice; SHA pins in deploy template |
| 2026-07-23 | K3 repo | code-coverage workflow token scopes | Standard org CI pattern; fork PRs capped by `if` guard |
| 2026-07-23 | K3 repo | Unpinned pip deepspeed/resemble-enhance | GPU image rebuild under operator control |
| 2026-07-23 | K3 repo | Error strings echo presigned URLs | **Harden separately** if not already redacted in handler |
