# Clean Package Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clean package export, quarantine, Markdown reports, project configuration, and explain mode to `ai-artifact-cleanup`.

**Architecture:** Keep the single Python CLI as the reusable engine, but add small pure functions for configuration, reporting, packaging, and explanation. Tests exercise public functions and CLI behavior so the skill remains dependable for future agents.

**Tech Stack:** Python standard library, `unittest`, Git, Codex skill metadata.

---

### Task 1: Tests For New Behavior

**Files:**
- Modify: `tests/test_cleanup_ai_artifacts.py`

- [x] Add tests for quarantine mode moving low-risk files into `.ai-cleanup-trash`.
- [x] Add tests for clean package export excluding caches, secrets, dependencies, and generated previews.
- [x] Add tests for package manifest content.
- [x] Add tests for Markdown report creation.
- [x] Add tests for `.ai-cleanup.json` project rules.
- [x] Add tests for explain mode.
- [x] Run `python -m unittest discover -s tests` and verify the new tests fail because the feature does not exist yet.

### Task 2: Cleaner Engine Upgrade

**Files:**
- Modify: `scripts/cleanup_ai_artifacts.py`

- [x] Add a `CleanupConfig` dataclass with pattern lists for protect, low-risk, high-risk, package include, and package exclude rules.
- [x] Load `.ai-cleanup.json` and a conservative subset of `.ai-cleanup.yml` when present.
- [x] Add quarantine support that moves candidates into a protected quarantine directory.
- [x] Add package export with deterministic ZIP ordering and a manifest.
- [x] Add Markdown report rendering.
- [x] Add explain mode for one path.
- [x] Run the test suite until all tests pass.

### Task 3: Public Documentation

**Files:**
- Create: `README.md`
- Modify: `SKILL.md`
- Modify: `references/cleanup-rules.md`
- Modify: `agents/openai.yaml`

- [x] Explain the product positioning: AI project cleanup and release prep.
- [x] Document safe cleanup, quarantine, report, explain, and package workflows.
- [x] Include examples that users can copy.
- [x] Keep skill frontmatter focused on trigger conditions.
- [x] Run skill validation.

### Task 4: Validation And Publish

**Files:**
- All changed files

- [ ] Run `python -m unittest discover -s tests`.
- [ ] Run `python -m py_compile scripts/cleanup_ai_artifacts.py tests/test_cleanup_ai_artifacts.py`.
- [ ] Run the skill quick validator.
- [ ] Copy the updated skill into `C:/Users/16978/.codex/skills/ai-artifact-cleanup`.
- [ ] Commit and push to GitHub.
