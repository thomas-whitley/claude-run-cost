from test_measure_run_cost import Home, turn, write_jsonl
import json
import os


class JsonTest(Home):
    def test_json_session_run_cost(self):
        write_jsonl(os.path.join(self.proj, "abcd1234.jsonl"), [turn(output=1_000_000)])
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0);
        data = json.loads(out)
        self.assertEqual(data["run_cost"], 1_000_000)

    def test_json_subagent_row_and_depth(self):
        write_jsonl(os.path.join(self.proj, "abcd1234.jsonl"), [turn(output=1000)])
        sub_p = os.path.join(self.proj, "abcd1234", "subagents", "agent-x1.jsonl")
        write_jsonl(sub_p, [turn(output=2000)])
        code, out, _ = self.run_main("--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(len(data["rows"]), 2)
        self.assertEqual(data["rows"][1]["depth"], 1)
