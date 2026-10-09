"""Regression: a frozen resource tracker must not start another SQL server."""
from pathlib import Path
import os
import selectors
import subprocess
import sys

def main():
    root = Path(__file__).resolve().parent
    binary = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root/'dist/SQL 检查器.app/Contents/Resources/backend/SQLCheckerBackend/SQLCheckerBackend'
    read_fd, write_fd = os.pipe()
    p = subprocess.Popen([str(binary), '-B', '-S', '-I', '-c', f'from multiprocessing.resource_tracker import main;main({read_fd})'], pass_fds=(read_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.close(read_fd)
    try:
        selector = selectors.DefaultSelector()
        selector.register(p.stdout, selectors.EVENT_READ)
        # Correct resource tracker waits silently for the pipe to close.
        assert not selector.select(timeout=2), 'Resource tracker incorrectly emitted application output'
        os.close(write_fd); write_fd = None
        stdout, stderr = p.communicate(timeout=10)
        assert p.returncode == 0, stderr.decode()
        assert stdout == b'', stdout.decode()
        print('Frozen multiprocessing resource-tracker routing passed; no SQL server relaunched.')
    finally:
        selector.close()
        if write_fd is not None: os.close(write_fd)
        if p.poll() is None: p.terminate(); p.wait(timeout=10)

if __name__ == '__main__': main()
