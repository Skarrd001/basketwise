"""Shell-neutral helpers for the workflow, so the same steps run on Windows PowerShell, Mac and Linux.

  python scraper/ci.py plan     -> decides the weekly jobs, writes them to $GITHUB_OUTPUT
  python scraper/ci.py commit   -> commits data/ and pushes it
  python scraper/ci.py fail MSG -> prints a GitHub error annotation and exits 1
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


PNP_WINDOW_UTC = (400, 845)  # Pick n Pay's robots.txt Visit-time


def _today_status() -> tuple[bool, bool]:
    """(Checkers+Shoprite saved today, Pick n Pay refreshed today) from the committed prices.json."""
    import json
    p = ROOT / "data" / "prices.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, False
    if d.get("generated_at", "")[:10] != datetime.now(timezone.utc).strftime("%Y-%m-%d"):
        return False, False
    r = d.get("retailers", {})
    cs = r.get("checkers", {}).get("status") == "ok" and r.get("shoprite", {}).get("status") == "ok"
    return cs, r.get("pnp", {}).get("status") == "ok"


def pnp_window_open() -> bool:
    return PNP_WINDOW_UTC[0] <= int(datetime.now(timezone.utc).strftime("%H%M")) <= PNP_WINDOW_UTC[1]


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
    # The PC's own morning timer starts runs with auto=true; treat them like scheduled runs.
    scheduled = os.environ.get("GITHUB_EVENT_NAME") == "schedule" or os.environ.get("IN_AUTO") == "true"
    skip = scheduled and already_done_today()
    if skip:
        stores = discover = False
    cs_today, pnp_today = _today_status()
    cs_done = scheduled and cs_today                 # manual runs always refresh Checkers/Shoprite
    pnp_needed = pnp_window_open() and not (scheduled and pnp_today)
    b = lambda v: "true" if v else "false"  # noqa: E731
    out = os.environ.get("GITHUB_OUTPUT")
    lines = (f"stores={b(stores)}\ndiscover={b(discover)}\nskip={b(skip)}\n"
             f"cs_done={b(cs_done)}\npnp_needed={b(pnp_needed)}\n")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(lines)
    print(lines.strip())


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and r.returncode:
        # Show git's own message in the log; a bare CalledProcessError hides it.
        print(f"git {' '.join(args)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr}")
        r.check_returncode()
    return r


def commit() -> None:
    git("config", "user.name", "basketwise-bot")
    git("config", "user.email", "basketwise-bot@users.noreply.github.com")
    # A run killed or failed mid-rebase leaves rebase state in .git that actions/checkout doesn't remove, and
    # it breaks every later pull. --quit drops that state but keeps the fresh checkout (--abort would bring
    # back the old run's unpushed commit and conflict again).
    git_dir = Path(git("rev-parse", "--git-dir").stdout.strip())
    if not git_dir.is_absolute():
        git_dir = ROOT / git_dir
    if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
        print("clearing a rebase left over from an earlier run")
        git("rebase", "--quit", check=False)
    git("add", "data")
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        print("no data changes")
        return
    msg = f"data: prices {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"
    git("commit", "-m", msg)
    if git("pull", "--rebase", "-q", "origin", "main", check=False).returncode:
        # Someone else pushed data since this run checked out. Never leave a half-done rebase behind:
        # this run's files are the newest scrape, so they win whole (never a line-by-line JSON mix);
        # files only the other side changed are kept.
        print("data conflict with a newer push: keeping this run's files")
        git("rebase", "--abort", check=False)
        keep = Path(os.environ.get("RUNNER_TEMP", ROOT.parent)) / "bw_data_keep"
        if keep.exists():
            shutil.rmtree(keep)
        shutil.copytree(ROOT / "data", keep)
        git("fetch", "-q", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        shutil.copytree(keep, ROOT / "data", dirs_exist_ok=True)
        shutil.rmtree(keep, ignore_errors=True)
        git("add", "data")
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("no data changes after syncing")
            return
        git("commit", "-m", msg)
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
