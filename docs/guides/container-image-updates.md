# Container Image Updates

This guide covers the maintained workflow for updating VM1 container images without reintroducing mutable tags into deployment.

## Goal

The deploy path stays pinned to immutable digests in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml). Updating an image means:

1. Change the intended upstream tag in the lock file.
2. Resolve the exact digest with `skopeo`.
3. Verify the image signature with `cosign` when `signature_required: true` and the lock entry pins the expected signer metadata.
4. Scan the image with `trivy`.
5. Run the repo's policy and container-hardening tests before deployment.

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

Edit the target service entry in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml) and change `upstream_ref` and `approved_tag` to the new tag you want to review.

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

If you want to inspect the resolved digest before writing it back to the lock file, run the promotion step directly without `--write` first:

```bash
python3 scripts/promote_artifacts.py --service traefik
python3 scripts/promote_artifacts.py --write --service traefik
```

## What To Review

Treat each update as approved only after all of the following are true:

- `skopeo` resolved the expected upstream tag to a digest.
- `cosign verify` succeeded for services that require signatures and have pinned signer metadata in the lock file.
- `trivy` reported no `HIGH` or `CRITICAL` findings.
- `scripts/test_supply_chain_policy.sh` passed.
- `scripts/test_container_security.sh` passed against the locked image set.

The container security test now defaults to the digest-pinned refs in [`artifacts/containers.lock.yml`](../../artifacts/containers.lock.yml), so it exercises the same approved images that `vm1.yml` deploys. You can still override individual images with environment variables when needed.

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
