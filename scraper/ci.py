"""Shell-neutral helpers for the workflow, so the same steps run on Windows PowerShell, Mac and Linux.

  python scraper/ci.py plan     -> decides the weekly jobs, writes them to $GITHUB_OUTPUT
  python scraper/ci.py commit   -> commits data/ and pushes it
  python scraper/ci.py fail MSG -> prints a GitHub error annotation and exits 1
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def plan() -> None:
    dow = datetime.now(timezone.utc).isoweekday()  # 1=Mon .. 7=Sun
    stores = dow == 1 or not (ROOT / "data" / "stores.json").exists() or os.environ.get("IN_STORES") == "true"
    discover = dow == 7 or os.environ.get("IN_DISCOVER") == "true"
    out = os.environ.get("GITHUB_OUTPUT")
    lines = f"stores={'true' if stores else 'false'}\ndiscover={'true' if discover else 'false'}\n"
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(lines)
    print(lines.strip())


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)


def commit() -> None:
    git("config", "user.name", "basketwise-bot")
    git("config", "user.email", "basketwise-bot@users.noreply.github.com")
    git("add", "data")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("no data changes")
        return
    git("commit", "-m", f"data: prices {datetime.now(timezone.utc):%Y-%m-%d}")
    git("pull", "--rebase", "-q", "origin", "main")
    r = git("push", check=False)
    print(r.stdout, r.stderr)
    if r.returncode:
        sys.exit(r.returncode)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "plan":
        plan()
    elif cmd == "commit":
        commit()
    elif cmd == "fail":
        print("::error::" + " ".join(sys.argv[2:]))
        sys.exit(1)
    else:
        sys.exit(__doc__)
