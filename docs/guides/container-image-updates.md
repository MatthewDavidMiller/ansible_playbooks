# Container Image Updates

This guide covers the maintained workflow for updating VM1 container images without reintroducing mutable tags into deployment.

## Goal

The deploy path stays pinned to immutable digests in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml). Updating images means running the review; the tool selects the version itself:

1. List the upstream tags and select the newest release of the major line already pinned.
2. Resolve the exact digest with `skopeo`.
3. Require a changed image's recorded creation time to be at least 24 hours old, unless it is a [first-party image](#first-party-images).
4. Verify the image signature with `cosign` when `signature_required: true` and the lock entry pins the expected signer metadata.
5. Scan the image with `trivy` for fix-available `MEDIUM`, `HIGH`, and `CRITICAL` vulnerabilities, and fail only on a Critical the current digest does not already have.
6. Write the tag and digest back, then run the repo's policy and container-hardening tests before deployment.

```bash
./scripts/toolbox.sh python3 scripts/promote_artifacts.py --write
```

### The tool picks the version

`approved_tag` is an output, not an input. Editing a tag by hand only matters when you want something the selection will not pick, and `--keep-pinned-tag` reviews exactly what the lock already names.

Selection is deliberately narrow. A candidate must share the current tag's exact shape — same prefix, same number of components — because registries publish `17.11` beside `17.11.0` and `v3.7.13` beside `3.7.13`, and mixing spellings would make the result depend on which variants a registry happens to carry. Anything that is not a plain dotted version (`latest`, `stable`, `3.0.5-rc1`, `34.0.3-apache`) is never a candidate.

### Major versions are held back

The tool never crosses a major. It reports newer majors as `held-back` and stays on the pinned line, because a major is where upstream may break the configuration these roles render — Paperless 3.0 required a new `PAPERLESS_SECRET_KEY`, and PostgreSQL majors need the whole procedure in [postgres-upgrade.md](postgres-upgrade.md).

Taking one is a deliberate act: edit `upstream_ref` and `approved_tag` to the new major, run the review, then run `make test-full` so the runtime container tests start the image for real before it reaches VM1.

### First-party images

Images this project builds and releases itself — currently only
`ghcr.io/matthewdavidmiller/playbook-runner` — are exempt from the 24-hour
age gate. The gate exists so the wider community has a day to catch a
compromised or broken third-party release before VM1 runs it; for our own
image there is no upstream to wait on, and the release is already gated by
its repository's full test suite and by its runtime tests under VM1's
container flags (`make release` runs both before it pushes).

The exemption is explicit and narrow. A lock entry opts in with
`first_party: true`, and the review tool refuses that flag on any image
outside `FIRST_PARTY_IMAGE_PREFIXES` in `scripts/promote_artifacts.py`
(`ghcr.io/matthewdavidmiller/`), so a third-party image cannot be exempted
by mistake. Everything else still applies to first-party images: digest
pinning, the Trivy scan and its no-new-Critical rule, and the runtime tests.

## Tooling

The repo supports two ways to run the review tooling:

- Preferred: install `skopeo`, `cosign`, and `trivy` locally on the control node.
- Fallback: if a tool is missing locally, [`scripts/promote_artifacts.py`](../../scripts/promote_artifacts.py) automatically uses a pinned official container image for that tool through `podman`.

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
- The candidate image's recorded creation time is at least 24 hours old. Younger images are not eligible for promotion. First-party images are exempt; see below.
- `cosign verify` succeeded for services that require signatures and have pinned signer metadata in the lock file.
- `trivy` introduced no Critical finding that the digest being replaced did not already carry. Remaining findings are reported, not blocking — review `logs/container-vulnerability-findings.log` and see [container-vulnerability-policy.md](container-vulnerability-policy.md) for why currency wins over standing findings.
- Any local VEX/ignore use is digest-specific, service-specific, time-bounded, and backed by runtime hardening or network containment.
- `scripts/test_supply_chain_policy.sh` passed.
- `scripts/test_container_security.sh` passed against the locked image set. During focused debugging, target affected services with commands like `bash scripts/test_container_security.sh semaphore`.

The container security test now defaults to the digest-pinned refs in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml), so it exercises the same approved images that `vm1.yml` deploys. You can still override individual images with environment variables when needed.

## Pre-existing And New Critical Findings

Do not retain an older image because a newer one carries the same findings. When a candidate is at least 24 hours old, the promotion tool scans both digests and promotes without a new acceptance whenever every unaccepted Critical finding in the candidate is also present in the currently approved image.

A Critical the candidate *introduces* fails closed and requires an exact local acceptance in the untracked schema. That is the one finding-based block left; non-Critical findings never stop a promotion.

A service already on the newest release of its major reports `scan=STANDING` with its Critical IDs on every run. There is nothing to promote to, so the finding is surfaced rather than converted into a block that no update could clear.

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
