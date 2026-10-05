"""Render the Mermaid diagrams in docs/diagrams to PNG images in docs/assets/diagrams.

Rendering requires Node.js (``npx``). A locally installed Chrome or Edge is used when one is
found, so no browser download is needed; set ``PUPPETEER_EXECUTABLE_PATH`` to choose another
browser. Every render records a fingerprint of its inputs and of the image it produced in
``docs/diagrams/manifest.json``, so ``--check`` can verify without Node.js that each image is
current and that no image or source is orphaned.

Usage:
    uv run python scripts/render_diagrams.py          # render every diagram
    uv run python scripts/render_diagrams.py --check  # verify that the images are current
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "docs" / "diagrams"
OUTPUT = ROOT / "docs" / "assets" / "diagrams"
CONFIG = SOURCES / "mermaid-config.json"
MANIFEST = SOURCES / "manifest.json"
MERMAID_CLI = "@mermaid-js/mermaid-cli@12.0.0"
OPTIONS = ("--backgroundColor", "white", "--scale", "2")
BROWSERS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def _digest(*parts: bytes) -> str:
    sha = hashlib.sha256()
    for part in parts:
        sha.update(len(part).to_bytes(8, "big"))
        sha.update(part)
    return sha.hexdigest()


def _text(path: Path) -> bytes:
    # Normalized line endings give every checkout, on any platform, the same fingerprint.
    return path.read_bytes().replace(b"\r\n", b"\n")


def source_fingerprint(source: Path) -> str:
    """Return the fingerprint of every input that determines ``source``'s rendered image."""
    return _digest(MERMAID_CLI.encode(), " ".join(OPTIONS).encode(), _text(CONFIG), _text(source))


def image_fingerprint(image: Path) -> str:
    """Return the fingerprint of a rendered image."""
    return _digest(image.read_bytes())


def check() -> list[str]:
    """Return one message per stale, missing, modified, or orphaned diagram; empty when current."""
    recorded = (
        json.loads(MANIFEST.read_text(encoding="utf-8")).get("diagrams", {})
        if MANIFEST.exists()
        else {}
    )
    sources = {path.stem: path for path in SOURCES.glob("*.mmd")}
    images = {path.stem: path for path in OUTPUT.glob("*.png")}
    problems = [
        f"{name}.png has no source diagram" for name in sorted(images.keys() - sources.keys())
    ]
    for name, source in sorted(sources.items()):
        entry = recorded.get(name, {})
        if name not in images:
            problems.append(f"{name}.mmd has not been rendered")
        elif entry.get("source") != source_fingerprint(source):
            problems.append(f"{name}.png is out of date with {name}.mmd")
        elif entry.get("image") != image_fingerprint(images[name]):
            problems.append(f"{name}.png was modified after it was rendered")
    problems.extend(
        f"the manifest lists {name}, which has no source diagram"
        for name in sorted(recorded.keys() - sources.keys())
    )
    return problems


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    # Trust the operating system's certificate store (corporate proxies) on Node.js 22+.
    env.setdefault("NODE_OPTIONS", "--use-system-ca")
    browser = env.get("PUPPETEER_EXECUTABLE_PATH") or next(
        (path for path in BROWSERS if Path(path).exists()), None
    )
    if browser:
        env["PUPPETEER_EXECUTABLE_PATH"] = browser
        env["PUPPETEER_SKIP_DOWNLOAD"] = "true"
    return env


def render() -> int:
    """Render every diagram, remove orphaned images, and rewrite the manifest."""
    npx = shutil.which("npx")
    if npx is None:
        print("npx was not found. Install Node.js to render diagrams.", file=sys.stderr)
        return 1
    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = _environment()
    diagrams: dict[str, dict[str, str]] = {}
    for source in sorted(SOURCES.glob("*.mmd")):
        target = OUTPUT / f"{source.stem}.png"
        command = [
            npx,
            "--yes",
            MERMAID_CLI,
            "--input",
            str(source),
            "--output",
            str(target),
            "--configFile",
            str(CONFIG),
            *OPTIONS,
        ]
        subprocess.run(command, check=True, env=env)  # noqa: S603 - fixed renderer and paths
        diagrams[source.stem] = {
            "source": source_fingerprint(source),
            "image": image_fingerprint(target),
        }
        print(f"rendered {target.relative_to(ROOT).as_posix()}")
    for orphan in sorted(OUTPUT.glob("*.png")):
        if orphan.stem not in diagrams:
            orphan.unlink()
            print(f"removed orphaned {orphan.relative_to(ROOT).as_posix()}")
    manifest = {"renderer": MERMAID_CLI, "diagrams": diagrams}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Render the diagrams, or verify with ``--check`` that the rendered images are current."""
    parser = argparse.ArgumentParser(
        description="Render the Mermaid diagrams to PNG, or check that the images are current."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify that every image is current without rendering (no Node.js needed)",
    )
    if not parser.parse_args(argv).check:
        return render()
    problems = check()
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        print("Run `uv run python scripts/render_diagrams.py` to re-render.", file=sys.stderr)
        return 1
    print(f"All {len(list(SOURCES.glob('*.mmd')))} diagrams are current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
