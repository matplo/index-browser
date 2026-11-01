# index-browser

Turn any directory of files into an interactive **3D `index.html`** for the files: talks, papers,
figures and media. Folders are glowing nodes that **unfold** into cards for their files. Click a
card to open the file in a new tab. A side panel adds search, type filters and a plain list.

Made for static hosting such as GitHub Pages: one self-contained HTML file, no build step, and
no runtime dependencies (three.js loads from a CDN).

```sh
pip install index-browser          # or: uv tool install index-browser / pipx install index-browser

cd my-site/public
index-browser                      # writes ./index.html for everything below .
index-browser --serve              # …and previews it at http://127.0.0.1:8000
```

Live example: <https://matplo.github.io/publix/>

## What you get

- **Unfolding radial tree** (three.js). Every visible file gets an equal slice of the circle, and
  unfolding sweeps cards out along arcs while the folder you clicked stays put.
- **Real thumbnails.** Images show their contents, videos a frame, and HTML files their `<title>`.
  PDFs and other types get typed icon cards.
- **Side panel** with live search (`/` to focus), type filters (HTML · PDF · Image · Video · …),
  and sizes and dates. It stays in sync with the 3D view.
- **Deep links.** `index.html#talks/2026` opens with that folder unfolded.
- **Graceful fallbacks.** Without WebGL you get a plain list. With JavaScript off you get a static
  `<ul>` of links. The page honours `prefers-reduced-motion`, and on a phone the panel becomes a
  bottom sheet.
- **Dates from git.** Inside a git repo each file shows its last commit date (works in CI, where
  file times are meaningless). Otherwise it uses modification times.

## Usage

```
index-browser [DIR] [-o FILE] [-t TITLE] [-x GLOB ...] [--link URL] [--fresh] [--check] [--serve]
```

| option | |
|---|---|
| `DIR` | directory to index (default `.`) |
| `-o, --output FILE` | where to write the page (default `DIR/index.html`) |
| `-t, --title TITLE` | page title (default: the directory's name) |
| `-x, --exclude GLOB` | skip names or `DIR`-relative paths matching `GLOB` (repeatable). Dot-files, `__pycache__` and `node_modules` are always skipped |
| `--link URL` / `--link-text` | a link in the panel footer, e.g. your repo |
| `--no-git` | use modification times, not commit dates |
| `--fresh` | rewrite the page from the bundled template (see below) |
| `--check` | write nothing; exit 1 if the page is missing or stale |
| `--serve [--port N]` | serve `DIR` locally after building |

### Re-running and hand edits

The page has three generated regions: the `<title>`, a JSON data block and the no-JS list.
Re-running `index-browser` rewrites **only those**, so you can restyle the page by hand and keep
refreshing it. After upgrading index-browser, run with `--fresh` to pick up the new page design;
this discards hand edits. index-browser never overwrites an `index.html` it didn't create unless
you pass `--fresh`.

### Opening the file directly

Browsers block WebGL from using local images when a page is opened as `file://…`. The page
still works but shows icon cards instead of thumbnails there. Serve it over HTTP
(`index-browser --serve`, `python -m http.server`, GitHub Pages, …) for the full view.

## GitHub Pages

Generate the index in the deploy workflow so it never goes stale:

```yaml
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # full history → per-file commit dates
      - run: pipx run index-browser public --link "https://github.com/${{ github.repository }}"
      - uses: actions/upload-pages-artifact@v3
        with:
          path: ./public
```

## Python API

```python
from index_browser import build

res = build("public", title="Talks", excludes=["drafts/*"])
print(res.output, res.files, res.changed)
```

## License

MIT
