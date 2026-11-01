import json
import re

import pytest

from index_browser import IndexBrowserError, build, scan
from index_browser.cli import main
from index_browser.core import kind_of, template

MANIFEST = re.compile(r'id="ib-manifest">(.*?)</script>', re.S)


def manifest(page_path):
    return json.loads(MANIFEST.search(page_path.read_text(encoding="utf-8")).group(1))


@pytest.fixture
def site(tmp_path):
    (tmp_path / "talks").mkdir()
    (tmp_path / "talks" / "Slides & notes.html").write_text(
        "<html><head><title> My &amp; talk </title></head></html>", encoding="utf-8")
    (tmp_path / "talks" / "paper.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "logo.PNG").write_bytes(b"\x89PNG")
    (tmp_path / "empty").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "x.txt").write_text("x")
    (tmp_path / ".DS_Store").write_bytes(b"")
    (tmp_path / "readme.md").write_text("# hi")
    return tmp_path


def test_creates_page_with_tree(site):
    res = build(site, use_git=False)
    assert res.created and res.changed
    assert (res.files, res.folders) == (4, 2)
    m = manifest(site / "index.html")
    assert m["title"] == site.name
    names = [c["name"] for c in m["root"]["children"]]
    assert names == ["img", "talks", "readme.md"]          # dirs first, empty/hidden dropped
    talks = m["root"]["children"][1]["children"]
    html_file = next(c for c in talks if c["kind"] == "html")
    assert html_file["title"] == "My & talk"
    assert html_file["href"] == "talks/Slides%20%26%20notes.html"
    assert kind_of("logo.PNG") == ("png", "image")


def test_rerun_is_idempotent_and_skips_own_output(site):
    build(site, use_git=False)
    res = build(site, use_git=False)
    assert not res.changed
    paths = json.dumps(manifest(site / "index.html"))
    assert '"index.html"' not in paths


def test_keeps_hand_edits_outside_generated_regions(site):
    build(site, use_git=False)
    page = site / "index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("</style>", "/* mine */</style>"),
                    encoding="utf-8")
    (site / "new.txt").write_text("new")
    build(site, use_git=False)
    text = page.read_text(encoding="utf-8")
    assert "/* mine */" in text and "new.txt" in text
    build(site, use_git=False, fresh=True)
    assert "/* mine */" not in page.read_text(encoding="utf-8")


def test_refuses_foreign_index(site):
    (site / "index.html").write_text("<h1>hand made</h1>")
    with pytest.raises(IndexBrowserError):
        build(site, use_git=False)
    build(site, use_git=False, fresh=True)
    assert "ib-manifest" in (site / "index.html").read_text(encoding="utf-8")


def test_script_breakout_is_escaped(tmp_path):
    # File names can't contain "/" (nor "<" on Windows), but HTML titles and --title can.
    (tmp_path / "a&b.html").write_text("<title>x&lt;/script&gt;&lt;b&gt;</title>", encoding="utf-8")
    build(tmp_path, use_git=False, title="T</title>")
    text = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert text.count("</script>") == template().count("</script>")
    assert "<title>T&lt;/title&gt;</title>" in text
    item = manifest(tmp_path / "index.html")["root"]["children"][0]
    assert item["title"] == "x</script><b>" and item["name"] == "a&b.html"
    assert 'href="a%26b.html"' in text and ">a&amp;b.html</a>" in text


def test_excludes_and_link(site):
    build(site, use_git=False, excludes=["img", "*.md"], link="https://example.org/repo", title="Site")
    m = manifest(site / "index.html")
    assert [c["name"] for c in m["root"]["children"]] == ["talks"]
    assert m["link"] == "https://example.org/repo" and m["title"] == "Site"


def test_scan_custom_output_elsewhere(site, tmp_path_factory):
    out = tmp_path_factory.mktemp("out") / "listing.html"
    build(site, out, use_git=False)
    assert out.is_file() and not (site / "index.html").exists()
    assert scan(site, use_git=False)["children"]


def test_cli_check_and_errors(site, capsys):
    assert main([str(site), "--no-git", "--check"]) == 1      # missing page
    assert main([str(site), "--no-git", "-q"]) == 0
    assert main([str(site), "--no-git", "--check"]) == 0
    (site / "more.pdf").write_bytes(b"%PDF")
    assert main([str(site), "--no-git", "--check"]) == 1
    assert main([str(site / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().err
