---
name: ai-artifact-cleanup
description: Use when the user asks to clean, prune, package, export, audit, explain, or quarantine AI-created temporary files, tool caches, generated previews, build outputs, Codex logs, untracked planning artifacts, or clutter after AI-assisted development.
---

# AI Artifact Cleanup

## Overview

Use this skill to clean and package a project workspace without damaging source code or user data. Prefer the bundled Python cleaner for deterministic scanning, risk classification, quarantine, export, and reporting.

## Safety Rules

- Work only inside the requested workspace root.
- Never delete `.git/`, `.env*`, virtual environments, `node_modules/`, or files tracked by Git.
- Start with a scan before deleting anything unless the user explicitly asked for immediate cleanup.
- Delete low-risk items only when cleanup is requested.
- Preview high-risk items and ask for confirmation before deleting them.
- Use quarantine when the user wants a reversible cleanup.
- Use clean package export when the user wants a handoff, backup, deployment review, or GitHub-ready archive.
- Do not replace the bundled cleaner with broad shell commands such as recursive wildcard deletion.

## Workflow

1. Identify the workspace root. If the user did not specify a path, use the current project root.
2. Run a dry run:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --dry-run
```

3. Review the report:
   - `low` items are common caches and explicit temporary files.
   - `high` items are generated outputs or untracked AI planning/spec artifacts.
   - `protected` items are skipped and must not be deleted.
4. If the user asked to clean, delete low-risk items:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --apply
```

5. If high-risk items should be removed, show the exact list and ask for confirmation. After confirmation, run:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --apply --include-high-risk
```

6. If the user wants reversible cleanup, quarantine instead of deleting:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --apply --quarantine .ai-cleanup-trash
```

7. If the user wants a clean handoff package, export a ZIP:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --package clean-export.zip
```

8. If the user wants a human-readable record, write a report:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --dry-run --report cleanup-report.md
```

9. If the user questions a specific file, explain it:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --explain path/to/file
```

10. Summarize what was deleted, quarantined, packaged, excluded, what still needs confirmation, and any protected files that were skipped.

## Machine-Readable Reports

Use JSON when another tool, script, or test needs to consume the cleanup report:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --dry-run --json
```

The report includes `deleted_count`, `quarantined_count`, `low_risk_count`, `high_risk_count`, `skipped_count`, and per-item `relative_path`, `risk`, `kind`, `reason`, and `action`.

## Project Rules

Read `.ai-cleanup.json`, `.ai-cleanup.yml`, or `.ai-cleanup.yaml` when present. Supported keys are `protect`, `low_risk`, `high_risk`, `package_exclude`, and `package_include`.

## Rule Reference

Read `references/cleanup-rules.md` only when changing the cleanup rules, explaining classification details, or diagnosing why a file was or was not selected.
