# Clean Package Export Design

## Goal

Upgrade `ai-artifact-cleanup` from a safe cache cleaner into a release-prep assistant that can clean, explain, quarantine, report, and export a clean project package.

## User Problems

- Users do not only want files deleted; they want confidence that important source files, secrets, and Git-tracked work are safe.
- Users often need a clean package for GitHub upload, handoff, backup, or deployment review.
- Users need readable reports so humans and future AI agents can understand what was removed or excluded.

## Features

- Clean ZIP export: create a portable archive without `.git/`, secrets, dependencies, caches, and generated clutter.
- Manifest: write machine-readable `cleanup-manifest.json` into the package and optionally next to reports.
- Quarantine mode: move delete candidates into a quarantine directory instead of deleting them permanently.
- Markdown report: summarize deleted, quarantined, excluded, protected, and high-risk items.
- Project config: allow `.ai-cleanup.yml` or `.ai-cleanup.json` to add project-specific protect, low-risk, high-risk, and package include/exclude patterns.
- Explain mode: explain how a path is classified and which rule caused the decision.

## Safety Rules

- Git-tracked files stay protected during cleanup.
- `.git/`, `.env*`, virtual environments, and `node_modules/` remain protected.
- High-risk items require `--include-high-risk` before deletion or quarantine.
- Package export does not need to mutate the workspace.
- Quarantine directories are protected from recursive cleanup.

## CLI Shape

```bash
python scripts/cleanup_ai_artifacts.py . --dry-run
python scripts/cleanup_ai_artifacts.py . --apply --quarantine .ai-cleanup-trash
python scripts/cleanup_ai_artifacts.py . --package clean-export.zip
python scripts/cleanup_ai_artifacts.py . --report cleanup-report.md
python scripts/cleanup_ai_artifacts.py . --explain preview-report.html
```

## Success Criteria

- Existing behavior remains compatible.
- New features have automated tests.
- README and skill docs explain why the tool is powerful and safe.
- The updated skill validates, installs locally, commits cleanly, and pushes to GitHub.
