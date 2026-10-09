"""Synthetic smoke checks against the frozen backend, independent of system Python deps."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import urllib.request

def main():
    root = Path(__file__).resolve().parent
    binary = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / 'dist/SQL 检查器.app/Contents/Resources/backend/SQLCheckerBackend/SQLCheckerBackend'
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
        env.pop(key, None)
    p = subprocess.Popen([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd='/private/tmp', text=True)
    try:
        selector = selectors.DefaultSelector()
        selector.register(p.stdout, selectors.EVENT_READ)
        assert selector.select(timeout=40), 'Backend startup timed out'
        url = p.stdout.readline().strip()
        assert url.startswith('http://127.0.0.1:'), p.stderr.read() if p.poll() is not None else url
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        def post(action, sql):
            request = urllib.request.Request(url + '/api/' + action, data=json.dumps({'sql': sql}).encode(), headers={'Content-Type':'application/json'})
            with opener.open(request, timeout=30) as response:
                return json.load(response)
        assert 'SQL'.encode() in opener.open(url).read()
        result = post('check', 'select\n    a/b\nfrom t')
        assert any(i['code'] == 'DIVISION_ZERO' and i['line'] == 2 for i in result['issues'])
        assert any(i['code'] == 'GROUP_TRAILING_COMMA' for i in post('check', 'select a from t group by a,')['issues'])
        result = post('format', "SELECT\n    a,\n    b\nFROM t WHERE dt='${dt}'")['sql']
        assert 'select' in result and '${dt}' in result and '\n    ,' in result
        print('Frozen backend smoke checks passed: startup, assets, lint, rules, format, templates.')
    finally:
        p.terminate()
        p.wait(timeout=10)

if __name__ == '__main__':
    main()
