# Cleanup Rules

## Low Risk

Low-risk items may be deleted with `--apply`:

- Python caches: `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `*.pyc`, `*.pyo`
- Frontend/tool caches: `.vite/`, `.turbo/`, `.parcel-cache/`, `.next/cache/`
- Temporary files: `*.tmp`, `*.bak`
- Explicit Codex dev logs: `.codex-dev*.log`, `codex-dev*.log`

## High Risk

High-risk items are previewed by default and require `--include-high-risk`:

- Build/report outputs: `dist/`, `build/`, `coverage/`
- AI output names: `generated-*`, `ai-output-*`, `ai_output_*`
- Preview/report media: `preview-*.html`, `*preview*.html`, `*report*.html`, `*screenshot*.png`, `*screenshot*.jpg`
- Untracked Superpowers artifacts: `docs/superpowers/plans/*`, `docs/superpowers/specs/*`

## Protected

Protected items must not be deleted:

- Version control internals: `.git/`, `.hg/`, `.svn/`
- Secrets/config files: `.env`, `.env.*`, `.env.local`
- Heavy dependency/runtime folders: `node_modules/`, `.venv/`, `venv/`, `env/`
- Cleanup quarantine folders: `.ai-cleanup-trash/`
- Any file reported by `git ls-files`

## Project Config

Project-level config files are optional:

- `.ai-cleanup.json`
- `.ai-cleanup.yml`
- `.ai-cleanup.yaml`

Supported keys:

- `protect`: mark paths as protected.
- `low_risk`: add low-risk path or filename patterns.
- `high_risk`: add high-risk path or filename patterns.
- `package_exclude`: exclude paths from clean ZIP export.
- `package_include`: reserved for future allow-list workflows.

Config protection has the highest priority.

## Package Export

`--package <zip>` creates a clean ZIP without mutating the workspace. It excludes protected paths, cleanup candidates, configured package exclusions, and the package output itself. Every package receives `cleanup-manifest.json` with included and excluded path lists.

## Action Meanings

- `would_delete`: dry-run candidate.
- `deleted`: removed from disk.
- `quarantined`: moved into a quarantine directory instead of permanent deletion.
- `needs_confirmation`: high-risk item skipped until explicit confirmation.
- `skipped`: protected or tracked item that the cleaner intentionally ignored.
- `excluded`: omitted from clean package export.
