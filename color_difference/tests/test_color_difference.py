import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from color_difference_inspector import (srgb_to_lab, delta_e76, linear_fit, parse_fitting_text,
                                       read_fitting_txt, write_fitting_txt, image_point)


class ColorDifferenceTests(unittest.TestCase):
    def test_black_white_reference(self):
        for rgb, expected in [((0, 0, 0), (0, 0, 0)), ((255, 255, 255), (100, 0, 0))]:
            for actual, ref in zip(srgb_to_lab(rgb), expected):
                self.assertAlmostEqual(actual, ref, places=10)
        self.assertAlmostEqual(delta_e76((0, 0, 0), (255, 255, 255)), 100)

    def test_primary_color_lab_reference(self):
        for rgb, expected in [((255, 0, 0), (53.24, 80.09, 67.20)),
                              ((0, 255, 0), (87.74, -86.18, 83.19)),
                              ((0, 0, 255), (32.30, 79.19, -107.86)),
                              ((128, 128, 128), (53.585, 0, 0))]:
            for actual, ref in zip(srgb_to_lab(rgb), expected):
                self.assertAlmostEqual(actual, ref, delta=.02)

    def test_identity_symmetry_and_large_difference(self):
        self.assertEqual(delta_e76((12, 35, 76), (12, 35, 76)), 0)
        forward = delta_e76((255, 0, 0), (0, 255, 0))
        self.assertAlmostEqual(forward, 170.57, delta=.05)
        self.assertEqual(forward, delta_e76((0, 255, 0), (255, 0, 0)))
        self.assertGreater(forward, 100)

    def test_dark_transfer_and_validation(self):
        # This dark neutral lies within both linear branches: L*=kappa*Y.
        expected_l = (24389 / 27) * ((1 / 255) / 12.92)
        self.assertAlmostEqual(srgb_to_lab((1, 1, 1))[0], expected_l)
        for rgb in ((-1, 0, 0), (256, 0, 0), (math.nan, 0, 0), (1, 2)):
            with self.assertRaises(ValueError):
                srgb_to_lab(rgb)

    def test_known_and_noisy_regression(self):
        result = linear_fit([(0, 3), (10, 23), (20, 43)])
        self.assertEqual(result["slope"], 2)
        self.assertEqual(result["intercept"], 3)
        self.assertEqual(result["r_squared"], 1)
        noisy = linear_fit([(1, 2), (2, 3), (3, 5)])
        self.assertAlmostEqual(noisy["slope"], 1.5)
        self.assertAlmostEqual(noisy["r_squared"], 27 / 28)
        self.assertIsNone(linear_fit([(0, 5), (10, 5)])["r_squared"])

    def test_invalid_regression(self):
        for rows in ([], [(1, 2)], [(1, 2), (1, 3)], [(1, ""), (2, 3)],
                     [(-1, 2), (2, 3)], [(1, math.inf), (2, 3)], [(1e308, 2), (0, 3)]):
            with self.assertRaises(ValueError):
                linear_fit(rows)

    def test_txt_round_trip(self):
        rows = [(str(delta_e76((255, 0, 0), (0, 255, 0))), ""), ("0", "5")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "色差.txt"
            write_fitting_txt(path, rows)
            self.assertEqual(read_fitting_txt(path), rows)
            self.assertTrue(path.read_text(encoding="utf-8-sig").startswith("色差 ΔE76\t厚度\n"))
        self.assertEqual(parse_fitting_text("DeltaE76,Thickness\n12.5,20\n25.1,"), [("12.5", "20"), ("25.1", "")])
        self.assertEqual(parse_fitting_text("色差 厚度\n0 0"), [("0", "0")])

    def test_old_format_and_bad_rows_rejected(self):
        for text in ("R G B 厚度\n1 2 3 4", "1 2 3 4", "-1 2", "1 -2", "nan 2", "1 inf", "\t2"):
            with self.assertRaisesRegex(ValueError, "第 1 行"):
                parse_fitting_text(text)

    def test_failed_export_preserves_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.txt"
            path.write_text("existing", encoding="utf-8")
            with patch("color_difference_inspector.os.replace", side_effect=OSError("test")):
                with self.assertRaises(OSError):
                    write_fitting_txt(path, [(1, 2)])
            self.assertEqual(path.read_text(), "existing")
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_coordinate_mapping(self):
        self.assertEqual(image_point(120, 60, (20, 10), (200, 100), (400, 200)), (200, 100))
        self.assertIsNone(image_point(19, 10, (20, 10), (200, 100), (400, 200)))


if __name__ == "__main__":
    unittest.main()
