"""Documentation integrity: runnable snippets, API coverage, links, diagrams, and versions."""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import io
import re
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path
from types import ModuleType

import pytest

import behaviorweave

ROOT = Path(__file__).parents[1]
DOCS = ROOT / "docs"
SKILLS = ROOT / "behaviorweave-skills"
MARKDOWN = sorted([ROOT / "README.md", *DOCS.rglob("*.md"), *SKILLS.rglob("*.md")])
FENCE = re.compile(r"^(?P<indent>[ \t]*)```python[ \t]*$")


def _snippets(path: Path) -> list[tuple[int, str]]:
    """Return ``(line, code)`` for each runnable ```python block in ``path``."""
    return _parse_snippets(path.read_text(encoding="utf-8"))


def _parse_snippets(text: str) -> list[tuple[int, str]]:
    """Extract Python blocks, including indented ones, unless a skip marker precedes them."""
    lines = text.splitlines()
    snippets: list[tuple[int, str]] = []
    index = 0
    while index < len(lines):
        fence = FENCE.match(lines[index])
        if fence:
            indent = fence["indent"]
            start = index + 1
            end = next(i for i in range(start, len(lines)) if lines[i].strip() == "```")
            previous = next((line.strip() for line in reversed(lines[:index]) if line.strip()), "")
            if not previous.startswith("<!-- skip-snippet"):
                body = [line.removeprefix(indent) for line in lines[start:end]]
                snippets.append((start + 1, "\n".join(body)))
            index = end
        index += 1
    return snippets


class _PrintChecks(ast.NodeTransformer):
    """Replace ``print(...)  # expected`` with an assertion on the printed text."""

    def __init__(self, expectations: dict[int, str]) -> None:
        self.expectations = expectations

    def visit_Expr(self, node: ast.Expr) -> ast.Expr:
        call = node.value
        expected = self.expectations.get(node.end_lineno or 0)
        if (
            expected is not None
            and isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "print"
        ):
            assert not call.keywords, f"line {node.lineno}: checked print() takes no keywords"
            check = ast.Name("__check_print", ast.Load())
            node.value = ast.copy_location(
                ast.Call(check, [ast.Constant(expected), *call.args], []), call
            )
        return node


def _with_print_checks(code: str) -> ast.Module:
    """Parse ``code``, asserting the output of every print call that ends in ``# expected``.

    The expectation is the comment that follows the call's closing parenthesis, so calls that
    span several lines are checked too.
    """
    expectations = {
        token.start[0]: token.string.removeprefix("# ")
        for token in tokenize.generate_tokens(io.StringIO(code).readline)
        if token.type == tokenize.COMMENT and token.line[: token.start[1]].strip()
    }
    return ast.fix_missing_locations(_PrintChecks(expectations).visit(ast.parse(code)))


def _check_print(expected: str, *values: object) -> None:
    actual = " ".join(str(value) for value in values)
    assert actual == expected, f"documented output {expected!r} != actual {actual!r}"


DOCUMENTED = [path for path in MARKDOWN if _snippets(path)]


@pytest.mark.parametrize("path", DOCUMENTED, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_documentation_snippets_run_and_match_their_output(path: Path) -> None:
    namespace: dict[str, object] = {"__name__": "__docs__", "__check_print": _check_print}
    for line, code in _snippets(path):
        compiled = compile(_with_print_checks(code), f"{path.name}:{line}", "exec")
        exec(compiled, namespace)  # noqa: S102 - runs the documentation's own snippets


def test_snippet_extraction_honors_skip_markers_and_indentation() -> None:
    page = (
        "```python\nx = 1\n```\n\n<!-- skip-snippet: live -->\n```python\nboom()\n```\n"
        "1. Step:\n\n   ```python\n   if x:\n       y = 2\n   ```\n"
    )
    assert _parse_snippets(page) == [(2, "x = 1"), (12, "if x:\n    y = 2")]


def _printed(code: str) -> list[str]:
    calls: list[str] = []
    namespace = {"__check_print": lambda expected, *values: calls.append(expected)}
    exec(compile(_with_print_checks(code), "<test>", "exec"), namespace)  # noqa: S102
    return calls


def test_print_expectations_are_checked_on_single_and_multi_line_calls() -> None:
    assert _printed("print(1)  # 1") == ["1"]
    assert _printed("print(\n    1,\n    2,\n)  # 1 2\nprint('unchecked')\n# 3") == ["1 2"]
    with pytest.raises(AssertionError, match="documented output '2' != actual '1'"):
        exec(  # noqa: S102
            compile(_with_print_checks("print(1)  # 2"), "<test>", "exec"),
            {"__check_print": _check_print},
        )


def test_every_public_symbol_is_in_the_api_reference() -> None:
    reference = (DOCS / "api-reference.md").read_text(encoding="utf-8")
    modules = [
        "behaviorweave",
        "behaviorweave.integrations.langchain",
        "behaviorweave.integrations.langgraph",
        "behaviorweave.integrations.langgraph_xai",
    ]
    missing = [
        f"{module}.{name}"
        for module in modules
        for name in importlib.import_module(module).__all__
        if f"::: {module}.{name}\n" not in reference
    ]
    assert missing == []


def test_readme_links_resolve() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"\]\(([^)\s]+)\)", readme) + re.findall(r'src="([^"]+)"', readme)
    local = [t for t in targets if not t.startswith(("http://", "https://", "#", "mailto:"))]
    assert local
    assert [t for t in local if not (ROOT / t).exists()] == []


def test_every_diagram_is_rendered_and_used() -> None:
    sources = {path.stem for path in (DOCS / "diagrams").glob("*.mmd")}
    images = {path.stem for path in (DOCS / "assets" / "diagrams").glob("*.png")}
    assert sources == images
    text = "\n".join(path.read_text(encoding="utf-8") for path in MARKDOWN)
    assert [name for name in images if f"diagrams/{name}.png" not in text] == []


def _render_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "render_diagrams", ROOT / "scripts" / "render_diagrams.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rendered_diagrams_are_current() -> None:
    assert _render_script().check() == []


def test_the_diagram_check_reports_every_kind_of_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _render_script()
    sources, output = tmp_path / "diagrams", tmp_path / "images"
    shutil.copytree(DOCS / "diagrams", sources)
    shutil.copytree(DOCS / "assets" / "diagrams", output)
    monkeypatch.setattr(script, "SOURCES", sources)
    monkeypatch.setattr(script, "OUTPUT", output)
    monkeypatch.setattr(script, "CONFIG", sources / "mermaid-config.json")
    monkeypatch.setattr(script, "MANIFEST", sources / "manifest.json")
    assert script.check() == []

    (sources / "architecture.mmd").write_text("flowchart LR\n    a --> b\n", encoding="utf-8")
    (output / "escalation-ladder.png").write_bytes(b"not the rendered image")
    (output / "pattern-semantics.png").unlink()
    (output / "orphan.png").write_bytes(b"")
    (sources / "guarded-tool-call.mmd").unlink()

    assert script.check() == [
        "guarded-tool-call.png has no source diagram",
        "orphan.png has no source diagram",
        "architecture.png is out of date with architecture.mmd",
        "escalation-ladder.png was modified after it was rendered",
        "pattern-semantics.mmd has not been rendered",
        "the manifest lists guarded-tool-call, which has no source diagram",
    ]
    (sources / "manifest.json").unlink()
    assert "decision-pipeline.png is out of date with decision-pipeline.mmd" in script.check()


def test_the_diagram_check_command() -> None:
    completed = subprocess.run(  # noqa: S603 - runs this repository's own script
        [sys.executable, str(ROOT / "scripts" / "render_diagrams.py"), "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "All 5 diagrams are current."


def test_versions_are_consistent() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    latest = re.search(r"^## \[(?P<version>[^\]]+)\]", changelog, re.MULTILINE)
    assert latest is not None
    assert behaviorweave.__version__ == importlib.metadata.version("behaviorweave")
    assert latest["version"] == behaviorweave.__version__
