# Container Image Updates

This guide covers the maintained workflow for updating VM1 container images without reintroducing mutable tags into deployment.

## Goal

The deploy path stays pinned to immutable digests in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml). Updating an image means:

1. Change the intended upstream tag in the lock file to the latest **currently eligible** stable tag.
2. Resolve the exact digest with `skopeo`.
3. Require the image's recorded creation time to be at least 48 hours old.
4. Verify the image signature with `cosign` when `signature_required: true` and the lock entry pins the expected signer metadata.
5. Scan the image with `trivy` for fix-available `MEDIUM`, `HIGH`, and `CRITICAL` vulnerabilities.
6. Run the repo's policy and container-hardening tests before deployment.

### Select latest eligible now

Promote the newest stable tag that already satisfies the 48-hour age gate and the rest of this workflow. Do not sleep or otherwise wait for a younger upstream tag to become eligible. Leave younger tags for a later update run, and record that choice in the lock-file `notes` when useful.

Stay on the current major track when a major bump needs a separate procedure (for example PostgreSQL; see [postgres-upgrade.md](postgres-upgrade.md)).

## Tooling

The repo supports two ways to run the review tooling:

- Preferred: install `skopeo`, `cosign`, and `trivy` locally on the control node.
- Fallback: if a tool is missing locally, [`scripts/promote_artifacts.py`](../../scripts/promote_artifacts.py) automatically uses a pinned official container image for that tool through `podman` or `docker`.

Check the current tool path selection with:

```bash
python3 scripts/promote_artifacts.py --check-tools
```

If you want native installs, use the official project instructions:

- `skopeo`: <https://github.com/containers/skopeo/blob/main/install.md>
- `cosign`: <https://docs.sigstore.dev/cosign/system_config/installation/>
- `trivy`: <https://trivy.dev/docs/latest/getting-started/installation/>

## Review Workflow

Edit the target service entry in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml) and change `upstream_ref` and `approved_tag` to the latest currently eligible tag.

For a full review and lock-file update in one pass:

```bash
bash scripts/review_container_updates.sh --service traefik
```

To review multiple services together:

```bash
bash scripts/review_container_updates.sh --service postgres --service redis --service nextcloud
```

That workflow does the following:

1. `python3 scripts/promote_artifacts.py --write ...`
2. `bash scripts/test_supply_chain_policy.sh`
3. `bash scripts/test_container_security.sh`

Trivy findings are written to `logs/container-vulnerability-findings.log`. The `logs/` directory is git ignored so local scan output is easy to inspect without being committed.

For local accepted-risk review, the scanner also honors git-ignored policy files when present:

- `logs/.trivyignore` is passed to Trivy with `--ignorefile`.
- `logs/trivy-vex.json` is passed to Trivy with `--vex`.

Do not commit real accepted CVEs, VEX statements, exposure analysis, or remediation timing. Keep those files under `logs/` and record only public-safe process notes in git.

If you want to inspect the resolved digest before writing it back to the lock file, run the promotion step directly without `--write` first:

```bash
python3 scripts/promote_artifacts.py --service traefik
python3 scripts/promote_artifacts.py --write --service traefik
```

## What To Review

Treat each update as approved only after all of the following are true:

- `skopeo` resolved the expected upstream tag to a digest.
- The candidate image's recorded creation time is at least 48 hours old. Younger images are not eligible for promotion.
- `cosign verify` succeeded for services that require signatures and have pinned signer metadata in the lock file.
- `trivy` reported no fix-available `MEDIUM`, `HIGH`, or `CRITICAL` findings. A maximum-30-day `no_newer_upstream_image` exception may cover non-Critical findings. A Critical finding needs an exact local acceptance unless the same Critical finding is already present in the currently approved image; in that no-regression case, prefer the eligible newer image. Review `logs/container-vulnerability-findings.log`.
- Any local VEX/ignore use is digest-specific, service-specific, time-bounded, and backed by runtime hardening or network containment.
- `scripts/test_supply_chain_policy.sh` passed.
- `scripts/test_container_security.sh` passed against the locked image set. During focused debugging, target affected services with commands like `bash scripts/test_container_security.sh semaphore`.

The container security test now defaults to the digest-pinned refs in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml), so it exercises the same approved images that `vm1.yml` deploys. You can still override individual images with environment variables when needed.

## Vulnerability Exceptions

Use `vulnerability_exception: no_newer_upstream_image` only when Trivy reports fix-available non-Critical findings and no newer eligible stable upstream image is available. Record `vulnerability_exception_reviewed_on` and an expiry no more than 30 days later.

- Keep the exception on the specific digest-pinned lock entry.
- Continue running and retaining the local Trivy findings for review.
- Remove the exception when a newer upstream image passes the scan.
- Do not use the exception for an older image when a newer eligible stable image exists.
- Do not use this public exception to accept a new Critical finding; use the untracked exact-acceptance schema instead.

## Pre-existing Critical Findings

Do not retain an older image solely because an eligible newer image contains the same Critical findings. When a candidate is at least 48 hours old, the promotion tool scans both digests. It may promote the candidate without a new Critical acceptance only when every unaccepted Critical finding in the candidate is also present in the currently approved image. Any new Critical finding still fails closed and requires exact local acceptance.

The `no_newer_upstream_image` exception is still required when the candidate also has fix-available non-Critical findings. This no-regression rule does not hide findings or treat them as remediated; it prevents known inherited findings from blocking an otherwise newer image.

## Signature Exceptions

Use `signature_required: true` only when the lock entry also records the expected signer metadata:

- `signature_identity` or `signature_identity_regexp`
- `signature_oidc_issuer` or `signature_oidc_issuer_regexp`

If an upstream image is unsigned, or you have not yet pinned the signer metadata after review:

- change only that service's `signature_required` field after manual review
- record the reason in the `notes` field
- keep the exception narrow and explicit instead of using `--skip-signature-verify` as the normal workflow

## Deployment

After the review passes, commit the updated lock file and deploy normally:

```bash
ansible-playbook -i inventory.yml vm1.yml -v
```

At runtime, service launchers still use `--pull=never`, so restarts do not silently change image versions.
