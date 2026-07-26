# Archive

Legacy playbooks, roles, and docs are preserved on the separate `archive`
branch. They are absent from `main`, are not part of the maintained workflow,
and should not drive new changes or tests.

## Browse Without Switching Branches

```bash
git show archive:archive/README.md
git ls-tree -r --name-only archive archive/
git show archive:archive/playbooks/<playbook>.yml
```

## Work On The Historical Snapshot

Use a worktree when you need the archived files alongside `main`:

```bash
git worktree add ../ansible_playbooks_archive archive
```

The branch is a historical reference. New maintained work belongs on `main`.
