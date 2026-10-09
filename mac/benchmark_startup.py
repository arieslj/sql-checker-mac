"""Measure packaged loopback backend with synthetic SQL. Never reads business data."""
import json
import os
from pathlib import Path
import selectors
import statistics
import subprocess
import sys
import time
import urllib.request

binary = Path(sys.argv[1]).resolve()
count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
samples = []
for _ in range(count):
    start = time.perf_counter()
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'): env.pop(key, None)
    p = subprocess.Popen([str(binary)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd='/private/tmp', env=env)
    try:
        selector = selectors.DefaultSelector()
        selector.register(p.stdout, selectors.EVENT_READ)
        assert selector.select(45), 'startup timeout'
        url = p.stdout.readline().strip()
        assert url.startswith('http://127.0.0.1:')
        ready = time.perf_counter()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        assert opener.open(url, timeout=30).status == 200
        page = time.perf_counter()
        req = urllib.request.Request(url + '/api/check', data=json.dumps({'sql':'select a / b from synthetic_table'}).encode(), headers={'Content-Type':'application/json'})
        result = json.load(opener.open(req, timeout=45))
        assert any(i['code']=='DIVISION_ZERO' for i in result['issues'])
        done = time.perf_counter()
        samples.append({'server_ready':ready-start, 'page_ready':page-start, 'first_check':done-page, 'total_to_checked':done-start})
    finally:
        p.terminate(); p.wait(timeout=10); selector.close()
report = {'samples':samples, 'median_seconds': {key:round(statistics.median(s[key] for s in samples),4) for key in samples[0]}}
print(json.dumps(report, indent=2))
