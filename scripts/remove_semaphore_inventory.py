#!/usr/bin/env python3
"""Remove the retired Semaphore settings from an inventory YAML file.

The edit is textual, so comments, ordering, quoting, and !vault blocks in the
rest of the file stay exactly as they are. Nothing is written until --write is
given, and the script never prints a value from the file: it reports variable
names and line numbers only.

Before writing, it parses the file before and after, applies the same removals
to the parsed original, and refuses to write unless the two agree. It also
refuses if anything left in the file still refers to a variable it would
remove, for example a "{{ semaphore_known_hosts }}" template.

By default it keeps semaphore_database_name and semaphore_db_user, which
retire_semaphore.yml needs to drop the database. Run it again with --all after
that playbook has run.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

import yaml


# Needed by retire_semaphore.yml, so kept until it has run.
CLEANUP_VARS = ("semaphore_database_name", "semaphore_db_user")
REMOVED_VARS = (
    "semaphore_db_password",
    "semaphore_admin_name",
    "semaphore_admin_email",
    "semaphore_admin_password",
    "semaphore_encryption_key",
    "semaphore_known_hosts",
    "semaphore_backup_location",
    "semaphore_egress_network",
    "semaphore_image",
    # From before Semaphore moved into the shared PostgreSQL container; nothing
    # reads them any more, but an older inventory may still carry them.
    "semaphore_postgres_path",
    "semaphore_database_user",
    "semaphore_database_user_password",
)
ROUTE_NETWORK = "semaphore_container_net"
SERVICE_NAMES = {"semaphore", "semaphore.service"}
# Entries removed from named mappings, keyed by the mapping's own name.
DICT_ENTRIES = {
    "route_proxy_network_subnets": {ROUTE_NETWORK},
    "route_proxy_container_ips": {ROUTE_NETWORK},
    "route_proxy_traefik_ips": {ROUTE_NETWORK},
    "container_static_ips": {"semaphore_backend", "semaphore_proxy"},
    "aliases": {"semaphore_backend", "semaphore_proxy", "semaphore_egress"},
}
LIST_ENTRIES = {"reverse_proxy_deferred_route_networks": {ROUTE_NETWORK}}

KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*):(?:\s|$)")
ITEM = re.compile(r"^( *)- ")
BLOCK_SCALAR = re.compile(r"^(?:!\S+\s+)?[|>][-+0-9]*$")
SERVICE_LINE = re.compile(
    r"^(?P<head>\s*container_service_names:\s*)(?P<quote>[\"']?)(?P<value>[^\"'#]*?)(?P=quote)"
    r"(?P<tail>\s+#.*)?\s*$"
)
ROUTE_LINE = re.compile(
    r"^\s*(?:-\s+)?proxy_network:\s*[\"']?" + ROUTE_NETWORK + r"[\"']?\s*(?:#.*)?$"
)


class Refusal(Exception):
    """The file cannot be edited safely; nothing was changed."""


class _Loader(yaml.SafeLoader):
    """Reads Ansible's !vault and other local tags as plain data."""


def _any_tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_Loader.add_multi_constructor("!", _any_tag)


def parse(text: str, what: str):
    try:
        return yaml.load(text, Loader=_Loader)  # noqa: S506 - subclass of SafeLoader
    except yaml.YAMLError as exc:
        raise Refusal(f"the {what} is not valid YAML: {type(exc).__name__}") from None


def indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def is_blank(line: str) -> bool:
    return not line.strip()


def is_comment(line: str) -> bool:
    return line.lstrip().startswith("#")


def remainder(line: str) -> str:
    """What follows the colon of a key line, without a trailing comment."""
    rest = line.split(":", 1)[1].strip()
    return "" if rest.startswith("#") else re.split(r"\s+#", rest, maxsplit=1)[0].strip()


def block_scalar_lines(lines: list[str]) -> set[int]:
    """Lines that are the body of a | or > scalar, which are data, not keys."""
    inside: set[int] = set()
    for i, line in enumerate(lines):
        match = KEY.match(line)
        if match and BLOCK_SCALAR.match(remainder(line)):
            owner = len(match.group("indent"))
            j = i + 1
            while j < len(lines) and (is_blank(lines[j]) or indent(lines[j]) > owner):
                inside.add(j)
                j += 1
    return inside


def block_end(lines: list[str], i: int) -> int:
    """Index after the last line belonging to the key at line i."""
    n = indent(lines[i])
    empty = remainder(lines[i]) == ""
    end = i + 1
    for j in range(i + 1, len(lines)):
        line = lines[j]
        if is_blank(line):
            continue
        if indent(line) > n or (empty and indent(line) == n and ITEM.match(line)):
            end = j + 1
            continue
        break
    return end


def ancestors(lines: list[str], i: int) -> list[str | None]:
    """Names of the enclosing keys of line i, nearest first."""
    n = indent(lines[i])
    names: list[str | None] = []
    j = i - 1
    while j >= 0 and n > 0:
        line = lines[j]
        if line.strip() and not is_comment(line) and indent(line) < n:
            match = KEY.match(line)
            names.append(match.group("key") if match else None)
            n = indent(line)
        j -= 1
    return names


def list_items(lines: list[str], i: int) -> list[tuple[int, int]]:
    """(start, end) of each "- " item under the key at line i."""
    stop = block_end(lines, i)
    starts = [j for j in range(i + 1, stop) if ITEM.match(lines[j])]
    if not starts:
        return []
    level = min(indent(lines[j]) for j in starts)
    starts = [j for j in starts if indent(lines[j]) == level]
    items = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else stop
        # Comments above the next item belong to it, not to this one.
        while end - 1 > start and (
            is_blank(lines[end - 1])
            or (is_comment(lines[end - 1]) and indent(lines[end - 1]) <= level)
        ):
            end -= 1
        items.append((start, end))
    return items


def item_value(line: str) -> str:
    value = re.split(r"\s+#", ITEM.sub("", line, count=1), maxsplit=1)[0].strip()
    return value.strip("\"'")


class Plan:
    def __init__(self, lines: list[str], remove_vars: set[str]):
        self.lines = lines
        self.remove_vars = remove_vars
        self.deleted: set[int] = set()
        self.reports: list[str] = []
        self.parents: dict[int, str] = {}  # line index -> "{}" or "[]"
        self.edits: dict[int, str] = {}
        self.removed_names: set[str] = set()
        self.manual: list[str] = []

    def delete(self, start: int, end: int, label: str, name: str | None = None):
        # A comment block that names Semaphore directly above goes with it.
        while (
            start > 0
            and is_comment(self.lines[start - 1])
            and "semaphore" in self.lines[start - 1].lower()
            and indent(self.lines[start - 1]) == indent(self.lines[start])
        ):
            start -= 1
        self.deleted.update(range(start, end))
        span = f"line {start + 1}" if end - start == 1 else f"lines {start + 1}-{end}"
        self.reports.append(f"{label} ({span})")
        if name:
            self.removed_names.add(name)

    def run(self):
        lines = self.lines
        data = block_scalar_lines(lines)
        for i, line in enumerate(lines):
            if i in data or i in self.deleted:
                continue
            match = KEY.match(line)
            if not match:
                continue
            name = match.group("key")
            if name in self.remove_vars:
                self.delete(i, block_end(lines, i), f"variable {name}", name)
                continue
            chain = ancestors(lines, i)
            parent = chain[0] if chain else None
            if (
                parent in DICT_ENTRIES
                and name in DICT_ENTRIES[parent]
                and (parent != "aliases" or chain[1:2] == ["container_dns"])
            ):
                self.delete(i, block_end(lines, i), f"{parent} entry {name}", name)
                self.parents[ancestor_index(lines, i)] = "{}"
            elif name in LIST_ENTRIES:
                self.prune_list(i, name)
            elif name == "proxy_config":
                self.prune_routes(i)
            elif name == "container_service_names":
                self.prune_services(i)

    def prune_list(self, i: int, name: str):
        for start, end in list_items(self.lines, i):
            if item_value(self.lines[start]) in LIST_ENTRIES[name]:
                self.delete(start, end, f"{name} entry {item_value(self.lines[start])}")
                self.removed_names.add(ROUTE_NETWORK)
                self.parents[i] = "[]"

    def prune_routes(self, i: int):
        for start, end in list_items(self.lines, i):
            body = self.lines[start:end]
            if any(ROUTE_LINE.match(line) for line in body):
                self.delete(start, end, "proxy_config route on semaphore_container_net")
                self.removed_names.update({ROUTE_NETWORK, "semaphore_proxy"})
                self.parents[i] = "[]"
            elif any("semaphore" in line.lower() and not is_comment(line) for line in body):
                self.manual.append(
                    f"proxy_config entry at lines {start + 1}-{end} mentions semaphore "
                    "but is not on semaphore_container_net; check it by hand"
                )

    def prune_services(self, i: int):
        line = self.lines[i]
        if BLOCK_SCALAR.match(remainder(line)):
            body = "\n".join(self.lines[i + 1 : block_end(self.lines, i)]).lower()
            if "semaphore" in body:
                self.manual.append(
                    f"container_service_names at line {i + 1} is a multi-line value that "
                    "names semaphore; edit it by hand"
                )
            return
        match = SERVICE_LINE.match(line)
        if not match:
            return
        tokens = match.group("value").split()
        if not SERVICE_NAMES & set(tokens):
            return
        kept = " ".join(t for t in tokens if t not in SERVICE_NAMES)
        # An emptied plain value would read back as null, not "".
        quote = match.group("quote") or ("" if kept else '"')
        self.edits[i] = f"{match.group('head')}{quote}{kept}{quote}{match.group('tail') or ''}"
        self.reports.append(f"container_service_names entry semaphore (line {i + 1})")

    def apply(self) -> list[str]:
        out = []
        for i, line in enumerate(self.lines):
            if i in self.deleted:
                continue
            if i in self.edits:
                line = self.edits[i]
            elif i in self.parents and self.is_empty_after_delete(i):
                line = mark_empty(line, self.parents[i])
            out.append(line)
        return out

    def is_empty_after_delete(self, i: int) -> bool:
        stop = block_end(self.lines, i)
        return all(
            j in self.deleted or is_blank(self.lines[j]) or is_comment(self.lines[j])
            for j in range(i + 1, stop)
        )


def ancestor_index(lines: list[str], i: int) -> int:
    n = indent(lines[i])
    for j in range(i - 1, -1, -1):
        if lines[j].strip() and not is_comment(lines[j]) and indent(lines[j]) < n:
            return j
    return i


def mark_empty(line: str, empty: str) -> str:
    colon = line.index(":")
    rest = line[colon + 1 :]
    comment = rest[rest.index("#") :] if "#" in rest else ""
    return f"{line[: colon + 1]} {empty}{(' ' + comment) if comment else ''}"


def prune(node, trail: list[str], remove_vars: set[str]):
    """The parsed file with the same removals applied, for comparison."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in remove_vars:
                continue
            if (
                trail
                and key in DICT_ENTRIES.get(trail[-1], ())
                and (trail[-1] != "aliases" or trail[-2:-1] == ["container_dns"])
            ):
                continue
            if key == "container_service_names" and isinstance(value, str):
                if SERVICE_NAMES & set(value.split()):
                    value = " ".join(t for t in value.split() if t not in SERVICE_NAMES)
            elif key == "proxy_config" and isinstance(value, list):
                value = [
                    item
                    for item in value
                    if not (isinstance(item, dict) and item.get("proxy_network") == ROUTE_NETWORK)
                ]
            elif key in LIST_ENTRIES and isinstance(value, list):
                value = [item for item in value if item not in LIST_ENTRIES[key]]
            out[key] = prune(value, trail + [str(key)], remove_vars)
        return out
    if isinstance(node, list):
        return [prune(item, trail, remove_vars) for item in node]
    return node


def plan_edit(text: str, remove_all: bool):
    remove_vars = set(REMOVED_VARS) | (set(CLEANUP_VARS) if remove_all else set())
    original = parse(text, "inventory file")
    if not isinstance(original, dict):
        raise Refusal("the inventory file is not a YAML mapping")
    plan = Plan(text.split("\n"), remove_vars)
    plan.run()
    new_text = "\n".join(plan.apply())

    updated = parse(new_text, "edited inventory")
    if updated != prune(original, [], remove_vars):
        raise Refusal(
            "the edited file does not match the expected result; the file uses a layout "
            "this script does not handle (flow style, quoted keys, or similar). "
            "Edit it by hand using docs/guides/playbook-runner-migration.md, section 4."
        )

    names = sorted(plan.removed_names | remove_vars & set(re.findall(r"semaphore_\w+", text)))
    leftovers = []
    for number, line in enumerate(new_text.split("\n"), start=1):
        if is_comment(line):
            continue
        for name in names:
            if re.search(rf"\b{re.escape(name)}\b", line):
                leftovers.append(f"line {number} still refers to {name}")
    if leftovers:
        raise Refusal(
            "not changed, because what remains would break:\n  "
            + "\n  ".join(leftovers)
            + "\nRemove or replace those references, then run this again."
        )
    return plan, new_text


def mentions_left(new_text: str) -> list[str]:
    kept = set(CLEANUP_VARS)
    found = []
    for number, line in enumerate(new_text.split("\n"), start=1):
        if "semaphore" not in line.lower() or is_comment(line):
            continue
        match = KEY.match(line)
        if match and match.group("key") in kept:
            continue
        found.append(f"line {number}")
    return found


def write_atomically(path: Path, new_text: str, backup: bool) -> Path | None:
    target = path.resolve()
    mode = target.stat().st_mode & 0o777
    saved = None
    if backup:
        saved = target.with_name(
            f"{target.name}.semaphore-removal-{time.strftime('%Y%m%d-%H%M%S')}.bak"
        )
        shutil.copyfile(target, saved)
        os.chmod(saved, 0o600)
    fd, temp = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(new_text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, target)
    except BaseException:
        if os.path.exists(temp):
            os.unlink(temp)
        raise
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("inventory", type=Path, help="the inventory YAML file to edit")
    parser.add_argument("--write", action="store_true", help="apply the changes (default: preview only)")
    parser.add_argument(
        "--all",
        action="store_true",
        help="also remove semaphore_database_name and semaphore_db_user (run after retire_semaphore.yml)",
    )
    parser.add_argument("--no-backup", action="store_true", help="do not keep a 0600 copy of the original")
    args = parser.parse_args(argv)

    path: Path = args.inventory
    if not path.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return 1
    try:
        text = path.read_text(encoding="utf-8")
        plan, new_text = plan_edit(text, args.all)
    except (Refusal, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not plan.reports and not plan.manual:
        print("Nothing to remove.")
        return 0
    verb = "Removed" if args.write else "Would remove"
    for report in plan.reports:
        print(f"{verb}: {report}")
    for note in plan.manual:
        print(f"Check by hand: {note}")
    for line in mentions_left(new_text):
        print(f"Check by hand: {line} still mentions semaphore")
    if not plan.reports:
        return 2 if plan.manual else 0

    if not args.write:
        print("Preview only. Run again with --write to apply.")
        return 0
    saved = write_atomically(path, new_text, backup=not args.no_backup)
    if saved:
        print(f"Original kept at {saved} (mode 0600, holds the same secrets); delete it once you have checked the result.")
    return 2 if plan.manual else 0


if __name__ == "__main__":
    sys.exit(main())
