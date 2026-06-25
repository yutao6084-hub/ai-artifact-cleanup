---
name: ai-artifact-cleanup
description: Clean AI-generated workspace clutter and common tool caches safely. Use when the user asks to clean, remove, prune, tidy, or audit AI-created temporary files, Codex logs, generated previews, build/cache folders, untracked Superpowers plan/spec artifacts, or similar files after AI-assisted development.
---

# AI Artifact Cleanup

## Overview

Use this skill to clean a project workspace without damaging source code or user data. Prefer the bundled Python cleaner for deterministic scanning, risk classification, deletion, and reporting.

## Safety Rules

- Work only inside the requested workspace root.
- Never delete `.git/`, `.env*`, virtual environments, `node_modules/`, or files tracked by Git.
- Start with a scan before deleting anything unless the user explicitly asked for immediate cleanup.
- Delete low-risk items only when cleanup is requested.
- Preview high-risk items and ask for confirmation before deleting them.
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

6. Summarize what was deleted, what still needs confirmation, and any protected files that were skipped.

## Machine-Readable Reports

Use JSON when another tool, script, or test needs to consume the cleanup report:

```bash
python scripts/cleanup_ai_artifacts.py <workspace-root> --dry-run --json
```

The report includes `deleted_count`, `low_risk_count`, `high_risk_count`, `skipped_count`, and per-item `relative_path`, `risk`, `kind`, `reason`, and `action`.

## Rule Reference

Read `references/cleanup-rules.md` only when changing the cleanup rules, explaining classification details, or diagnosing why a file was or was not selected.
