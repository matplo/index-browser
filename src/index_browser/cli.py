"""Command line entry point: ``index-browser [DIR]``."""

from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys

from . import __version__
from .core import IndexBrowserError, build


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="index-browser",
        description="Write an interactive 3D index.html (folders unfold into file cards; "
                    "files open in a new tab) for a directory tree. Re-run after adding files.",
        epilog="examples:\n"
               "  index-browser                      # index the current directory\n"
               "  index-browser public -t 'My talks' --link https://github.com/me/site\n"
               "  index-browser docs -x 'drafts/*' --serve",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("dir", nargs="?", default=".", help="directory to index (default: .)")
    p.add_argument("-o", "--output", metavar="FILE", help="page to write (default: DIR/index.html)")
    p.add_argument("-t", "--title", help="page title (default: the directory's name)")
    p.add_argument("-x", "--exclude", action="append", default=[], metavar="GLOB",
                   help="skip names or DIR-relative paths matching GLOB; repeatable "
                        "(dot-files are always skipped)")
    p.add_argument("--link", metavar="URL", help="link shown in the panel footer, e.g. the source repo")
    p.add_argument("--link-text", metavar="TEXT", help="label for --link (default: source)")
    p.add_argument("--no-git", action="store_true",
                   help="use file modification times instead of last-commit dates")
    p.add_argument("--fresh", action="store_true",
                   help="rewrite the page from the bundled template (picks up a newer UI, "
                        "drops hand edits); needed to replace an index.html not made by index-browser")
    p.add_argument("--check", action="store_true",
                   help="write nothing; exit 1 if the page is missing or out of date (for CI)")
    p.add_argument("--serve", action="store_true", help="then serve DIR on http://127.0.0.1:PORT")
    p.add_argument("--port", type=int, default=8000, help="port for --serve (default: 8000)")
    p.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return p


def serve(directory: str, port: int) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving {directory} at http://127.0.0.1:{port}/  (Ctrl-C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        res = build(args.dir, args.output, title=args.title, excludes=args.exclude,
                    link=args.link, link_text=args.link_text, use_git=not args.no_git,
                    fresh=args.fresh, dry_run=args.check)
    except IndexBrowserError as exc:
        print(f"index-browser: error: {exc}", file=sys.stderr)
        return 2

    try:
        rel = os.path.relpath(res.output)
    except ValueError:  # Windows: output on another drive than the cwd
        rel = ".."
    where = str(res.output) if rel.startswith("..") else rel
    summary = f"{res.files} files in {res.folders} folders, {_human(res.size)}"
    if args.check:
        if res.changed:
            print(f"{where} is out of date ({summary}); run index-browser", file=sys.stderr)
            return 1
        if not args.quiet:
            print(f"{where} is up to date ({summary})")
        return 0
    if not args.quiet:
        verb = "Created" if res.created else "Updated" if res.changed else "Unchanged:"
        print(f"{verb} {where} — {summary}")
    if args.serve:
        serve(os.path.abspath(args.dir), args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
