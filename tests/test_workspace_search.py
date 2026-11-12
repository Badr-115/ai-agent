import tempfile
import unittest
from pathlib import Path

from tools.workspace import Workspace


class WorkspaceSearchTests(unittest.TestCase):
    def test_search_reports_when_not_all_files_were_searched(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for number in range(81):
                (root / f"file{number:03}.txt").write_text(
                    "needle" if number == 80 else "ordinary text", encoding="utf-8"
                )
            result = Workspace(root).search_text("needle")
            self.assertIn("[search limited]", result)

    def test_search_of_exactly_80_files_is_not_reported_as_limited(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            for number in range(80):
                (root / f"file{number:03}.txt").write_text("ordinary text", encoding="utf-8")
            result = Workspace(root).search_text("needle")
            self.assertEqual(result, "[no matches]")


if __name__ == "__main__":
    unittest.main()
