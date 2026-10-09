"""Prepare packaged file UI. No remote URLs, external scripts, or SQL persistence."""
from pathlib import Path
import sys
source = Path(__file__).resolve().parents[1] / 'static'
target = Path(sys.argv[1])
target.mkdir(parents=True, exist_ok=True)
for name in ('index.html', 'style.css', 'app.js'):
    text = (source / name).read_text()
    if name == 'index.html':
        text = text.replace('/static/style.css', 'style.css').replace('/static/app.js', 'app.js')
        text = text.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'self\'; style-src \'self\'; script-src \'self\'; connect-src \'none\'; object-src \'none\'; base-uri \'none\'">')
    (target / name).write_text(text)
