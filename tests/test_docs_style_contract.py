from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_api_reference_wraps_stoplight_embed():
    reference_md = (REPO_ROOT / "site" / "docs" / "api" / "reference.md").read_text()

    assert 'class="api-reference-embed"' in reference_md
    assert "<elements-api" in reference_md


def test_stoplight_svg_icons_are_not_scaled_by_mkdocs_typeset_rule():
    css = (REPO_ROOT / "site" / "docs" / "stylesheets" / "extra.css").read_text()

    assert "elements-api svg.svg-inline--fa" in css
    assert "height: 1em" in css
    assert "max-width: none" in css


def test_stoplight_embed_has_light_surface_in_dark_docs_theme():
    css = (REPO_ROOT / "site" / "docs" / "stylesheets" / "extra.css").read_text()

    assert ".api-reference-embed" in css
    assert "color-scheme: light" in css
    assert "background: #ffffff" in css
    assert ".api-reference-embed elements-api :is(h1, h2, h3, h4, h5, h6)" in css
