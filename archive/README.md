# Archive

This directory holds legacy playbooks, roles, and historical docs that are
intentionally preserved on the separate `archive` branch for reference. The
maintained `main` branch does not carry this directory.

## Rules

- Archived content is not part of the maintained VM1 workflow.
- Do not wire archived playbooks or roles back into active tooling by default.
- Make maintained changes on `main`; treat this branch as read-only history.
- Use archived content for history, examples, or one-off reference only.

## Layout

- `playbooks/` — retired top-level playbooks
- `roles/` — retired role directories
- `docs/` — archived documentation that explains the retired layout
