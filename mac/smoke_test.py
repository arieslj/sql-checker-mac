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
        joined = post('check', 'select * from t a1 join u a5 on a5.id=a1.id join v a6 on a6.area=a1.area and a5.region=a1.region')['issues']
        assert joined[0]['code'] == 'JOIN_KEY_ALIAS_MISMATCH' and joined[0]['priority'] == 0
        assert 'a6.region = a1.region' in joined[0]['suggestion']
        grouped = post('check', 'select area,region,sum(amount) from synthetic_items group by area')['issues']
        assert grouped[0]['code'] == 'GROUP_NON_AGGREGATE' and grouped[0]['priority'] == 0 and grouped[0]['severity'] == 'error'
        missing = post('check', 'select area,sum(amount) from synthetic_items')['issues']
        assert missing[0]['code'] == 'GROUP_BY_MISSING' and missing[0]['priority'] == 0
        subtotal = post('check', 'select vehicle,reason,count(*) from synthetic_items group by rollup(vehicle)')['issues']
        assert subtotal[0]['code'] == 'GROUP_NON_AGGREGATE' and 'reason' in subtotal[0]['reason'] and subtotal[0]['priority'] == 0
        legitimate = post('check', 'select vehicle,reason,count(*) from synthetic_items group by grouping sets((vehicle),(reason),())')['issues']
        assert not any(i['severity']=='error' and i['code'].startswith('GROUP') for i in legitimate)
        print('Frozen backend checks passed: priority-0 aliases, ordinary and multi-dimensional groups, templates and formatting.')
    finally:
        p.terminate()
        p.wait(timeout=10)

if __name__ == '__main__':
    main()
