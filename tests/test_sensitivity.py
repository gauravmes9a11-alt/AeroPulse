import tempfile
import unittest
from pathlib import Path

from sensitivity import run_fixed_baseline_sensitivity


class SensitivityTests(unittest.TestCase):
    def test_fixed_baseline_sensitivity_produces_nonzero_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            df = run_fixed_baseline_sensitivity(output_dir=Path(tmpdir))
            self.assertFalse(df.empty)
            self.assertGreater(len(df), 1)
            self.assertIn("parameter", df.columns)

            shift_columns = [col for col in df.columns if col.endswith("_shift_pct")]
            self.assertTrue(shift_columns)
            self.assertTrue((df[shift_columns].abs() > 1e-6).any().any())

            first_row = df.iloc[0]
            self.assertGreater(first_row["endurance_h"], 0.0)
            self.assertGreater(first_row["fuel_burned_kg"], 0.0)
            self.assertGreater(first_row["efficiency"], 0.0)


if __name__ == "__main__":
    unittest.main()
