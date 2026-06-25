# AI Artifact Cleanup

AI Artifact Cleanup is a Codex skill and Python CLI for cleaning AI-generated workspace clutter, protecting important files, and exporting a clean handoff package.

It is built for a real pain point in AI-assisted development: after several agent runs, a project can fill up with caches, previews, screenshots, reports, generated folders, temporary logs, and half-useful artifacts. This tool helps an AI agent or human clean that safely instead of using risky wildcard deletion.

## What It Does

- Scans a workspace and classifies cleanup candidates as `low`, `high`, or `protected`.
- Deletes only low-risk caches by default.
- Requires explicit confirmation flags before high-risk generated outputs are removed.
- Protects `.git/`, `.env*`, `node_modules/`, virtual environments, and Git-tracked files.
- Moves candidates into a quarantine folder instead of deleting them permanently.
- Creates a clean ZIP package for upload, deployment review, backup, or handoff.
- Writes a machine-readable `cleanup-manifest.json` into each package.
- Generates Markdown reports for humans and future AI agents.
- Explains why a single file was classified a certain way.
- Supports project-specific rules through `.ai-cleanup.json` or a simple `.ai-cleanup.yml`.

## Quick Start

Preview what would be cleaned:

```bash
python scripts/cleanup_ai_artifacts.py . --dry-run
```

Delete low-risk items:

```bash
python scripts/cleanup_ai_artifacts.py . --apply
```

Move low-risk items into a quarantine folder:

```bash
python scripts/cleanup_ai_artifacts.py . --apply --quarantine .ai-cleanup-trash
```

Create a clean handoff package:

```bash
python scripts/cleanup_ai_artifacts.py . --package clean-export.zip
```

Write a cleanup report:

```bash
python scripts/cleanup_ai_artifacts.py . --dry-run --report cleanup-report.md
```

Explain one path:

```bash
python scripts/cleanup_ai_artifacts.py . --explain preview-report.html
```

Get JSON output for another tool or AI agent:

```bash
python scripts/cleanup_ai_artifacts.py . --dry-run --json
```

## Clean Package Export

The package feature creates a ZIP without mutating your workspace. It excludes common noise and protected paths, then adds `cleanup-manifest.json` so the receiver can inspect what was included and excluded.

Typical excluded paths:

- `.git/`
- `.env`, `.env.local`, `.env.*`
- `node_modules/`
- `.venv/`, `venv/`, `env/`
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`
- `.vite/`, `.turbo/`, `.parcel-cache/`, `.next/cache/`
- `dist/`, `build/`, `coverage/`
- generated previews, screenshots, and report HTML files

## Project Rules

Create `.ai-cleanup.json` to tune rules for one repository:

```json
{
  "protect": ["exports/keep/**"],
  "low_risk": ["tmp-ai/**"],
  "high_risk": ["generated-demo/**"],
  "package_exclude": ["private-notes.md"]
}
```

Supported keys:

- `protect`: never clean or package-match these paths as removable.
- `low_risk`: delete or quarantine with `--apply`.
- `high_risk`: preview by default; remove only with `--include-high-risk`.
- `package_exclude`: exclude from clean ZIP exports.
- `package_include`: reserved for future allow-list workflows.

## Why It Is Safe

The cleaner uses structured scanning, path containment checks, Git-tracked file protection, and risk labels. It avoids broad recursive shell deletion and keeps high-risk outputs behind an explicit flag. When in doubt, use `--dry-run`, `--report`, or `--quarantine`.

## Codex Skill Usage

Install this folder as a Codex skill, then ask:

```text
Use ai-artifact-cleanup to scan this project and create a clean package.
```

The skill tells the agent to dry-run first, preserve protected files, request confirmation before high-risk deletion, and use the bundled Python script instead of ad hoc deletion commands.

## Development

Run tests:

```bash
python -m unittest discover -s tests
```

Validate the skill:

```bash
python C:/Users/16978/.codex/skills/.system/skill-creator/scripts/quick_validate.py .
```
