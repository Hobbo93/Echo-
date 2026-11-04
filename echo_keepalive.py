"""Keeps one part of Echo running: restarts it if it ever stops or crashes.

Run: py echo_keepalive.py echo_server.py   (echo_start.py does this for you)
While running it also asks Windows not to go to sleep (the screen can still
turn off), so Echo stays reachable from your phone. Closing the window stops it.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def keep_awake():
    if sys.platform == "win32":
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def main():
    script = sys.argv[1]
    if script == "echo_server.py":
        keep_awake()
        print("Echo is keeping this PC awake while it runs (the screen can still turn off).", flush=True)
    restarts = 0
    while True:
        started = time.time()
        code = subprocess.call([sys.executable, script], cwd=ROOT)
        if time.time() - started > 300:
            restarts = 0
        restarts += 1
        wait = min(300, 10 * restarts)  # back off if it keeps crashing straight away
        try:
            import echo_log
            echo_log.error("keepalive", note=f"{script} stopped (code {code}), restarting in {wait}s")
        except Exception:
            pass
        print(f"\n{script} stopped (code {code}). Restarting in {wait} seconds… "
              "Close this window to stop it.", flush=True)
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
