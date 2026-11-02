from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from optical_contrast_inspector import (optical_contrast, region_box, region_means, linear_fit,
                                       parse_fitting_text, read_fitting_txt, write_fitting_txt, image_point)


class ContrastTests(unittest.TestCase):
    def test_signed_contrast(self):
        self.assertEqual(optical_contrast((100, 100, 100), (110, 120, 90)), (-.1, -.2, .1))
        self.assertEqual(optical_contrast((10, 10, 10), (0, 30, 10)), (1, -2, 0))

    def test_zero_background(self):
        self.assertEqual(optical_contrast((0, 100, 0), (10, 120, 0)), (None, -.2, None))
        self.assertEqual(optical_contrast((0, 0, 0), (10, 20, 30)), (None, None, None))

    def test_regions_average_before_division(self):
        image = Image.new("RGB", (2, 2))
        image.putdata([(50, 50, 50), (150, 150, 150), (100, 120, 80), (140, 120, 80)])
        background = region_means(image, (0, 0, 2, 1))
        signal = region_means(image, (0, 1, 2, 2))
        self.assertEqual(background, (100, 100, 100))
        self.assertEqual(signal, (120, 120, 80))
        self.assertEqual(optical_contrast(background, signal), (-.2, -.2, .2))
        self.assertEqual(region_box((1, 1), (0, 0)), (0, 0, 2, 2))
        self.assertEqual(region_means(image, (0, 0, 1, 1)), (50, 50, 50))
        with self.assertRaises(ValueError):
            region_means(image, (0, 0, 3, 3))

    def test_default_green_and_channel_switching(self):
        rows = [(0, 0, 0, 0), (-.1, -.2, .1, 10), (-.2, -.4, .2, 20)]
        for channel, slope in (("C_G", -50), ("C_B", 100), ("C_R", -100)):
            result = linear_fit(rows, channel)
            self.assertAlmostEqual(result["slope"], slope)
            self.assertAlmostEqual(result["intercept"], 0)
            self.assertAlmostEqual(result["r_squared"], 1)
            self.assertAlmostEqual(result["rmse"], 0)
        self.assertEqual(linear_fit(rows)["channel"], "C_G")

    def test_partial_channels_and_constant_thickness(self):
        rows = [("", -.1, "", 5), ("", -.2, "", 5)]
        self.assertIsNone(linear_fit(rows)["r_squared"])
        self.assertAlmostEqual(linear_fit(rows)["slope"], 0)
        with self.assertRaises(ValueError):
            linear_fit(rows, "C_R")

    def test_invalid_regression(self):
        for rows in ([], [(0, 0, 0, 1)], [(0, 0, 0, 1), (0, 0, 0, 2)],
                     [(0, -.1, 0, ""), (0, -.2, 0, 10)], [(0, -.1, 0, -1), (0, -.2, 0, 10)]):
            with self.assertRaises(ValueError):
                linear_fit(rows)

    def test_txt_round_trip_signed_and_empty(self):
        rows = [("-0.1234567890123456", "-0.2", "0.1", "10"), ("", "-0.3", "", "")]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "对比度.txt"
            write_fitting_txt(path, rows)
            self.assertEqual(read_fitting_txt(path), rows)
        self.assertEqual(parse_fitting_text("C_R,C_G,C_B,thickness_nm\n,-0.2,,10"), [("", "-0.2", "", "10")])

    def test_old_tables_and_bad_values_rejected(self):
        for text in ("R G B 厚度\n1 2 3 4", "色差 厚度\n1 2", "0 0 0 0", "C_R C_G C_B 厚度\n0 2 0 1",
                     "C_R C_G C_B 厚度\n0 nan 0 1", "C_R,C_G,C_B,厚度\n,,,5"):
            with self.assertRaises(ValueError):
                parse_fitting_text(text)

    def test_export_failure_preserves_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "data.txt"
            path.write_text("existing", encoding="utf-8")
            with patch("optical_contrast_inspector.os.replace", side_effect=OSError("test")):
                with self.assertRaises(OSError):
                    write_fitting_txt(path, [(0, -.2, 0, 10)])
            self.assertEqual(path.read_text(), "existing")
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_scaled_coordinates_and_clamping(self):
        self.assertEqual(image_point(120, 60, (20, 10), (200, 100), (400, 200)), (200, 100))
        self.assertEqual(image_point(900, 900, (20, 10), (200, 100), (400, 200), True), (399, 199))
        self.assertIsNone(image_point(19, 10, (20, 10), (200, 100), (400, 200)))


if __name__ == "__main__":
    unittest.main()
