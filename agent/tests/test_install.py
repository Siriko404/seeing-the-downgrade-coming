"""Tests of install.py: agent skill copies, backups, contact files, checks and uninstall.

Every test runs install.py in a temporary HOME and a temporary repository, so nothing here touches the real home
folder and no network or model download is used.
From the agent/ folder, run all tests with: python3 -m unittest discover -s tests
One file only: python3 -m unittest discover -s tests -p test_install.py
Standard library only.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INSTALL = ROOT / "install.py"
SKILL_TEXT = "---\nname: credit-watch\ndescription: test copy\n---\n\nTest skill.\n"


class InstallCase(unittest.TestCase):
    """Builds a temporary repository with one skill file and a temporary home folder."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.repo = self.tmp / "repo"
        self.skill = self.repo / "agent" / "skills" / "credit-watch"
        self.skill.mkdir(parents=True)
        (self.skill / "SKILL.md").write_text(SKILL_TEXT, encoding="utf-8")
        (self.skill / "tools").mkdir()
        (self.skill / "tools" / "fetch.py").write_text("print('test')\n", encoding="utf-8")
        (self.skill / "__pycache__").mkdir()
        (self.skill / "__pycache__" / "old.pyc").write_bytes(b"old")
        (self.repo / "model").mkdir()
        (self.repo / "model" / "requirements.txt").write_text("", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def env(self, path=None):
        """Return a clean environment with the temporary home and no contact variable."""
        env = {**os.environ, "HOME": str(self.home), "USERPROFILE": str(self.home)}
        env.pop("SEC_CONTACT", None)
        env.pop("TCF_SEC_CONTACT", None)
        if path is not None:
            env["PATH"] = path
        return env

    def run_install(self, *args, repo=None, path=None):
        """Run install.py with --repo and the temporary home, returning the finished process."""
        command = [sys.executable, str(INSTALL), "--repo", str(repo or self.repo), *args]
        return subprocess.run(command, cwd=self.tmp, env=self.env(path), capture_output=True, text=True)

    def target(self, agent):
        """Return the home-folder skill target for one agent."""
        if agent == "claude":
            return self.home / ".claude" / "skills" / "credit-watch"
        if agent == "opencode":
            return self.home / ".agents" / "skills" / "credit-watch"
        return self.home / ".codex" / "skills" / "credit-watch"

    def test_skill_copied_for_each_agent_choice(self):
        """--agents claude, opencode and codex each copy the skill to that agent's folder."""
        for agent in ("claude", "opencode", "codex"):
            with self.subTest(agent=agent):
                result = self.run_install("--skip-model", "--agents", agent)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                target = self.target(agent)
                self.assertEqual((target / "SKILL.md").read_text(encoding="utf-8"), SKILL_TEXT)
                self.assertFalse((target / "__pycache__").exists())
                self.assertIn(str(target), result.stdout)

    def test_default_choice_when_no_agent_command_is_on_path(self):
        """With an empty PATH the default agent is opencode and its home folder gets the skill."""
        empty = self.tmp / "empty-bin"
        empty.mkdir()
        result = self.run_install("--skip-model", path=str(empty))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.home / ".agents" / "skills" / "credit-watch" / "SKILL.md").is_file())
        self.assertFalse((self.home / ".claude").exists())
        self.assertFalse((self.home / ".codex").exists())

    def test_identical_target_says_already_installed(self):
        """A second install over the same files reports already installed and makes no backup."""
        first = self.run_install("--skip-model", "--agents", "claude")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = self.run_install("--skip-model", "--agents", "claude")
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("already installed", second.stdout)
        self.assertFalse((self.repo / ".install-backups").exists())

    def test_changed_target_is_moved_to_backups_and_replaced(self):
        """Different files in the target are moved into .install-backups and the new skill is copied."""
        old = self.home / ".claude" / "skills" / "credit-watch"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old skill\n", encoding="utf-8")
        (old / "old.txt").write_text("keep me in the backup\n", encoding="utf-8")
        result = self.run_install("--skip-model", "--agents", "claude")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("replaced", result.stdout)
        backups = list((self.repo / ".install-backups").glob("claude-*/credit-watch"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "SKILL.md").read_text(encoding="utf-8"), "old skill\n")
        self.assertEqual((backups[0] / "old.txt").read_text(encoding="utf-8"), "keep me in the backup\n")
        self.assertEqual((old / "SKILL.md").read_text(encoding="utf-8"), SKILL_TEXT)
        self.assertFalse((old / "old.txt").exists())

    def test_contact_is_written_in_the_formats_the_readers_use_and_never_printed(self):
        """--contact writes both files, both readers load the contact back, and output hides it."""
        contact = "Ada Lovelace ada@example.edu"
        result = self.run_install("--skip-model", "--agents", "opencode", "--contact", contact, repo=ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn(contact, result.stdout)
        self.assertNotIn(contact, result.stderr)
        self.assertEqual((self.home / ".config" / "credit-watch" / "contact.txt").read_text(
            encoding="utf-8").splitlines()[0], contact)
        model = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(ROOT / 'model' / 'src')!r}); "
             "from tcf_credit.sec_http import contact; print(contact())"],
            env=self.env(), capture_output=True, text=True)
        self.assertEqual(model.returncode, 0, model.stdout + model.stderr)
        self.assertEqual(model.stdout.strip(), contact)
        tools = self.home / ".agents" / "skills" / "credit-watch" / "tools"
        skill = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, {str(tools)!r}); import fetch; print(fetch.contact())"],
            env=self.env(), capture_output=True, text=True)
        self.assertEqual(skill.returncode, 0, skill.stdout + skill.stderr)
        self.assertEqual(skill.stdout.strip(), contact)

    def test_existing_settings_keep_their_other_keys(self):
        """Writing a contact changes only contact and keeps the other settings keys and sections."""
        settings = self.home / ".config" / "tcf_credit" / "settings.toml"
        settings.parent.mkdir(parents=True)
        settings.write_text('[sec]\ncontact = "old"\nother = "keep"\n\n[mail]\nhost = "smtp"\n', encoding="utf-8")
        result = self.run_install("--skip-model", "--agents", "opencode", "--contact", "New Person new@example.edu")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = tomllib.loads(settings.read_text(encoding="utf-8"))
        self.assertEqual(data["sec"]["contact"], "New Person new@example.edu")
        self.assertEqual(data["sec"]["other"], "keep")
        self.assertEqual(data["mail"]["host"], "smtp")

    def test_uninstall_removes_only_skill_folders(self):
        """--uninstall removes installed skills and leaves .venv, contacts, other skills and run folders alone."""
        result = self.run_install("--skip-model", "--agents", "opencode", "--contact", "A Person a@example.edu")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        (self.repo / ".venv").mkdir()
        (self.repo / ".venv" / "keep.txt").write_text("keep", encoding="utf-8")
        other = self.home / ".agents" / "skills" / "other-skill"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("other", encoding="utf-8")
        unrelated = self.home / ".claude" / "skills" / "credit-watch"
        unrelated.mkdir(parents=True)
        (unrelated / "notes.txt").write_text("no SKILL.md", encoding="utf-8")
        run_folder = self.tmp / "credit-watch" / "run"
        run_folder.mkdir(parents=True)
        (run_folder / "passages.md").write_text("student run", encoding="utf-8")
        removed = self.run_install("--uninstall", "--agents", "all")
        self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
        self.assertFalse((self.home / ".agents" / "skills" / "credit-watch").exists())
        self.assertTrue((self.home / ".config" / "credit-watch" / "contact.txt").is_file())
        self.assertTrue((self.home / ".config" / "tcf_credit" / "settings.toml").is_file())
        self.assertTrue((self.repo / ".venv" / "keep.txt").is_file())
        self.assertTrue((other / "SKILL.md").is_file())
        self.assertTrue((unrelated / "notes.txt").is_file())
        self.assertTrue((run_folder / "passages.md").is_file())
        self.assertIn("left alone", removed.stdout)

    def test_skip_model_makes_no_venv(self):
        """--skip-model installs the skill and does not create .venv."""
        result = self.run_install("--skip-model", "--agents", "opencode")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.repo / ".venv").exists())

    def test_project_install_uses_project_folders(self):
        """With --project the skill goes into the project's .claude and .agents skills folders."""
        project = self.tmp / "project"
        result = self.run_install("--skip-model", "--agents", "all", "--project", str(project))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((project / ".claude" / "skills" / "credit-watch" / "SKILL.md").is_file())
        self.assertTrue((project / ".agents" / "skills" / "credit-watch" / "SKILL.md").is_file())
        self.assertFalse((self.home / ".claude").exists())

    def test_summary_block_is_printed(self):
        """Every run ends with an INSTALL SUMMARY block listing the skill, model, contact and next step."""
        result = self.run_install("--skip-model", "--agents", "opencode")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("INSTALL SUMMARY", lines)
        self.assertIn("  contact set: no", lines)
        self.assertTrue(any(line.startswith("  skill: opencode:") for line in lines))
        self.assertTrue(any(line.startswith("  model environment: skipped (--skip-model)") for line in lines))
        self.assertTrue(any("/credit-watch HON --offline" in line for line in lines))

    def test_what_you_have_now_block_is_printed(self):
        """Every install ends with a WHAT YOU HAVE NOW block that names agent/MODIFYING.md."""
        result = self.run_install("--skip-model", "--agents", "opencode")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertIn("INSTALL SUMMARY", lines)
        self.assertIn("WHAT YOU HAVE NOW", lines)
        self.assertLess(lines.index("INSTALL SUMMARY"), lines.index("WHAT YOU HAVE NOW"))
        self.assertTrue(any("agent/MODIFYING.md" in line for line in lines))
        self.assertTrue(any("not investment advice" in line for line in lines))

    def test_what_you_have_now_block_is_absent_on_uninstall(self):
        """--uninstall prints the INSTALL SUMMARY but no WHAT YOU HAVE NOW block."""
        result = self.run_install("--uninstall", "--agents", "opencode")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("INSTALL SUMMARY", result.stdout)
        self.assertNotIn("WHAT YOU HAVE NOW", result.stdout)
        self.assertNotIn("agent/MODIFYING.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
