"""Dependency-free checks for the static NexusVault prototype."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
required = [
    "index.html",
    "styles.css",
    "result.css",
    "animations.css",
    "contributor.css",
    "app.js",
    "favicon.svg",
    "README.md",
    "LICENSE",
]

for filename in required:
    path = ROOT / filename
    assert path.is_file(), f"missing required file: {filename}"
    assert path.stat().st_size > 0, f"empty required file: {filename}"

html = (ROOT / "index.html").read_text(encoding="utf-8")
app = (ROOT / "app.js").read_text(encoding="utf-8")
readme = (ROOT / "README.md").read_text(encoding="utf-8")

assert '<html lang="en">' in html
assert '<meta name="viewport"' in html
assert 'id="query-input"' in html
assert 'id="ask-button"' in html
assert 'aria-label="Primary navigation"' in html
assert 'href="https://github.com/DineshDhanoki/nexusvault-rag/issues"' in html
assert re.search(r"<title>[^<]+</title>", html)
assert "function escapeHtml" in app
assert "escapeHtml(match.copy)" in app
assert "CONTRIBUTING.md" in readme
assert "SECURITY.md" in readme
assert "good first issue" in readme
assert "github.io/nexusvault-rag" in readme

print(f"smoke checks passed ({len(required)} required files, {len(html)} HTML characters)")

# Persona menu keyboard contract. The real behavior (Tab closes the menu and
# moves focus forward, Escape restores the trigger, one roving tab stop) was
# checked in Chromium; these keep the dependency-free CI from losing it.
assert 'aria-haspopup="menu"' in html
assert 'role="menuitemradio"' in html
assert html.count('role="menuitemradio"') == 4
assert html.count('tabindex="-1" data-role=') == 3
assert 'tabindex="0" data-role=' in html
assert "function setRoleTabStop" in app
assert "if(e.key==='Tab')" in app
assert "setRoleMenuOpen(false);roleButton.focus()" in app
assert "next?.focus()" in app
