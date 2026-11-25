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


PNP_WINDOW_UTC = (400, 845)  # Pick n Pay's robots.txt Visit-time


def already_done_today() -> bool:
    """A scheduled run is skipped if today's prices are already saved: Checkers/Shoprite refreshed today and
    Pick n Pay either refreshed today or no longer reachable today (its window has closed)."""
    import json
    p = ROOT / "data" / "prices.json"
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    if d.get("generated_at", "")[:10] != now.strftime("%Y-%m-%d"):
        return False
    r = d.get("retailers", {})
    if r.get("checkers", {}).get("status") != "ok" or r.get("shoprite", {}).get("status") != "ok":
        return False
    pnp_window_open = PNP_WINDOW_UTC[0] <= int(now.strftime("%H%M")) <= PNP_WINDOW_UTC[1]
    return r.get("pnp", {}).get("status") == "ok" or not pnp_window_open


def plan() -> None:
    dow = datetime.now(timezone.utc).isoweekday()  # 1=Mon .. 7=Sun
    stores = dow == 1 or not (ROOT / "data" / "stores.json").exists() or os.environ.get("IN_STORES") == "true"
    discover = dow == 7 or os.environ.get("IN_DISCOVER") == "true"
    # The schedule fires several times each morning (GitHub's cron can be hours late, and the PC may
    # wake late); later runs skip once the day's prices are in. Manual runs never skip.
    skip = os.environ.get("GITHUB_EVENT_NAME") == "schedule" and already_done_today()
    if skip:
        stores = discover = False
    out = os.environ.get("GITHUB_OUTPUT")
    lines = (f"stores={'true' if stores else 'false'}\ndiscover={'true' if discover else 'false'}\n"
             f"skip={'true' if skip else 'false'}\n")
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
