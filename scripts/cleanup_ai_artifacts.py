#!/usr/bin/env python3
"""Clean AI-generated clutter and common tool caches from a workspace."""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import shutil
import subprocess
import sys
import zipfile
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
    ".ai-cleanup-trash",
}

DEFAULT_CONFIG_FILES = (".ai-cleanup.json", ".ai-cleanup.yml", ".ai-cleanup.yaml")


@dataclass(frozen=True)
class CleanupItem:
    relative_path: str
    risk: str
    kind: str
    reason: str
    action: str = "pending"


@dataclass(frozen=True)
class CleanupConfig:
    protect_patterns: tuple[str, ...] = ()
    low_risk_patterns: tuple[str, ...] = ()
    high_risk_patterns: tuple[str, ...] = ()
    package_exclude_patterns: tuple[str, ...] = ()
    package_include_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class CleanupReport:
    root: str
    items: list[CleanupItem]
    deleted_count: int
    quarantined_count: int
    low_risk_count: int
    high_risk_count: int
    skipped_count: int

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "deleted_count": self.deleted_count,
            "quarantined_count": self.quarantined_count,
            "low_risk_count": self.low_risk_count,
            "high_risk_count": self.high_risk_count,
            "skipped_count": self.skipped_count,
            "items": [asdict(item) for item in self.items],
        }


def scan_workspace(root: str | Path, config: CleanupConfig | None = None) -> list[CleanupItem]:
    workspace = resolve_workspace(root)
    cleanup_config = config or load_config(workspace)
    tracked = git_tracked_paths(workspace)
    candidates: list[CleanupItem] = []
    candidate_dirs: list[Path] = []

    for path in sorted(workspace.rglob("*")):
        if should_prune(path, workspace):
            continue

        rel = relative_posix(path, workspace)
        if is_config_protected(path, workspace, cleanup_config):
            candidates.append(CleanupItem(rel, "protected", "dir" if path.is_dir() else "file", "protected by project config", "skipped"))
            continue

        if is_protected_file(path, workspace):
            candidates.append(CleanupItem(rel, "protected", "file", "protected secret/config file", "skipped"))
            continue

        if rel in tracked:
            continue

        if any(is_relative_to(path, parent) for parent in candidate_dirs):
            continue

        item = classify_path(path, workspace, cleanup_config)
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
    quarantine_dir: str | Path | None = None,
    config: CleanupConfig | None = None,
) -> CleanupReport:
    workspace = resolve_workspace(root)
    cleanup_config = config or load_config(workspace)
    scanned_items = scan_workspace(workspace, cleanup_config)
    quarantine_root = resolve_quarantine_dir(workspace, quarantine_dir) if quarantine_dir else None
    completed: list[CleanupItem] = []
    deleted_count = 0
    quarantined_count = 0

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

        if quarantine_root:
            quarantine_path(path, workspace, quarantine_root)
            quarantined_count += 1
            completed.append(replace_action(item, "quarantined"))
            continue

        delete_path(path)
        deleted_count += 1
        completed.append(replace_action(item, "deleted"))

    return CleanupReport(
        root=str(workspace),
        items=completed,
        deleted_count=deleted_count,
        quarantined_count=quarantined_count,
        low_risk_count=sum(1 for item in completed if item.risk == "low"),
        high_risk_count=sum(1 for item in completed if item.risk == "high"),
        skipped_count=sum(1 for item in completed if item.action == "skipped"),
    )


def classify_path(path: Path, workspace: Path, config: CleanupConfig | None = None) -> CleanupItem | None:
    rel = relative_posix(path, workspace)
    name = path.name
    kind = "dir" if path.is_dir() else "file"
    cleanup_config = config or CleanupConfig()

    if matches_path(rel, name, cleanup_config.high_risk_patterns):
        return CleanupItem(rel, "high", kind, "high-risk pattern from project config")

    if matches_path(rel, name, cleanup_config.low_risk_patterns):
        return CleanupItem(rel, "low", kind, "low-risk pattern from project config")

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


def load_config(workspace: Path) -> CleanupConfig:
    data: dict[str, list[str]] = {}
    for name in DEFAULT_CONFIG_FILES:
        path = workspace / name
        if not path.exists() or not path.is_file():
            continue
        loaded = load_config_file(path)
        for key, values in loaded.items():
            data.setdefault(key, []).extend(values)

    return CleanupConfig(
        protect_patterns=tuple(data.get("protect", ())),
        low_risk_patterns=tuple(data.get("low_risk", ())),
        high_risk_patterns=tuple(data.get("high_risk", ())),
        package_exclude_patterns=tuple(data.get("package_exclude", ())),
        package_include_patterns=tuple(data.get("package_include", ())),
    )


def load_config_file(path: Path) -> dict[str, list[str]]:
    if path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = parse_simple_yaml_lists(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for key in ("protect", "low_risk", "high_risk", "package_exclude", "package_include"):
        value = payload.get(key, [])
        if isinstance(value, str):
            normalized[key] = [value]
        elif isinstance(value, list):
            normalized[key] = [str(item) for item in value if str(item).strip()]
    return normalized


def parse_simple_yaml_lists(text: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1].strip()
            parsed.setdefault(current_key, [])
            continue
        if current_key and line.lstrip().startswith("- "):
            value = line.lstrip()[2:].strip().strip("\"'")
            if value:
                parsed.setdefault(current_key, []).append(value)
    return parsed


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


def is_config_protected(path: Path, workspace: Path, config: CleanupConfig) -> bool:
    rel = relative_posix(path, workspace)
    return matches_path(rel, path.name, config.protect_patterns)


def matches_path(relative_path: str, name: str, patterns: Iterable[str]) -> bool:
    return any(
        fnmatch.fnmatch(relative_path, pattern)
        or fnmatch.fnmatch(name, pattern)
        or (pattern.endswith("/**") and relative_path == pattern[:-3])
        for pattern in patterns
    )


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


def resolve_quarantine_dir(workspace: Path, quarantine_dir: str | Path) -> Path:
    raw = Path(quarantine_dir)
    quarantine = raw if raw.is_absolute() else workspace / raw
    quarantine = quarantine.expanduser().resolve()
    if not is_relative_to(quarantine, workspace):
        raise ValueError(f"Quarantine directory must stay inside workspace: {quarantine}")
    return quarantine


def quarantine_path(path: Path, workspace: Path, quarantine_root: Path) -> Path:
    relative_path = path.resolve().relative_to(workspace)
    destination = unique_destination(quarantine_root / relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(destination))
    return destination


def unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(1, 10_000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find free quarantine destination for {path}")


def delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def create_clean_package(
    root: str | Path,
    output_path: str | Path,
    *,
    config: CleanupConfig | None = None,
) -> dict:
    workspace = resolve_workspace(root)
    cleanup_config = config or load_config(workspace)
    package_path = Path(output_path).expanduser()
    if not package_path.is_absolute():
        package_path = workspace / package_path
    package_path = package_path.resolve()
    if package_path.exists() and package_path.is_dir():
        raise IsADirectoryError(f"Package path is a directory: {package_path}")
    package_path.parent.mkdir(parents=True, exist_ok=True)

    excluded_map = package_exclusion_map(workspace, cleanup_config, package_path)
    included: list[str] = []

    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        rel = relative_posix(path, workspace)
        if path.resolve() == package_path or should_exclude_from_package(path, workspace, cleanup_config, excluded_map):
            continue
        included.append(rel)

    manifest = {
        "schema_version": 1,
        "created_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "root": str(workspace),
        "package": str(package_path),
        "included_count": len(included),
        "excluded_count": len(excluded_map),
        "included": included,
        "excluded": [asdict(item) for item in sorted(excluded_map.values(), key=lambda item: item.relative_path)],
    }

    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel in included:
            archive.write(workspace / rel, rel)
        archive.writestr("cleanup-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return manifest


def package_exclusion_map(workspace: Path, config: CleanupConfig, package_path: Path) -> dict[str, CleanupItem]:
    excluded: dict[str, CleanupItem] = {}
    package_rel = relative_posix(package_path, workspace) if is_relative_to(package_path, workspace) and package_path.exists() else None
    if package_rel:
        excluded[package_rel] = CleanupItem(package_rel, "protected", "file", "package output file", "excluded")

    for item in scan_workspace(workspace, config):
        excluded[item.relative_path] = replace_action(item, "excluded")

    for path in sorted(workspace.rglob("*")):
        rel = relative_posix(path, workspace)
        kind = "dir" if path.is_dir() else "file"
        if should_prune(path, workspace):
            protected_root = protected_root_for(path, workspace)
            if protected_root and protected_root not in excluded:
                excluded[protected_root] = CleanupItem(protected_root, "protected", "dir", "protected runtime or dependency directory", "excluded")
            continue
        if matches_path(rel, path.name, config.package_exclude_patterns):
            excluded[rel] = CleanupItem(rel, "high", kind, "package exclude pattern from project config", "excluded")

    return excluded


def should_exclude_from_package(
    path: Path,
    workspace: Path,
    config: CleanupConfig,
    excluded_map: dict[str, CleanupItem],
) -> bool:
    rel = relative_posix(path, workspace)
    if should_prune(path, workspace) or is_protected_file(path, workspace) or is_config_protected(path, workspace, config):
        return True
    if matches_path(rel, path.name, config.package_exclude_patterns):
        return True
    return any(rel == item.relative_path or rel.startswith(f"{item.relative_path}/") for item in excluded_map.values())


def protected_root_for(path: Path, workspace: Path) -> str | None:
    rel_parts = path.relative_to(workspace).parts
    for index, part in enumerate(rel_parts):
        if part in PROTECTED_DIR_NAMES:
            return Path(*rel_parts[: index + 1]).as_posix()
    return None


def write_markdown_report(report: CleanupReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AI Artifact Cleanup Report",
        "",
        f"- Workspace: `{report.root}`",
        (
            f"- Counts: low={report.low_risk_count} high={report.high_risk_count} "
            f"skipped={report.skipped_count} deleted={report.deleted_count} quarantined={report.quarantined_count}"
        ),
        "",
        "| Risk | Action | Path | Reason |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.items:
        lines.append(f"| {item.risk} | {item.action} | `{item.relative_path}` | {item.reason} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def explain_path(root: str | Path, target: str | Path, *, config: CleanupConfig | None = None) -> CleanupItem:
    workspace = resolve_workspace(root)
    cleanup_config = config or load_config(workspace)
    raw = Path(target)
    path = raw if raw.is_absolute() else workspace / raw
    path = path.expanduser().resolve()
    if not is_relative_to(path, workspace):
        raise ValueError(f"Path is outside workspace: {path}")

    rel = relative_posix(path, workspace)
    kind = "dir" if path.is_dir() else "file"
    tracked = git_tracked_paths(workspace)
    if should_prune(path, workspace):
        return CleanupItem(rel, "protected", kind, "inside protected runtime or dependency directory", "skipped")
    if is_config_protected(path, workspace, cleanup_config):
        return CleanupItem(rel, "protected", kind, "protected by project config", "skipped")
    if is_protected_file(path, workspace):
        return CleanupItem(rel, "protected", kind, "protected secret/config file", "skipped")
    if rel in tracked:
        return CleanupItem(rel, "protected", kind, "git tracked file", "skipped")

    item = classify_path(path, workspace, cleanup_config)
    if item:
        return item
    return CleanupItem(rel, "none", kind, "no cleanup rule matched", "kept")


def print_text_report(report: CleanupReport) -> None:
    print(f"Workspace: {report.root}")
    print(
        f"Items: low={report.low_risk_count} high={report.high_risk_count} "
        f"skipped={report.skipped_count} deleted={report.deleted_count} "
        f"quarantined={report.quarantined_count}"
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
    parser.add_argument(
        "--quarantine",
        nargs="?",
        const=".ai-cleanup-trash",
        help="Move eligible cleanup items into a workspace quarantine directory instead of deleting them.",
    )
    parser.add_argument("--package", help="Create a clean ZIP package at the given path without mutating the workspace.")
    parser.add_argument("--report", help="Write a Markdown cleanup report to the given path.")
    parser.add_argument("--explain", help="Explain how one workspace path is classified.")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON report.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    dry_run = not args.apply or args.dry_run

    if args.explain:
        item = explain_path(args.workspace, args.explain)
        if args.json:
            print(json.dumps(asdict(item), ensure_ascii=False, indent=2))
        else:
            print(f"{item.relative_path}: risk={item.risk} action={item.action} reason={item.reason}")
        return 0

    report = cleanup_workspace(
        args.workspace,
        dry_run=dry_run,
        include_high_risk=args.include_high_risk,
        quarantine_dir=args.quarantine,
    )

    manifest = None
    if args.report:
        write_markdown_report(report, args.report)
    if args.package:
        manifest = create_clean_package(args.workspace, args.package)

    if args.json:
        payload: dict[str, object] = {"cleanup": report.to_dict()}
        if manifest:
            payload["package"] = manifest
        print(json.dumps(payload if (args.report or args.package) else report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
        if args.report:
            print(f"Report written: {args.report}")
        if manifest:
            print(f"Package written: {manifest['package']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
