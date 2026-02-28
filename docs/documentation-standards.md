# Documentation Standards

Standards for authoring and maintaining documentation in the `docs/` directory.

---

## Core Principle: No Duplication

Never copy content from another file — link to it. If the same fact appears in two places, one of them must be a reference to the other.

Authoritative sources that docs must reference rather than repeat:
- `CLAUDE.md` — running playbooks, architecture patterns, role conventions
- `README.md` — top-level project overview
- `example_inventory.yml` — inventory structure and example values
- Role task files — what a role actually does

---

## File Organization

- Documentation files live under `docs/` and use kebab-case names (e.g., `getting-started.md`)
- Role reference docs go under `docs/roles/`
- How-to guides go under `docs/guides/`
- `docs/index.md` is the navigation hub — update it when adding new docs files

---

## Variable Tables

Use this column order for variable reference tables:

| Variable | Type | Required | Description | Example |
|---|---|---|---|---|

- **Required** variables are listed first, optional variables after
- **Type** values: `string`, `list`, `integer`, `boolean`, `path` (absolute filesystem path)
- **Example** values should use `example.com`, `example_user`, `/path/to/...`, or other obviously placeholder values

---

## Role Documentation Format

Each role entry in `docs/roles/*.md` follows this structure:

```
### `role_name`

Brief one-sentence purpose.

**Distributions:** Rocky Linux 10 / Debian 12 / Arch Linux (list which apply)

**Required variables:**

| Variable | Type | Description | Example |
|---|---|---|---|
| ... | ... | ... | ... |

**Templates:**

| Template | Destination | Description |
|---|---|---|
| ... | ... | ... |

**Notable tasks:** (brief bullet list, only when not self-evident from purpose)
```

---

## Playbook Documentation Format

Each playbook entry in `docs/playbooks.md` follows this structure:

```
### `playbook.yml`

**Target:** `host_group`

**Roles (in order):** role1 → role2 → role3 → ...

**Usage:** When to run this playbook (one or two sentences).

**Notes:** Any caveats or special behavior (omit if none).
```

---

## Guide Format

Guides use numbered steps for sequential procedures and bullet lists for non-ordered options. Cross-references use relative Markdown links. Guides describe *what to do*; for *why things work the way they do*, link to the relevant reference document instead.

---

## Tone and Style

- Second person ("you"), imperative mood for steps ("Run the playbook", not "The playbook should be run")
- Present tense for descriptions ("The role installs...", not "The role will install...")
- No emojis
- No time estimates

---

## Update Policy

Documentation is updated in the same commit as the code changes it describes. A code change that affects role variables, playbook structure, or inventory conventions requires a corresponding docs update before the commit is complete.
