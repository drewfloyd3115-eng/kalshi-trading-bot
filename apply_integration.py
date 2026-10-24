"""Idempotently add CFB Model page to the EXISTING Kalshi Trade Lab app.

Usage (inside the existing repository, after copying cfb_model/ here):
    python apply_integration.py

Creates timestamp-free .bak backups the first time changes are applied.
"""
from pathlib import Path


def _patch_smoke_tests(repo:Path):
    """Update existing fixed-size navigation test when present."""
    path=repo/"test_sports_ui.py"
    if not path.exists():return
    contents=path.read_text(encoding="utf-8")
    updated=contents.replace("self.assertEqual(len(nav.options), 5)","self.assertEqual(len(nav.options), 6)")
    updated=updated.replace('"Research", "Home"):','"CFB Model", "Research", "Home"):')
    if updated!=contents:
        backup=path.with_suffix(".py.bak")
        if not backup.exists(): backup.write_text(contents,encoding="utf-8")
        path.write_text(updated,encoding="utf-8")


def apply(repo:Path):
    navigation=repo/'sports_ui.py'
    app=repo/'app.py'
    if not navigation.exists() or not app.exists():
        raise FileNotFoundError('Run this in the existing kalshi-trading-bot repository root')
    if not (repo/'cfb_model'/'ui.py').exists():
        raise FileNotFoundError('Copy the cfb_model/ package to repository root first')
    contents=navigation.read_text(encoding='utf-8')
    expected='PAGES = ["Home", "Opportunities", "Market Detail", "Portfolio", "Research"]'
    replacement='PAGES = ["Home", "Opportunities", "Market Detail", "Portfolio", "CFB Model", "Research"]'
    if expected in contents:
        backup=navigation.with_suffix('.py.bak')
        if not backup.exists():backup.write_text(contents,encoding='utf-8')
        navigation.write_text(contents.replace(expected,replacement,1),encoding='utf-8')
    elif replacement not in contents:
        raise ValueError('Navigation structure differs; review sports_ui.py manually')
    body=app.read_text(encoding='utf-8')
    anchor='else:\n    if "quick_results" in st.session_state:'
    inserted='elif page == "CFB Model":\n    from cfb_model.ui import render_model_ui\n    render_model_ui()\nelse:\n    if "quick_results" in st.session_state:'
    if inserted in body:
        _patch_smoke_tests(repo)
        return 'Already integrated'
    if anchor not in body:raise ValueError('App routing differs; review app.py manually')
    backup=app.with_suffix('.py.bak')
    if not backup.exists():backup.write_text(body,encoding='utf-8')
    app.write_text(body.replace(anchor,inserted,1),encoding='utf-8')
    _patch_smoke_tests(repo)
    return 'Integrated: CFB Model tab added; existing behavior retained'


if __name__=='__main__':print(apply(Path.cwd()))
