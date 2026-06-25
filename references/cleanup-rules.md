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
- Any file reported by `git ls-files`

## Action Meanings

- `would_delete`: dry-run candidate.
- `deleted`: removed from disk.
- `needs_confirmation`: high-risk item skipped until explicit confirmation.
- `skipped`: protected or tracked item that the cleaner intentionally ignored.
