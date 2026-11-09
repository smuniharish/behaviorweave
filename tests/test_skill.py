"""The Agent Skill is valid, its links resolve, and its setup check and test template pass."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from skills_ref import read_properties, validate

import behaviorweave

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = ROOT / "behaviorweave-skills"
SKILL = DISTRIBUTION / "skills" / "behaviorweave"
SKILLS = sorted((DISTRIBUTION / "skills").iterdir())
LINK = re.compile(r"\]\(([^)#<>\s]+)(?:#[^)]*)?\)")
# Match the upstream import-time warning filter used by the package test configuration.
STRICT_WARNINGS = [
    "-W",
    "error",
    "-W",
    "ignore:'asyncio.iscoroutinefunction' is deprecated:DeprecationWarning",
]


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - runs this repository's own files
        [sys.executable, *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
        cwd=ROOT,
    )


@pytest.mark.parametrize("skill", SKILLS, ids=lambda path: path.name)
def test_the_skill_follows_the_agent_skills_specification(skill: Path) -> None:
    properties = read_properties(skill)

    assert validate(skill) == []
    assert properties.name == skill.name
    assert properties.license == "Apache-2.0"
    assert properties.metadata["version"] == behaviorweave.__version__
    assert len((skill / "SKILL.md").read_text(encoding="utf-8").splitlines()) < 500


def test_references_are_one_level_deep_and_every_relative_link_resolves() -> None:
    assert all(path.is_file() for skill in SKILLS for path in (skill / "references").iterdir())
    for page in DISTRIBUTION.rglob("*.md"):
        for target in LINK.findall(page.read_text(encoding="utf-8")):
            if "://" not in target:
                assert (page.parent / target).exists(), f"{page.name} links to {target}"


def test_the_setup_check_passes() -> None:
    completed = run(*STRICT_WARNINGS, str(SKILL / "scripts" / "verify_setup.py"))

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "FAIL" not in completed.stdout
    assert completed.stdout.rstrip().endswith("All checks passed.")


def test_the_policy_test_template_passes(tmp_path: Path) -> None:
    template = SKILL / "assets" / "test_behavior_policy.py"
    # A private basetemp keeps the nested run away from the user-wide pytest temp directory.
    completed = run(
        "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={tmp_path}", str(template)
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "7 passed" in completed.stdout


def test_discovery_paths_and_evaluation_cases() -> None:
    discovery = json.loads((ROOT / "skills.sh.json").read_text(encoding="utf-8"))
    assert discovery["paths"] == ["./behaviorweave-skills/skills"]
    cases = json.loads((DISTRIBUTION / "validation" / "evals.json").read_text(encoding="utf-8"))
    assert {case["skill"] for case in cases} == {skill.name for skill in SKILLS}
    for skill in SKILLS:
        selected = [case for case in cases if case["skill"] == skill.name]
        assert {case["activate"] for case in selected} == {True, False}
        assert all(case["prompt"] and case["expected"] for case in selected)
