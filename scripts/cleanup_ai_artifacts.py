#!/usr/bin/env python3
"""Clean AI-generated clutter and common tool caches from a workspace."""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


LOW_RISK_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".vite",
    ".turbo",
    ".parcel-cache",
}

LOW_RISK_FILE_PATTERNS = (
    "*.pyc",
    "*.pyo",
    "*.tmp",
    "*.bak",
    ".codex-dev*.log",
    "codex-dev*.log",
)

HIGH_RISK_DIR_NAMES = {
    "dist",
    "build",
    "coverage",
}

HIGH_RISK_NAME_PATTERNS = (
    "generated-*",
    "ai-output-*",
    "ai_output_*",
    "preview-*.html",
    "*preview*.html",
    "*screenshot*.png",
    "*screenshot*.jpg",
    "*report*.html",
)

PROTECTED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
}


@dataclass(frozen=True)
class CleanupItem:
    relative_path: str
    risk: str
    kind: str
    reason: str
    action: str = "pending"


@dataclass(frozen=True)
class CleanupReport:
    root: str
    items: list[CleanupItem]
    deleted_count: int
    low_risk_count: int
    high_risk_count: int
    skipped_count: int

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "deleted_count": self.deleted_count,
            "low_risk_count": self.low_risk_count,
            "high_risk_count": self.high_risk_count,
            "skipped_count": self.skipped_count,
            "items": [asdict(item) for item in self.items],
        }


def scan_workspace(root: str | Path) -> list[CleanupItem]:
    workspace = resolve_workspace(root)
    tracked = git_tracked_paths(workspace)
    candidates: list[CleanupItem] = []
    candidate_dirs: list[Path] = []

    for path in sorted(workspace.rglob("*")):
        if should_prune(path, workspace):
            continue

        rel = relative_posix(path, workspace)
        if is_protected_file(path, workspace):
            candidates.append(CleanupItem(rel, "protected", "file", "protected secret/config file", "skipped"))
            continue

        if rel in tracked:
            continue

        if any(is_relative_to(path, parent) for parent in candidate_dirs):
            continue

        item = classify_path(path, workspace)
        if item is None:
            continue

        if path.is_dir():
            tracked_descendants = sorted(
                tracked_path for tracked_path in tracked if tracked_path == item.relative_path or tracked_path.startswith(f"{item.relative_path}/")
            )
            if tracked_descendants:
                candidates.extend(
                    CleanupItem(tracked_path, "protected", "file", "git tracked file inside candidate", "skipped")
                    for tracked_path in tracked_descendants
                )
                continue
            candidate_dirs.append(path)

        candidates.append(item)

    return dedupe_items(candidates)


def cleanup_workspace(
    root: str | Path,
    *,
    dry_run: bool = True,
    include_high_risk: bool = False,
) -> CleanupReport:
    workspace = resolve_workspace(root)
    scanned_items = scan_workspace(workspace)
    completed: list[CleanupItem] = []
    deleted_count = 0

    for item in scanned_items:
        path = (workspace / item.relative_path).resolve()

        if item.action == "skipped":
            completed.append(item)
            continue

        if not is_relative_to(path, workspace):
            completed.append(replace_action(item, "skipped", "path outside workspace"))
            continue

        if item.risk == "high" and not include_high_risk:
            completed.append(replace_action(item, "needs_confirmation"))
            continue

        if dry_run:
            completed.append(replace_action(item, "would_delete"))
            continue

        delete_path(path)
        deleted_count += 1
        completed.append(replace_action(item, "deleted"))

    return CleanupReport(
        root=str(workspace),
        items=completed,
        deleted_count=deleted_count,
        low_risk_count=sum(1 for item in completed if item.risk == "low"),
        high_risk_count=sum(1 for item in completed if item.risk == "high"),
        skipped_count=sum(1 for item in completed if item.action == "skipped"),
    )


def classify_path(path: Path, workspace: Path) -> CleanupItem | None:
    rel = relative_posix(path, workspace)
    name = path.name
    kind = "dir" if path.is_dir() else "file"

    if path.is_dir() and name in LOW_RISK_DIR_NAMES:
        return CleanupItem(rel, "low", kind, f"common tool cache directory: {name}")

    if is_next_cache_dir(path, workspace):
        return CleanupItem(rel, "low", kind, "Next.js cache directory")

    if path.is_file() and matches_any(name, LOW_RISK_FILE_PATTERNS):
        return CleanupItem(rel, "low", kind, "temporary/cache file pattern")

    if path.is_dir() and name in HIGH_RISK_DIR_NAMES:
        return CleanupItem(rel, "high", kind, f"build or report output directory: {name}")

    if is_superpowers_generated_doc(path, workspace):
        return CleanupItem(rel, "high", kind, "untracked Superpowers plan/spec candidate")

    if matches_any(name, HIGH_RISK_NAME_PATTERNS):
        return CleanupItem(rel, "high", kind, "AI/generated preview artifact pattern")

    return None


def resolve_workspace(root: str | Path) -> Path:
    workspace = Path(root).expanduser().resolve()
    if not workspace.exists():
        raise FileNotFoundError(f"Workspace does not exist: {workspace}")
    if not workspace.is_dir():
        raise NotADirectoryError(f"Workspace is not a directory: {workspace}")
    return workspace


def git_tracked_paths(workspace: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(workspace), "ls-files", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()

    raw = result.stdout.decode("utf-8", errors="replace")
    return {entry.replace("\\", "/") for entry in raw.split("\0") if entry}


def should_prune(path: Path, workspace: Path) -> bool:
    rel_parts = path.relative_to(workspace).parts
    return any(part in PROTECTED_DIR_NAMES for part in rel_parts[:-1])


def is_protected_file(path: Path, workspace: Path) -> bool:
    if not path.is_file():
        return False
    rel = relative_posix(path, workspace)
    name = path.name
    return name == ".env" or name.startswith(".env.") or rel == ".env.local"


def is_next_cache_dir(path: Path, workspace: Path) -> bool:
    if not path.is_dir() or path.name != "cache":
        return False
    parts = path.relative_to(workspace).parts
    return len(parts) >= 2 and parts[-2] == ".next"


def is_superpowers_generated_doc(path: Path, workspace: Path) -> bool:
    if not path.is_file():
        return False
    rel_parts = path.relative_to(workspace).parts
    return len(rel_parts) >= 4 and (
        rel_parts[0:3] == ("docs", "superpowers", "plans")
        or rel_parts[0:3] == ("docs", "superpowers", "specs")
    )


def matches_any(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def dedupe_items(items: list[CleanupItem]) -> list[CleanupItem]:
    by_path: dict[str, CleanupItem] = {}
    for item in items:
        previous = by_path.get(item.relative_path)
        if previous is None or risk_rank(item.risk) > risk_rank(previous.risk):
            by_path[item.relative_path] = item
    return sorted(by_path.values(), key=lambda item: item.relative_path)


def risk_rank(risk: str) -> int:
    return {"low": 1, "high": 2, "protected": 3}.get(risk, 0)


def relative_posix(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace).as_posix()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def replace_action(item: CleanupItem, action: str, reason: str | None = None) -> CleanupItem:
    return CleanupItem(
        relative_path=item.relative_path,
        risk=item.risk,
        kind=item.kind,
        reason=reason or item.reason,
        action=action,
    )


def delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def print_text_report(report: CleanupReport) -> None:
    print(f"Workspace: {report.root}")
    print(
        f"Items: low={report.low_risk_count} high={report.high_risk_count} "
        f"skipped={report.skipped_count} deleted={report.deleted_count}"
    )
    for item in report.items:
        print(f"- [{item.risk}] {item.action}: {item.relative_path} ({item.reason})")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean AI-generated artifacts and common caches safely.")
    parser.add_argument("workspace", nargs="?", default=".", help="Workspace root to scan. Defaults to current directory.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview all actions without deleting anything.")
    mode.add_argument("--apply", action="store_true", help="Delete low-risk items and preview high-risk items.")
    parser.add_argument(
        "--include-high-risk",
        action="store_true",
        help="With --apply, also delete high-risk candidates. Use only after reviewing a dry run.",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    dry_run = not args.apply or args.dry_run

    report = cleanup_workspace(
        args.workspace,
        dry_run=dry_run,
        include_high_risk=args.include_high_risk,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print_text_report(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
