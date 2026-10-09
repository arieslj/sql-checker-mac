#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
    echo '请先安装 Python 3.10 或更新版本。'
    read -r -p '按回车退出' unused
    exit 1
fi
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import flask, sqlglot, sqlfluff' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",8765)); s.close()' || { echo '8765 端口已被占用，请关闭旧实例后重试。'; exit 1; }
echo '打开 http://127.0.0.1:8765；按 Ctrl+C 停止。'
(sleep 2; open 'http://127.0.0.1:8765') &
exec .venv/bin/python app.py
