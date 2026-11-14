"""Install the credit-watch skill and the credit-downgrade model environment for this package.

Goes in:  the repository folder (this file's folder) and an optional student project folder.
Comes out: the skill copied into each chosen AI agent's skills folder, a .venv with the model's packages, and
          optional contact files. Data: none (the student downloads the data later; see README.md).

Skill folder locations checked 13 November 2026:
  Claude Code  https://code.claude.com/docs/en/skills        user ~/.claude/skills, project .claude/skills
  opencode     https://opencode.ai/docs/skills               user ~/.agents/skills, project .agents/skills
  Codex        https://developers.openai.com/codex/skills    project .agents/skills; user ~/.codex/skills
               (the Codex skill installer uses $CODEX_HOME/skills, default ~/.codex/skills:
                https://github.com/openai/skills/blob/main/skills/.system/skill-installer/SKILL.md)

Usage: python3 install.py [--agents LIST] [--project DIR] [--skip-model] [--contact "Name e-mail"] [--check]
       python3 install.py --uninstall [--agents LIST] [--project DIR]
  --agents     claude, opencode, codex, or all (comma list). Default: each one whose command is on PATH;
               if none is found, opencode.
  --project    install into DIR/.claude/skills and DIR/.agents/skills instead of the home folder.
  --skip-model do not make the model's .venv or install its packages.
  --contact    write the SEC contact to the skill's and the model's config files; never printed.
  --check      run the agent tests, one offline fetch for HON, and the model tests if the model is installed.
  --uninstall  remove installed credit-watch skill folders only.

The script uses the Python standard library only and runs on Linux, macOS and Windows.
"""
import argparse
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_NAME = "credit-watch"
AGENT_NAMES = ("claude", "opencode", "codex")
VENV_TORCH = "torch==2.15.0"
TORCH_INDEX = "https://download.pytorch.org/whl/cpu"


def run_capture(command, cwd=None, env=None):
    """Run a command and return (exit code, standard output and error joined)."""
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def run_visible(command, cwd=None, env=None):
    """Run a command with its output shown and return True when it exits 0."""
    return subprocess.run(command, cwd=cwd, env=env).returncode == 0


def last_line(text):
    """Return the last non-empty line of text, or an empty string."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def venv_python(repo):
    """Return the Python file inside the repository's .venv for this operating system."""
    if os.name == "nt":
        return repo / ".venv" / "Scripts" / "python.exe"
    return repo / ".venv" / "bin" / "python"


def select_agents(value):
    """Return the chosen agent names, expanding all and falling back to opencode."""
    if value:
        names = []
        for part in value.split(","):
            name = part.strip().lower()
            if not name:
                continue
            if name == "all":
                names.extend(AGENT_NAMES)
            elif name in AGENT_NAMES:
                names.append(name)
            else:
                raise ValueError(f"unknown agent '{name}'; use claude, opencode, codex, or all")
        unique = []
        for name in names:
            if name not in unique:
                unique.append(name)
        if unique:
            return unique
    found = [name for name in AGENT_NAMES if shutil.which(name)]
    return found or ["opencode"]


def agent_skills_dir(agent, project=None):
    """Return the skills folder an agent reads for the home folder or a project."""
    if project is not None:
        if agent == "claude":
            return project / ".claude" / "skills"
        return project / ".agents" / "skills"
    home = Path.home()
    if agent == "claude":
        return home / ".claude" / "skills"
    if agent == "opencode":
        return home / ".agents" / "skills"
    return home / ".codex" / "skills"


def skill_files(root):
    """Return the relative file paths of a skill folder, skipping __pycache__."""
    files = set()
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_file() and "__pycache__" not in relative.parts and path.suffix != ".pyc":
            files.add(relative)
    return files


def same_skill(source, target):
    """Return True when the target folder holds the same skill files as the source."""
    if not target.is_dir():
        return False
    source_files = skill_files(source)
    if source_files != skill_files(target):
        return False
    for relative in source_files:
        if (source / relative).read_bytes() != (target / relative).read_bytes():
            return False
    return True


def backup_skill(repo, agent, target):
    """Move an old skill folder into the repository's .install-backups and return the backup path."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = repo / ".install-backups" / f"{agent}-{stamp}"
    number = 1
    while base.exists():
        base = repo / ".install-backups" / f"{agent}-{stamp}-{number}"
        number += 1
    base.mkdir(parents=True)
    shutil.move(str(target), str(base / SKILL_NAME))
    return base


def install_skill(source, target, repo, agent):
    """Copy one skill into a target folder and return a short status line."""
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(f"skill source not found: {source}")
    if target.exists():
        if same_skill(source, target):
            return f"{target} (already installed)"
        backup = backup_skill(repo, agent, target)
        status = f"{target} (replaced; old folder in {backup})"
    else:
        status = f"{target} (installed)"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return status


def install_model(repo):
    """Make .venv if missing, install CPU torch and the model requirements; return True on success."""
    python = venv_python(repo)
    if not python.exists():
        print("model: making .venv")
        if not run_visible([sys.executable, "-m", "venv", str(repo / ".venv")], repo):
            return False
    pip = [str(python), "-m", "pip"]
    print(f"model: installing {VENV_TORCH}")
    if not run_visible([*pip, "install", VENV_TORCH, "--index-url", TORCH_INDEX], repo):
        return False
    print("model: installing model/requirements.txt")
    return run_visible([*pip, "install", "-r", str(repo / "model" / "requirements.txt")], repo)


def settings_with_contact(existing, contact):
    """Return settings.toml text with [sec] contact set, keeping every other line."""
    value = '"' + contact.replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = existing.splitlines()
    section = None
    for index, line in enumerate(lines):
        if re.match(r"^\s*\[sec\]\s*(#.*)?$", line):
            section = index
            break
    if section is None:
        body = existing.rstrip("\n")
        if body:
            body += "\n\n"
        return body + f"[sec]\ncontact = {value}\n"
    end = len(lines)
    for index in range(section + 1, len(lines)):
        if re.match(r"^\s*\[[^\]]+\]\s*(#.*)?$", lines[index]):
            end = index
            break
    contact_line = None
    for index in range(section + 1, end):
        if re.match(r"^\s*contact\s*=", lines[index]):
            contact_line = index
            break
    if contact_line is None:
        lines.insert(section + 1, f"contact = {value}")
    else:
        lines[contact_line] = re.sub(r'^(\s*contact\s*=\s*)("[^"]*"|\'[^\']*\'|.*?)(\s*#.*)?$',
                                     lambda match: match.group(1) + value + (match.group(3) or ""),
                                     lines[contact_line])
    return "\n".join(lines) + "\n"


def write_contact(text):
    """Write the contact for the skill and the model and return the two file paths."""
    contact = text.strip()
    if not contact:
        raise ValueError("--contact needs a name and e-mail address")
    home = Path.home()
    skill_file = home / ".config" / "credit-watch" / "contact.txt"
    model_file = home / ".config" / "tcf_credit" / "settings.toml"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    model_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(contact + "\n", encoding="utf-8")
    existing = model_file.read_text(encoding="utf-8") if model_file.exists() else ""
    model_file.write_text(settings_with_contact(existing, contact), encoding="utf-8")
    return skill_file, model_file


def contact_is_set():
    """Return True when a contact file, setting, or environment variable holds a contact."""
    home = Path.home()
    skill_file = home / ".config" / "credit-watch" / "contact.txt"
    if skill_file.is_file() and skill_file.read_text(encoding="utf-8").strip():
        return True
    model_file = home / ".config" / "tcf_credit" / "settings.toml"
    if model_file.is_file() and re.search(r"^\s*contact\s*=\s*\"[^\"]+\"", model_file.read_text(encoding="utf-8"),
                                          re.M):
        return True
    return bool(os.environ.get("SEC_CONTACT", "").strip() or os.environ.get("TCF_SEC_CONTACT", "").strip())


def check_agent_tests(repo):
    """Run the agent unit tests and return (passed, last output line)."""
    code, output = run_capture([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo / "agent")
    return code == 0, last_line(output)


def check_offline_fetch(repo):
    """Run the skill's first step for HON offline in a temporary folder and return (passed, last output line)."""
    tool = repo / "agent" / "skills" / SKILL_NAME / "tools" / "fetch.py"
    with tempfile.TemporaryDirectory() as folder:
        code, output = run_capture([sys.executable, str(tool), "HON", "--offline"], cwd=folder)
        wrote = (Path(folder) / "credit-watch" / "run" / "passages.json").is_file()
    return code == 0 and wrote, last_line(output)


def check_model_tests(repo):
    """Run the model tests with the .venv Python and return (passed, last output line)."""
    python = venv_python(repo)
    if not python.exists():
        return None, "no .venv (model not installed)"
    env = os.environ.copy()
    source = str(repo / "model" / "src")
    env["PYTHONPATH"] = source + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    code, output = run_capture([str(python), "-m", "unittest", "discover", "-s", "model/tests"], cwd=repo, env=env)
    return code == 0, last_line(output)


def uninstall_skills(agents, project):
    """Remove only credit-watch folders that contain SKILL.md and return what was removed."""
    removed = []
    kept = []
    seen = set()
    for agent in agents:
        target = agent_skills_dir(agent, project) / SKILL_NAME
        if target in seen:
            continue
        seen.add(target)
        if target.is_dir() and (target / "SKILL.md").is_file():
            shutil.rmtree(target)
            removed.append(f"{agent}: {target}")
        elif target.exists():
            kept.append(f"{agent}: {target} (no SKILL.md; left alone)")
    return removed, kept


def print_summary(repo, skill_lines, model_line, checks, uninstalled=None, kept=None):
    """Print the INSTALL SUMMARY block and the next steps."""
    print("")
    print("INSTALL SUMMARY")
    print(f"  repository: {repo}")
    for line in skill_lines:
        print(f"  skill: {line}")
    print(f"  model environment: {model_line}")
    print(f"  contact set: {'yes' if contact_is_set() else 'no'}")
    for name, passed, detail in checks:
        result = "PASS" if passed else "FAIL"
        if passed is None:
            result = "SKIPPED"
        print(f"  check {name}: {result}" + (f" ({detail})" if detail else ""))
    for line in uninstalled or []:
        print(f"  removed: {line}")
    for line in kept or []:
        print(f"  left: {line}")
    if uninstalled is not None:
        print("  left alone: .venv, contact files, and your own credit-watch/ run folders.")
    if not contact_is_set():
        print("  note: without a contact the skill works offline only until you set one.")
    print("  next: start a NEW agent session so it sees the skill, then run /credit-watch HON --offline.")


def parse_args(argv=None):
    """Read the command line and return the options."""
    parser = argparse.ArgumentParser(description="Install the credit-watch skill and the model environment.")
    parser.add_argument("--agents", help="claude, opencode, codex, or all (comma list)")
    parser.add_argument("--project", type=Path, help="install into this project folder instead of the home folder")
    parser.add_argument("--skip-model", action="store_true", help="do not make .venv or install the model packages")
    parser.add_argument("--contact", help='SEC contact, for example "Name you@school.ca"')
    parser.add_argument("--check", action="store_true", help="run the agent tests, offline HON fetch and model tests")
    parser.add_argument("--uninstall", action="store_true", help="remove installed credit-watch skill folders only")
    parser.add_argument("--repo", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv=None):
    """Install or uninstall the skill and model environment, run checks, and print the summary."""
    args = parse_args(argv)
    repo = (args.repo or Path(__file__).resolve().parent).resolve()
    project = args.project.resolve() if args.project else None
    try:
        agents = select_agents(args.agents)
    except ValueError as error:
        print(f"error: {error}")
        return 2

    if args.uninstall:
        removed, kept = uninstall_skills(agents, project)
        print_summary(repo, [], "left alone (--uninstall)", [], uninstalled=removed, kept=kept)
        return 0

    ok = True
    checks = []
    skill_lines = []
    source = repo / "agent" / "skills" / SKILL_NAME
    for agent in agents:
        target = agent_skills_dir(agent, project) / SKILL_NAME
        try:
            skill_lines.append(f"{agent}: {install_skill(source, target, repo, agent)}")
        except OSError as error:
            ok = False
            skill_lines.append(f"{agent}: FAILED ({error})")

    contact_written = False
    if args.contact is not None:
        try:
            write_contact(args.contact)
            contact_written = True
        except (OSError, ValueError) as error:
            ok = False
            print(f"contact: FAILED ({error})")

    if args.skip_model:
        model_line = "skipped (--skip-model)"
        model_ok = True
    elif sys.version_info < (3, 12):
        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        model_line = f"skipped (Python {version} is older than 3.12)"
        model_ok = True
    else:
        model_ok = install_model(repo)
        model_line = f"{venv_python(repo)}" if model_ok else "FAILED"
        ok = ok and model_ok

    if args.check:
        passed, detail = check_agent_tests(repo)
        checks.append(("agent tests", passed, detail))
        passed, detail = check_offline_fetch(repo)
        checks.append(("offline HON fetch", passed, detail))
        if not args.skip_model:
            passed, detail = check_model_tests(repo)
            checks.append(("model tests", passed, detail))
        ok = ok and all(item[1] is not False for item in checks)

    if contact_written:
        print("contact: written for the skill and the model (value not shown)")
    print_summary(repo, skill_lines, model_line, checks)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
