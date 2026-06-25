import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cleanup_ai_artifacts.py"


def load_cleanup_module():
    spec = importlib.util.spec_from_file_location("cleanup_ai_artifacts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["cleanup_ai_artifacts"] = module
    spec.loader.exec_module(module)
    return module


class CleanupAiArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative_path, content="x"):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def make_dir(self, relative_path):
        path = self.root / relative_path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def init_git(self):
        subprocess.run(["git", "init"], cwd=self.root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.root, check=True)

    def test_dry_run_reports_low_risk_without_deleting(self):
        cleanup = load_cleanup_module()
        self.make_dir("__pycache__")
        pyc = self.write("__pycache__/thing.pyc")
        log = self.write(".codex-dev.stdout.log")

        report = cleanup.cleanup_workspace(self.root, dry_run=True)

        self.assertTrue(pyc.exists())
        self.assertTrue(log.exists())
        self.assertEqual(report.deleted_count, 0)
        self.assertEqual(report.low_risk_count, 2)
        self.assertTrue(all(item.action == "would_delete" for item in report.items if item.risk == "low"))

    def test_apply_deletes_low_risk_artifacts(self):
        cleanup = load_cleanup_module()
        self.make_dir(".pytest_cache")
        self.write(".pytest_cache/CACHEDIR.TAG")
        self.write("module.pyc")
        self.write("notes.tmp")

        report = cleanup.cleanup_workspace(self.root, dry_run=False)

        self.assertFalse((self.root / ".pytest_cache").exists())
        self.assertFalse((self.root / "module.pyc").exists())
        self.assertFalse((self.root / "notes.tmp").exists())
        self.assertEqual(report.deleted_count, 3)

    def test_high_risk_artifacts_are_previewed_by_default(self):
        cleanup = load_cleanup_module()
        self.make_dir("dist")
        self.write("dist/index.html")
        self.write("docs/superpowers/plans/2026-06-25-ai-plan.md")

        report = cleanup.cleanup_workspace(self.root, dry_run=False)

        self.assertTrue((self.root / "dist").exists())
        self.assertTrue((self.root / "docs/superpowers/plans/2026-06-25-ai-plan.md").exists())
        high_actions = {item.relative_path: item.action for item in report.items if item.risk == "high"}
        self.assertEqual(high_actions["dist"], "needs_confirmation")
        self.assertEqual(
            high_actions["docs/superpowers/plans/2026-06-25-ai-plan.md"],
            "needs_confirmation",
        )

    def test_include_high_risk_deletes_high_risk_artifacts(self):
        cleanup = load_cleanup_module()
        self.write("generated-report.html")
        self.make_dir("coverage")

        report = cleanup.cleanup_workspace(self.root, dry_run=False, include_high_risk=True)

        self.assertFalse((self.root / "generated-report.html").exists())
        self.assertFalse((self.root / "coverage").exists())
        self.assertEqual(report.deleted_count, 2)

    def test_never_deletes_git_or_env_files(self):
        cleanup = load_cleanup_module()
        self.make_dir(".git/objects")
        self.write(".git/objects/keep")
        self.write(".env")
        self.write(".env.local")

        report = cleanup.cleanup_workspace(self.root, dry_run=False, include_high_risk=True)

        self.assertTrue((self.root / ".git/objects/keep").exists())
        self.assertTrue((self.root / ".env").exists())
        self.assertTrue((self.root / ".env.local").exists())
        skipped = {item.relative_path for item in report.items if item.action == "skipped"}
        self.assertIn(".env", skipped)
        self.assertIn(".env.local", skipped)

    def test_does_not_delete_tracked_files(self):
        cleanup = load_cleanup_module()
        self.init_git()
        tracked = self.write("dist/index.html")
        subprocess.run(["git", "add", "dist/index.html"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "track dist"], cwd=self.root, check=True, stdout=subprocess.DEVNULL)

        report = cleanup.cleanup_workspace(self.root, dry_run=False, include_high_risk=True)

        self.assertTrue(tracked.exists())
        skipped = {item.relative_path for item in report.items if item.action == "skipped"}
        self.assertIn("dist/index.html", skipped)

    def test_cli_json_output_is_machine_readable(self):
        self.make_dir("__pycache__")
        self.write("__pycache__/thing.pyc")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root), "--dry-run", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["deleted_count"], 0)
        self.assertEqual(payload["low_risk_count"], 1)

    def test_quarantine_moves_low_risk_artifacts_without_permanent_delete(self):
        cleanup = load_cleanup_module()
        self.write("notes.tmp")
        self.write(".pytest_cache/CACHEDIR.TAG")

        report = cleanup.cleanup_workspace(
            self.root,
            dry_run=False,
            quarantine_dir=self.root / ".ai-cleanup-trash",
        )

        self.assertFalse((self.root / "notes.tmp").exists())
        self.assertFalse((self.root / ".pytest_cache").exists())
        self.assertTrue((self.root / ".ai-cleanup-trash" / "notes.tmp").exists())
        self.assertTrue((self.root / ".ai-cleanup-trash" / ".pytest_cache" / "CACHEDIR.TAG").exists())
        self.assertEqual(report.deleted_count, 0)
        self.assertEqual(report.quarantined_count, 2)
        self.assertTrue(all(item.action == "quarantined" for item in report.items if item.risk == "low"))

    def test_clean_package_excludes_noise_and_writes_manifest(self):
        cleanup = load_cleanup_module()
        self.write("README.md", "# Demo\n")
        self.write("src/app.py", "print('hello')\n")
        self.write(".env", "SECRET=1\n")
        self.write("__pycache__/thing.pyc")
        self.write("node_modules/pkg/index.js")
        self.write("preview-report.html", "<html>preview</html>")
        package_path = self.root / "clean-export.zip"

        manifest = cleanup.create_clean_package(self.root, package_path)

        self.assertTrue(package_path.exists())
        with zipfile.ZipFile(package_path) as archive:
            names = set(archive.namelist())
            payload = json.loads(archive.read("cleanup-manifest.json"))

        self.assertIn("README.md", names)
        self.assertIn("src/app.py", names)
        self.assertIn("cleanup-manifest.json", names)
        self.assertNotIn(".env", names)
        self.assertNotIn("__pycache__/thing.pyc", names)
        self.assertNotIn("node_modules/pkg/index.js", names)
        self.assertNotIn("preview-report.html", names)
        self.assertEqual(payload["included_count"], len(payload["included"]))
        self.assertIn(".env", {item["relative_path"] for item in payload["excluded"]})
        self.assertIn("preview-report.html", {item["relative_path"] for item in manifest["excluded"]})

    def test_markdown_report_summarizes_actions_and_counts(self):
        cleanup = load_cleanup_module()
        self.write("notes.tmp")
        report = cleanup.cleanup_workspace(self.root, dry_run=True)
        report_path = self.root / "cleanup-report.md"

        cleanup.write_markdown_report(report, report_path)

        body = report_path.read_text(encoding="utf-8")
        self.assertIn("# AI Artifact Cleanup Report", body)
        self.assertIn("low=1", body)
        self.assertIn("would_delete", body)
        self.assertIn("notes.tmp", body)

    def test_project_config_adds_protect_low_and_high_risk_patterns(self):
        cleanup = load_cleanup_module()
        self.write(
            ".ai-cleanup.json",
            json.dumps(
                {
                    "protect": ["keep/**"],
                    "low_risk": ["scratch.agent"],
                    "high_risk": ["danger/output.txt"],
                    "package_exclude": ["private-notes.md"],
                }
            ),
        )
        self.write("keep/preview-report.html")
        self.write("scratch.agent")
        self.write("danger/output.txt")

        report = cleanup.cleanup_workspace(self.root, dry_run=True)
        by_path = {item.relative_path: item for item in report.items}

        self.assertEqual(by_path["keep/preview-report.html"].risk, "protected")
        self.assertEqual(by_path["keep/preview-report.html"].action, "skipped")
        self.assertEqual(by_path["scratch.agent"].risk, "low")
        self.assertEqual(by_path["danger/output.txt"].risk, "high")

    def test_cli_explain_mode_reports_matching_rule_as_json(self):
        self.write("preview-report.html", "<html>preview</html>")

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), str(self.root), "--explain", "preview-report.html", "--json"],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)

        self.assertEqual(payload["relative_path"], "preview-report.html")
        self.assertEqual(payload["risk"], "high")
        self.assertIn("preview", payload["reason"].lower())


if __name__ == "__main__":
    unittest.main()
