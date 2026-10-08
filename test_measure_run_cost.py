import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import measure_run_cost as mrc


def turn(output=0, create=0, read=0, inp=0, tools=(), ts="2026-10-01T00:00:00Z"):
    """One assistant line as Claude Code writes it."""
    content = [{"type": "tool_use", "name": t} for t in tools]
    return {
        "timestamp": ts,
        "message": {
            "usage": {
                "input_tokens": inp,
                "output_tokens": output,
                "cache_creation_input_tokens": create,
                "cache_read_input_tokens": read,
            },
            "content": content,
        },
    }


def write_jsonl(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line if isinstance(line, str) else json.dumps(line))
            f.write("\n")


class Home(unittest.TestCase):
    """A throwaway home directory holding ~/.claude/projects/<project>/."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home)
        env = mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home})
        env.start()
        self.addCleanup(env.stop)
        self.repo = os.path.join(self.home, "repo")
        os.makedirs(self.repo)
        self.proj = mrc.project_dir(self.repo)

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        argv = ["measure_run_cost.py", "--project", self.repo] + list(args)
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mrc.main()
        return code, out.getvalue(), err.getvalue()


class ProjectDir(Home):
    def test_lives_under_claude_projects_in_home(self):
        self.assertEqual(os.path.dirname(self.proj), os.path.join(self.home, ".claude", "projects"))

    def test_separators_and_colons_become_dashes(self):
        name = os.path.basename(self.proj)
        for ch in ":\\/":
            self.assertNotIn(ch, name)
        self.assertTrue(name.endswith("-repo"))


class Fmt(unittest.TestCase):
    def test_millions(self):
        self.assertEqual(mrc.fmt(12_100_000), "12.1M")

    def test_thousands(self):
        self.assertEqual(mrc.fmt(118_000), "118K")


class Totals(Home):
    def test_sums_usage_and_counts_tools(self):
        p = os.path.join(self.proj, "s.jsonl")
        write_jsonl(p, [
            turn(output=10, create=100, read=1000, ts="2026-10-01T00:00:00Z", tools=["WebFetch", "Agent"]),
            turn(output=5, create=50, read=2000, ts="2026-10-01T00:05:00Z", tools=["WebFetch"]),
        ])
        t = mrc.totals(p)
        self.assertEqual((t["out"], t["create"], t["read"]), (15, 150, 3000))
        self.assertEqual(t["msgs"], 2)
        self.assertEqual(t["tools"]["WebFetch"], 2)
        self.assertEqual(t["tools"]["Agent"], 1)
        self.assertEqual(t["first"], "2026-10-01T00:00:00Z")
        self.assertEqual(t["last"], "2026-10-01T00:05:00Z")

    def test_maxctx_is_the_largest_single_turn_input(self):
        p = os.path.join(self.proj, "s.jsonl")
        write_jsonl(p, [turn(inp=5, create=10, read=100), turn(inp=1, create=0, read=500), turn(read=50)])
        self.assertEqual(mrc.totals(p)["maxctx"], 501)

    def test_skips_lines_that_are_not_json(self):
        p = os.path.join(self.proj, "s.jsonl")
        write_jsonl(p, ["not json", turn(output=7)])
        t = mrc.totals(p)
        self.assertEqual(t["out"], 7)
        self.assertEqual(t["msgs"], 1)


class Main(Home):
    def session(self, sid, lines):
        write_jsonl(os.path.join(self.proj, sid + ".jsonl"), lines)

    def agent(self, sid, aid, lines, meta=None):
        p = os.path.join(self.proj, sid, "subagents", "agent-%s.jsonl" % aid)
        write_jsonl(p, lines)
        if meta is not None:
            with open(p[:-6] + ".meta.json", "w", encoding="utf-8") as f:
                f.write(meta if isinstance(meta, str) else json.dumps(meta))

    def test_no_transcripts_lists_projects_and_exits_1(self):
        os.makedirs(os.path.join(self.home, ".claude", "projects", "C--other"))
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("no transcripts", err)
        self.assertIn("C--other", err)

    def test_prints_session_and_run_cost(self):
        self.session("2ca32e43aaaa", [turn(output=100_000, read=900_000)])
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("main  2ca32e43", out)
        self.assertIn("RUN COST: 1.0M", out)

    def test_subagents_nest_under_their_session_by_description(self):
        self.session("abcd1234", [turn(output=1000)])
        self.agent("abcd1234", "x1", [turn(output=2000)], meta={"description": "Scan boards", "spawnDepth": 2})
        _, out, _ = self.run_main()
        self.assertIn("    agent Scan boards", out)

    def test_subagent_with_bad_meta_falls_back_to_its_id(self):
        self.session("abcd1234", [turn(output=1000)])
        self.agent("abcd1234", "x9", [turn(output=2000)], meta="{broken")
        _, out, _ = self.run_main()
        self.assertIn("  agent x9", out)

    def test_flags_turns_ctx_and_fanout(self):
        lines = [turn(output=1) for _ in range(mrc.TURNS_FLAG)]
        lines.append(turn(read=mrc.CTX_FLAG + 1, tools=["Agent", "Agent"]))
        self.session("abcd1234", lines)
        _, out, _ = self.run_main()
        self.assertIn("!turns", out)
        self.assertIn("!ctx", out)
        self.assertIn("!fanout(2)", out)

    def test_session_prefix_selects_one_session(self):
        self.session("aaaa1111", [turn(output=1000)])
        self.session("bbbb2222", [turn(output=1000)])
        _, out, _ = self.run_main("--session", "bbbb")
        self.assertIn("bbbb2222", out)
        self.assertNotIn("aaaa1111", out)

    def test_budget_over_exits_2(self):
        self.session("abcd1234", [turn(output=2_000_000)])
        code, out, _ = self.run_main("--budget", "1000000")
        self.assertEqual(code, 2)
        self.assertIn("OVER by", out)

    def test_budget_within_exits_0(self):
        self.session("abcd1234", [turn(output=1000)])
        code, out, _ = self.run_main("--budget", "1000000")
        self.assertEqual(code, 0)
        self.assertIn("within budget", out)

    def test_old_sessions_are_left_out(self):
        self.session("abcd1234", [turn(output=1000)])
        p = os.path.join(self.proj, "abcd1234.jsonl")
        old = os.path.getmtime(p) - 3 * 86400
        os.utime(p, (old, old))
        code, out, _ = self.run_main("--days", "1")
        self.assertEqual(code, 1)
        self.assertIn("no sessions", out)


if __name__ == "__main__":
    unittest.main()
