"""Private desktop backend: ephemeral loopback port, no business connections."""
import multiprocessing

# Required before Flask/SQLFluff imports in a frozen macOS process.
# Prevent Python's resource tracker from relaunching the whole application.
if __name__ == '__main__':
    multiprocessing.freeze_support()

import logging
import threading
from werkzeug.serving import make_server
from app import app

if __name__ == '__main__':
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    server = make_server('127.0.0.1', 0, app)
    print(f'http://127.0.0.1:{server.server_port}', flush=True)
    def prewarm():
        try:
            import checker
            print('ENGINE_READY', flush=True)
        except Exception:
            print('ENGINE_FAILED', flush=True)
    threading.Thread(target=prewarm, name='sql-engine-prewarm', daemon=True).start()
    server.serve_forever()
