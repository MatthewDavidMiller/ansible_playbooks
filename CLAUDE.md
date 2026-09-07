# Claude Code Instructions

The repository's agent instructions are canonical and apply here in full:

@AGENTS.md

Claude Code specifics on top of them:

- `.claude/settings.json` denies reads of `vars.yml`, `env/`, `host_vars/`, and
  `group_vars/`. That deny list is a backstop, not the rule — the rule is that
  secrets and real inventory stay out of anything you read, write, or report.
- Two subagents are defined in `.claude/agents/`: `docs-maintainer` for
  documentation work and `git-commit-writer` for staging and committing a
  logical unit of work. Equivalent definitions for Codex live in
  `.codex/agents/`; when you change one, change its counterpart.
- Run every check through `make` or `./scripts/toolbox.sh`. Do not install
  ansible-core, ansible-lint, yamllint, or shellcheck onto this machine to
  satisfy a gate.
- `make test-full` starts real containers and pulls the locked images; say so
  before running it rather than starting it unannounced.
