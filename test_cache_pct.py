from test_measure_run_cost import Home, turn, write_jsonl
import os


class CachePctTest(Home):
    def test_cache_pct_row_value(self):
        write_jsonl(os.path.join(self.proj, "2ca32e43aaaa.jsonl"), [turn(output=100_000, read=900_000)])
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("90%", out)

    def test_header_contains_cache_pct(self):
        write_jsonl(os.path.join(self.proj, "2ca32e43aaaa.jsonl"), [turn(output=100_000, read=900_000)])
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("cache%", out)
