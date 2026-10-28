# ECHO AI - AUTOMATIC UPDATER
# Windows 11 / GitHub

import subprocess
import sys
import os
from datetime import datetime

ECHO_FOLDER = os.path.dirname(
    os.path.abspath(__file__)
)

def run(command):
    return subprocess.run(
        command,
        cwd=ECHO_FOLDER,
        capture_output=True,
        text=True
    )

def update_echo():
    print("ECHO: Checking for updates...")

    if not os.path.isdir(
        os.path.join(ECHO_FOLDER, ".git")
    ):
        print("Git repository not found.")
        print("Clone Echo onto your PC first.")
        return

    check = run(["git", "status", "--porcelain"])

    if check.returncode != 0:
        print("Git is not installed or unavailable.")
        return

    if check.stdout.strip():
        print("Local changes detected.")
        print("Update paused to protect your files.")
        return

    fetch = run(["git", "fetch", "origin"])

    if fetch.returncode != 0:
        print("Could not contact GitHub.")
        return

    branch = run([
        "git", "branch", "--show-current"
    ]).stdout.strip()

    if not branch:
        print("No active Git branch.")
        return

    local = run([
        "git", "rev-parse", "HEAD"
    ]).stdout.strip()

    remote_check = run([
        "git", "rev-parse", f"origin/{branch}"
    ])

    if remote_check.returncode != 0:
        print("Remote branch not found.")
        return

    remote = remote_check.stdout.strip()

    if local == remote:
        print("ECHO: Already up to date.")
        return

    safe = run([
        "git", "merge-base", "--is-ancestor",
        "HEAD", f"origin/{branch}"
    ])

    if safe.returncode != 0:
        print("Branch has diverged.")
        print("Manual review required.")
        return

    backup = run([
        "git", "branch",
        "backup-" + datetime.now().strftime(
            "%Y%m%d-%H%M%S"
        )
    ])

    if backup.returncode != 0:
        print("Backup failed. Update cancelled.")
        return

    update = run([
        "git", "merge", "--ff-only",
        f"origin/{branch}"
    ])

    if update.returncode == 0:
        print("ECHO: Code updated successfully.")
        print("Restart Echo to apply changes.")
    else:
        print("Update failed.")
        print(update.stderr)

if __name__ == "__main__":
    update_echo()
