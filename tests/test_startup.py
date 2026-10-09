"""Startup regression checks: fast shell must not import the analysis engines."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def test_ui_server_import_is_lightweight():
    result = subprocess.run([sys.executable, '-c', "import sys; import app; assert 'checker' not in sys.modules; assert 'sqlfluff' not in sys.modules; assert 'sqlglot' not in sys.modules"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

def test_packaged_file_ui_is_self_contained(tmp_path):
    subprocess.run([sys.executable, str(ROOT/'mac/prepare-ui.py'), str(tmp_path)], check=True)
    page = (tmp_path/'index.html').read_text()
    assert 'href="style.css"' in page and 'src="app.js"' in page
    assert '/static/' not in page
    assert "connect-src 'none'" in page
    assert (tmp_path/'app.js').exists() and (tmp_path/'style.css').exists()
    assert '/static/app.js' in (ROOT/'static/index.html').read_text()
