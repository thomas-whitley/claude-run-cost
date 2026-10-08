from test_measure_run_cost import Home, turn, write_jsonl
import os


class RatesTest(Home):
    def test_rates_output(self):
        write_jsonl(os.path.join(self.proj, "abcd1234.jsonl"), [turn(output=1_000_000)])
        code, out, _ = self.run_main("--rates", "0,0,0,15")
        self.assertEqual(code, 0)
        self.assertIn("EST COST: $15.00", out)

    def test_no_rates_no_est_cost(self):
        write_jsonl(os.path.join(self.proj, "abcd1234.jsonl"), [turn(output=1_000_000)])
        code, out, _ = self.run_main()
        self.assertEqual(code, 0)
        for line in out.splitlines():
            self.assertNotIn("EST COST", line)
