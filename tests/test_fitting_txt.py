from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rgb_inspector import parse_fitting_text, read_fitting_txt, write_fitting_txt


class FittingTextTests(unittest.TestCase):
    def test_round_trip_precision_and_blank_thickness(self):
        rows = [("1.6666666666666667", "20", "255", ""), ("0", "12.5", "3", "10.25")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "拟合数据.txt"
            write_fitting_txt(path, rows)
            self.assertEqual(read_fitting_txt(path), rows)
            self.assertTrue(path.read_text(encoding="utf-8-sig").startswith("R\tG\tB\t厚度\n"))

    def test_supported_separators_and_optional_header(self):
        for text in ("R G B 厚度\n1 2 3 4", "r,g,b,thickness\n1,2,3,4",
                     "1\t2\t3\t4", "\ufeff\nR\tG\tB\t厚度\n\n1\t2\t3\t4\n"):
            self.assertEqual(parse_fitting_text(text), [("1", "2", "3", "4")])
        self.assertEqual(parse_fitting_text("1,2,3,"), [("1", "2", "3", "")])

    def test_invalid_rows_identify_line(self):
        for row in ("1 2 3", "1 2 3 4 5", "256 2 3 4", "1 -2 3 4", "1 2 nan 4",
                    "1 2 3 inf", "1 2 3 -4", "a 2 3 4", "\t2\t3\t4"):
            with self.assertRaisesRegex(ValueError, "第 3 行"):
                parse_fitting_text("R G B 厚度\n1 2 3 4\n" + row)

    def test_empty_table_and_bad_header(self):
        self.assertEqual(parse_fitting_text("R\tG\tB\t厚度\n"), [])
        with self.assertRaises(ValueError):
            parse_fitting_text("  \n")
        with self.assertRaises(ValueError):
            parse_fitting_text("B G R 厚度\n1 2 3 4")

    def test_failed_export_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "existing.txt"
            path.write_text("original", encoding="utf-8")
            with patch("rgb_inspector.os.replace", side_effect=OSError("test failure")):
                with self.assertRaises(OSError):
                    write_fitting_txt(path, [("1", "2", "3", "4")])
            self.assertEqual(path.read_text(encoding="utf-8"), "original")
            self.assertEqual(list(Path(folder).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
