#!/usr/bin/env python3
"""Print what a Claude Code session and its subagents actually cost.

Claude Code keeps a JSONL transcript per session under
~/.claude/projects/<project>/<session>.jsonl, and one per subagent under
~/.claude/projects/<project>/<session>/subagents/agent-*.jsonl. Every assistant
turn in them carries a usage block. Nobody adds them up. This does.

    python measure_run_cost.py                        # this project, sessions touched today
    python measure_run_cost.py --days 3
    python measure_run_cost.py --session 2ca32e43      # one session, by id prefix
    python measure_run_cost.py --project ~/src/thing   # another project
    python measure_run_cost.py --budget 15000000       # exit 2 if the total is over

"Cost" is input + cache creation + cache read + output tokens, which is what the
API bills. Rates differ by model and by cache tier, so this prints tokens, not
dollars; multiply by your own rates.

Three shapes account for nearly every expensive run, and each gets a flag:

    !turns    more than 200 messages: an agent with no scope limit
    !ctx      a turn with more than 150K tokens of input: from here on, every
              further turn re-reads all of it, so cost grows with the square of
              the turn count
    !fanout   the agent called the Agent tool, so it spawned agents of its own
"""

import argparse
import collections
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta

TURNS_FLAG = 200
CTX_FLAG = 150_000


def project_dir(path):
    """Claude Code names the transcript folder after the absolute path with ':' and
    separators replaced by '-': C:/Users/me/repo on Windows -> C--Users-me-repo,
    /home/me/repo -> -home-me-repo."""
    enc = re.sub("[:/]", "-", os.path.abspath(path).replace(os.sep, "/"))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", enc)


def totals(path):
    """Sum the usage blocks in one transcript."""
    inp = out = cre = red = mx = n = 0
    tools = collections.Counter()
    first = last = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            n += 1
            ts = d.get("timestamp")
            if ts:
                first = first or ts
                last = ts
            m = d.get("message") or {}
            u = m.get("usage")
            if u:
                inp += u.get("input_tokens", 0)
                out += u.get("output_tokens", 0)
                cre += u.get("cache_creation_input_tokens", 0)
                red += u.get("cache_read_input_tokens", 0)
                mx = max(mx, u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                         + u.get("cache_creation_input_tokens", 0))
            c = m.get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        tools[b.get("name", "?")] += 1
    return dict(input=inp, out=out, create=cre, read=red, maxctx=mx, msgs=n, tools=tools, first=first, last=last)


def fmt(n):
    return "%.1fM" % (n / 1e6) if n >= 1e6 else "%.0fK" % (n / 1e3)


def parse_rates(s):
    try:
        parts = [float(x) for x in s.split(",")]
    except ValueError:
        raise argparse.ArgumentTypeError("rates must be four comma-separated numbers")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("rates must be four comma-separated numbers")
    return parts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="repo path (default: current directory)")
    ap.add_argument("--days", type=int, default=1, help="sessions modified in the last N days (default 1)")
    ap.add_argument("--session", help="session id prefix; overrides --days")
    ap.add_argument("--budget", type=int, default=0, help="tokens; exit 2 if the total is over")
    ap.add_argument("--rates", type=parse_rates, help="four comma-separated numbers: dollars per million tokens for input, cache creation, cache read, output")
    a = ap.parse_args()

    proj = project_dir(a.project)
    if not os.path.isdir(proj):
        root = os.path.dirname(proj)
        print("no transcripts at %s" % proj, file=sys.stderr)
        if os.path.isdir(root):
            print("projects with transcripts:", file=sys.stderr)
            for d in sorted(os.listdir(root)):
                print("  " + d, file=sys.stderr)
        return 1

    cutoff = datetime.now() - timedelta(days=a.days)
    sessions = []
    for p in sorted(glob.glob(os.path.join(proj, "*.jsonl"))):
        if a.session:
            if os.path.basename(p).startswith(a.session):
                sessions.append(p)
        elif datetime.fromtimestamp(os.path.getmtime(p)) >= cutoff:
            sessions.append(p)
    if not sessions:
        print("no sessions in the last %d day(s) under %s" % (a.days, proj))
        return 1

    grand = 0
    sum_inp = 0
    sum_create = 0
    sum_read = 0
    sum_out = 0
    rows = []
    for s in sessions:
        sid = os.path.basename(s)[:-6]
        t = totals(s)
        tot = t["input"] + t["out"] + t["create"] + t["read"]
        grand += tot
        sum_inp += t["input"]
        sum_create += t["create"]
        sum_read += t["read"]
        sum_out += t["out"]
        rows.append(("main  " + sid[:8], t, tot))
        for sub in sorted(glob.glob(os.path.join(proj, sid, "subagents", "agent-*.jsonl"))):
            aid = os.path.basename(sub)[6:-6]
            meta_p = sub[:-6] + ".meta.json"
            desc, depth = "", 1
            if os.path.exists(meta_p):
                try:
                    meta = json.load(open(meta_p, encoding="utf-8"))
                    desc = meta.get("description", "")
                    depth = int(meta.get("spawnDepth", 1))
                except (ValueError, OSError):
                    pass
            st = totals(sub)
            stot = st["input"] + st["out"] + st["create"] + st["read"]
            grand += stot
            sum_inp += st["input"]
            sum_create += st["create"]
            sum_read += st["read"]
            sum_out += st["out"]
            rows.append(("  " * depth + "agent " + (desc or aid)[:34], st, stot))

    print()
    print("%-44s %8s %7s %7s %8s %8s" % ("", "TOTAL", "msgs", "maxctx", "output", "fetches"))
    print("-" * 88)
    for label, t, tot in rows:
        fetches = t["tools"].get("WebFetch", 0) + t["tools"].get("WebSearch", 0)
        flag = ""
        if t["msgs"] > TURNS_FLAG:
            flag += " !turns"
        if t["maxctx"] > CTX_FLAG:
            flag += " !ctx"
        if t["tools"].get("Agent"):
            flag += " !fanout(%d)" % t["tools"]["Agent"]
        print("%-44s %8s %7d %7s %8s %8d%s"
              % (label[:44], fmt(tot), t["msgs"], fmt(t["maxctx"]), fmt(t["out"]), fetches, flag))
    print("-" * 88)
    if a.budget:
        verdict = "OVER by %s" % fmt(grand - a.budget) if grand > a.budget else "within budget"
        print("RUN COST: %s   budget %s   %s" % (fmt(grand), fmt(a.budget), verdict))
    else:
        print("RUN COST: %s" % fmt(grand))
    if a.rates:
        cost = (sum_inp * a.rates[0] + sum_create * a.rates[1] + sum_read * a.rates[2] + sum_out * a.rates[3]) / 1_000_000
        print("EST COST: $%.2f" % cost)
    print()
    print("!turns: an agent with no scope limit. !ctx: a saturated context re-read on every turn.")
    print("!fanout: an agent that spawned its own agents; their cost is listed indented beneath it.")
    return 2 if a.budget and grand > a.budget else 0


if __name__ == "__main__":
    sys.exit(main())
