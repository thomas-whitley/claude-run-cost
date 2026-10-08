from test_measure_run_cost import Home, turn, write_jsonl
import os


class InputTokens(Home):
    def test_input_tokens_count_toward_run_cost(self):
        write_jsonl(os.path.join(self.proj, "abcd1234.jsonl"), [turn(inp=500000, output=500000)])
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("RUN COST: 1.0M", out)
