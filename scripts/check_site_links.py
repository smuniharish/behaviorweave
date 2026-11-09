"""Check internal pages, assets, and anchors in the built Zensical site."""

from __future__ import annotations

import argparse
import sys
import tomllib
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if identifier := values.get("id"):
            self.ids.add(identifier)
        attribute = "href" if tag in {"a", "link"} else "src"
        if tag in {"a", "link", "img", "script"} and (target := values.get(attribute)):
            self.links.append(target)


def broken_links(site: Path, *, base_path: str = "") -> list[str]:
    """Return all missing internal pages, assets, and fragment targets."""
    site = site.resolve()
    pages: dict[Path, _Page] = {}
    for path in site.rglob("*.html"):
        page = _Page()
        page.feed(path.read_text(encoding="utf-8"))
        pages[path] = page
    problems = []
    for path, page in sorted(pages.items()):
        for href in page.links:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc:
                continue
            local_path = unquote(parts.path)
            if base_path:
                local_path = local_path.removeprefix(base_path)
            target = (
                (site / local_path.lstrip("/")).resolve()
                if parts.path.startswith("/")
                else (path.parent / local_path).resolve()
                if parts.path
                else path
            )
            if target.is_dir():
                target /= "index.html"
            where = path.relative_to(site).as_posix()
            if not target.is_relative_to(site) or not target.is_file():
                problems.append(f"{where}: missing target {href}")
            elif (
                parts.fragment
                and target in pages
                and unquote(parts.fragment) not in pages[target].ids
            ):
                problems.append(f"{where}: missing anchor {href}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Check a site directory, returning a nonzero exit status on errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", nargs="?", type=Path, default=Path("site"))
    site = parser.parse_args(argv).site
    if not site.is_dir():
        print(f"{site} does not exist; build the docs first.", file=sys.stderr)
        return 2
    with Path("zensical.toml").open("rb") as stream:
        config = tomllib.load(stream)
    base_path = urlsplit(config["project"]["site_url"]).path
    problems = broken_links(site, base_path=base_path)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"{len(problems)} broken internal links.")
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
