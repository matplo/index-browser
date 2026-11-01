"""Scan a directory tree and write/refresh an interactive index.html for it."""

from __future__ import annotations

import datetime as dt
import fnmatch
import html
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable
from urllib.parse import quote

KINDS = {
    "html": {"html", "htm", "xhtml"},
    "pdf": {"pdf"},
    "image": {"png", "jpg", "jpeg", "gif", "webp", "svg", "avif", "bmp", "ico", "tif", "tiff"},
    "video": {"mp4", "webm", "mov", "m4v", "ogv"},
    "audio": {"mp3", "wav", "ogg", "oga", "m4a", "flac", "aac"},
    "text": {"md", "txt", "csv", "tsv", "json", "yaml", "yml", "xml", "log", "tex", "ipynb"},
}
EXT_KIND = {ext: kind for kind, exts in KINDS.items() for ext in exts}
DEFAULT_EXCLUDES = (".*", "__pycache__", "node_modules", "Thumbs.db", "desktop.ini")

_TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)
_PAGE_TITLE_RE = re.compile(r"<title>.*?</title>", re.S)
_MANIFEST_RE = re.compile(r'(<script type="application/json" id="ib-manifest">)(.*?)(</script>)', re.S)
_STATIC_RE = re.compile(r"(<!-- index-browser:static -->)(.*?)(<!-- /index-browser:static -->)", re.S)


class IndexBrowserError(Exception):
    """Raised for problems the user can fix (bad paths, foreign index.html, ...)."""


@dataclass
class Result:
    output: Path
    files: int
    folders: int
    size: int
    changed: bool
    created: bool


def template() -> str:
    """The bundled page template."""
    return resources.files(__package__).joinpath("template.html").read_text(encoding="utf-8")


def _iso_utc(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def kind_of(name: str) -> tuple[str, str]:
    """Return (extension, kind) for a file name."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
    return ext, EXT_KIND.get(ext, "other")


def git_dates(root: Path) -> dict[str, str]:
    """Map path (relative to root) -> ISO date of the last commit that touched it.

    Returns {} when root is not inside a git work tree or git is unavailable.
    """
    cmd = ["git", "-c", "core.quotepath=off", "log", "--format=%x01%ct",
           "--name-only", "--relative", "--", "."]
    try:
        out = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    dates: dict[str, str] = {}
    current = None
    for line in out.splitlines():
        if line.startswith("\x01"):
            current = _iso_utc(int(line[1:]))
        elif line and current:
            dates.setdefault(line, current)  # log is newest-first
    return dates


def html_title(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            head = fh.read(256 * 1024)
    except OSError:
        return None
    m = _TITLE_RE.search(head)
    if not m:
        return None
    title = " ".join(html.unescape(m.group(1).decode("utf-8", "replace")).split())
    return title[:200] or None


def _excluded(rel: str, name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel, p) for p in patterns)


def scan(root: Path, excludes: Iterable[str] = (), *, skip: Iterable[str] = (),
         use_git: bool = True) -> dict:
    """Walk root and return the nested manifest tree (dirs first, then files, by name)."""
    root = Path(root).resolve()
    patterns = list(DEFAULT_EXCLUDES) + list(excludes)
    skip = set(skip)
    dates = git_dates(root) if use_git else {}

    def walk(directory: Path) -> dict:
        rel_dir = "" if directory == root else directory.relative_to(root).as_posix()
        node = {"type": "dir", "name": directory.name, "path": rel_dir, "children": []}
        try:
            entries = sorted(os.scandir(directory), key=lambda e: (e.name.lower(), e.name))
        except OSError as exc:
            print(f"index-browser: warning: cannot read {directory}: {exc}", file=sys.stderr)
            return node
        dirs, files = [], []
        for entry in entries:
            rel = f"{rel_dir}/{entry.name}" if rel_dir else entry.name
            if rel in skip or _excluded(rel, entry.name, patterns):
                continue
            if entry.is_dir(follow_symlinks=False):
                sub = walk(Path(entry.path))
                if sub["children"]:
                    dirs.append(sub)
            elif entry.is_file():
                st = entry.stat()
                ext, kind = kind_of(entry.name)
                item = {
                    "type": "file", "name": entry.name, "path": rel, "href": quote(rel),
                    "ext": ext, "kind": kind, "size": st.st_size,
                    "mtime": dates.get(rel) or _iso_utc(st.st_mtime),
                }
                if kind == "html":
                    title = html_title(Path(entry.path))
                    if title:
                        item["title"] = title
                files.append(item)
        node["children"] = dirs + files
        return node

    return walk(root)


def tally(node: dict) -> tuple[int, int, int]:
    """(files, folders, bytes) below node."""
    files = folders = size = 0
    for child in node["children"]:
        if child["type"] == "dir":
            f, d, s = tally(child)
            files, folders, size = files + f, folders + d + 1, size + s
        else:
            files, size = files + 1, size + child["size"]
    return files, folders, size


def static_list(node: dict) -> str:
    """Plain nested <ul> of links, shown when JavaScript is off."""
    parts = ["<ul>"]
    for child in node["children"]:
        name = html.escape(child["name"])
        if child["type"] == "dir":
            parts.append(f"<li><strong>{name}/</strong>{static_list(child)}</li>")
        else:
            href = html.escape(child["href"], quote=True)
            parts.append(f'<li><a href="{href}" target="_blank" rel="noopener">{name}</a></li>')
    parts.append("</ul>")
    return "".join(parts)


def render(page: str, tree: dict, title: str, link: str | None = None,
           link_text: str | None = None) -> str:
    """Fill the generated regions of page with tree's data."""
    manifest: dict = {"title": title, "root": dict(tree, name=title)}
    if link:
        manifest["link"] = link
        if link_text:
            manifest["linkText"] = link_text
    # Escape every "<" so names can never close the <script> element early.
    data = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    page = _MANIFEST_RE.sub(lambda m: m.group(1) + data + m.group(3), page, count=1)
    page = _STATIC_RE.sub(lambda m: m.group(1) + static_list(tree) + m.group(3), page, count=1)
    return _PAGE_TITLE_RE.sub(lambda m: f"<title>{html.escape(title)}</title>", page, count=1)


def is_generated(page: str) -> bool:
    return bool(_MANIFEST_RE.search(page))


def build(root: str | os.PathLike = ".", output: str | os.PathLike | None = None, *,
          title: str | None = None, excludes: Iterable[str] = (), link: str | None = None,
          link_text: str | None = None, use_git: bool = True, fresh: bool = False,
          dry_run: bool = False) -> Result:
    """Scan root and create or refresh its index page.

    An existing page made by index-browser is updated in place (hand edits outside the
    generated regions survive). ``fresh=True`` rewrites it from the bundled template, and is
    required to replace an index.html that index-browser did not create.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise IndexBrowserError(f"{root} is not a directory")
    out = Path(output).resolve() if output else root / "index.html"
    title = title or root.name or "index"

    existing = out.read_text(encoding="utf-8") if out.is_file() else None
    if existing is not None and not fresh and not is_generated(existing):
        raise IndexBrowserError(f"{out} exists and was not made by index-browser "
                          "(use --fresh to replace it)")
    base = template() if fresh or existing is None else existing

    skip = []
    if out.parent == root or root in out.parents:
        skip.append(out.relative_to(root).as_posix())
    tree = scan(root, excludes, skip=skip, use_git=use_git)
    page = render(base, tree, title, link, link_text)

    changed = page != existing
    if changed and not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
    files, folders, size = tally(tree)
    return Result(out, files, folders, size, changed, existing is None)
