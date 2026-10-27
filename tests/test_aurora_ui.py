"""Static regression checks for the Opportunity OS Aurora Glass UI.

These checks verify asset wiring and important accessibility contracts;
they do not replace browser screenshot or interaction testing.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_workspace_loads_aurora_glass_after_base_styles():
    html = read("templates/workspace.html")
    assert html.index("workspace.css") < html.index("glass.css")
    assert 'href="/static/glass.css?v=4.0.0"' in html
    assert 'id="primary-nav"' in html
    assert 'id="content"' in html
    assert 'id="detail-dialog"' in html
    assert 'id="assistant-dialog"' in html
    assert 'data-action="theme"' in html
    assert 'aria-label="Find opportunities"' in html


def test_advanced_workspace_and_login_use_glass_styles():
    html = read("templates/index.html")
    assert html.index("filename='app.css'") < html.index("filename='glass-classic.css'")
    assert 'id="login-form"' in html
    assert 'id="main-content"' in html
    assert 'id="global-search-form"' in html


def test_design_system_covers_themes_breakpoints_and_accessibility():
    css = read("static/glass.css")
    assert ":root[data-theme=dark]" in css
    assert "#content[data-page=today]" in css
    assert ".workspace > main,.workspace > .workspace-footer" in css
    assert "position:sticky" in css
    assert "@media(max-width:700px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "@media(prefers-contrast:more)" in css
    assert "@supports not" in css
    assert "focus-visible" in css
    assert css.count("{") == css.count("}")


def test_advanced_style_covers_login_dashboard_and_responsive_motion():
    css = read("static/glass-classic.css")
    for selector in (".login-layout", ".login-card", ".sidebar", ".topbar", ".job-card"):
        assert selector in css
    assert "@media(max-width:760px)" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert css.count("{") == css.count("}")


def test_navigation_tracks_active_view_for_hero():
    script = read("static/workspace.js")
    assert "$('#content').dataset.page=state.page" in script
    assert "const ticket=++state.request;" in script
