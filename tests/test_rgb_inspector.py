import math
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from rgb_inspector import image_point, load_rgb, region_box, region_statistics


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (2, 2))
        self.image.putdata([(0, 10, 20), (100, 20, 40), (200, 30, 60), (100, 40, 80)])

    def test_population_statistics(self):
        means, stds = region_statistics(self.image, (0, 0, 2, 2))
        self.assertEqual(means, (100, 25, 50))
        for actual, expected in zip(stds, (math.sqrt(5000), math.sqrt(125), math.sqrt(500))):
            self.assertAlmostEqual(actual, expected)

    def test_single_pixel(self):
        self.assertEqual(region_statistics(self.image, (1, 1, 2, 2)), ((100, 40, 80), (0, 0, 0)))

    def test_reverse_and_line_regions(self):
        self.assertEqual(region_box((1, 1), (0, 0)), (0, 0, 2, 2))
        self.assertEqual(region_box((0, 1), (1, 1)), (0, 1, 2, 2))
        self.assertEqual(region_statistics(self.image, (0, 1, 2, 2))[0], (150, 35, 70))

    def test_invalid_regions(self):
        for box in ((0, 0, 0, 1), (-1, 0, 1, 1), (0, 0, 3, 2)):
            with self.assertRaises(ValueError):
                region_statistics(self.image, box)

    def test_scaled_coordinates_and_clamping(self):
        args = ((20, 10), (333, 200), (1000, 601))
        self.assertEqual(image_point(352, 209, *args), (996, 597))
        self.assertIsNone(image_point(19, 20, *args))
        self.assertIsNone(image_point(353, 210, *args))
        self.assertEqual(image_point(500, 500, *args, clamp=True), (999, 600))
        self.assertEqual(image_point(-5, -5, *args, clamp=True), (0, 0))

    def test_file_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "测试.png"
            Image.new("RGBA", (2, 1), (12, 34, 56, 0)).save(path)
            loaded = load_rgb(path)
            path.unlink()
            self.assertEqual(loaded.getpixel((0, 0)), (12, 34, 56))
            Image.new("L", (1, 1), 37).save(path)
            self.assertEqual(load_rgb(path).getpixel((0, 0)), (37, 37, 37))

    def test_exif_orientation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "oriented.png"
            source = Image.new("RGB", (2, 3))
            exif = Image.Exif()
            exif[274] = 6
            source.save(path, exif=exif)
            self.assertEqual(load_rgb(path).size, (3, 2))


if __name__ == "__main__":
    unittest.main()
