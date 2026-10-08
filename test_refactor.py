import unittest
from test_measure_run_cost import Home


class TestRefactor(Home):
    def test_no_transcripts_stderr_and_exit(self):
        code, _, err = self.run_main("--json")
        self.assertEqual(code, 1)
        self.assertIn("no transcripts", err)


if __name__ == "__main__":
    unittest.main()
