import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


class CleanImportTests(unittest.TestCase):
    def test_all_deployment_modules_import_in_fresh_process(self):
        command = (
            "import validation; import data_quality; "
            "import market_data.service; import offer_scoring; import app"
        )
        result = subprocess.run(
            [sys.executable, "-c", command],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
