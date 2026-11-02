import unittest

from rgb_inspector import linear_fit, rgb_to_hsv_values


class LinearFitTests(unittest.TestCase):
    def test_known_line(self):
        result = linear_fit([(255, 0, 0, 3), (255, 255, 0, 123), (0, 255, 0, 243)])
        self.assertEqual(result["points"], [(0, 3), (60, 123), (120, 243)])
        self.assertAlmostEqual(result["slope"], 2)
        self.assertAlmostEqual(result["intercept"], 3)
        self.assertAlmostEqual(result["r_squared"], 1)

    def test_noisy_line(self):
        result = linear_fit([(255, 0, 0, 2), (255, 255, 0, 3), (0, 255, 0, 5)])
        self.assertAlmostEqual(result["slope"], .025)
        self.assertAlmostEqual(result["intercept"], 11 / 6)
        self.assertAlmostEqual(result["r_squared"], 27 / 28)

    def test_two_points_negative_slope(self):
        result = linear_fit([(255, 255, 0, 1), (255, 0, 0, 4)])
        self.assertEqual(result["slope"], -.05)
        self.assertEqual(result["intercept"], 4)
        self.assertEqual(result["r_squared"], 1)

    def test_constant_thickness_has_undefined_r_squared(self):
        result = linear_fit([(255, 0, 0, 5), (0, 255, 0, 5)])
        self.assertEqual(result["slope"], 0)
        self.assertEqual(result["intercept"], 5)
        self.assertIsNone(result["r_squared"])

    def test_invalid_data(self):
        for rows in ([], [(1, 1, 0, 1)], [(1, 1, 1, 1), (2, 1, 0, 2)],
                     [(1, 1, 0, ""), (2, 1, 0, 2)], [(1, 1, 0, 1), (2, 2, 0, 2)],
                     [(1, 1, 0, "nan"), (2, 1, 0, 2)],
                     [(1, 1, 0, 1e308), (2, 1, 0, 0)]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                linear_fit(rows)

    def test_hsv_primary_colors_and_grayscale(self):
        for rgb, hsv in [((255, 0, 0), (0, 100, 100)), ((0, 255, 0), (120, 100, 100)),
                         ((0, 0, 255), (240, 100, 100)), ((0, 0, 0), (0, 0, 0)),
                         ((127.5, 127.5, 127.5), (0, 0, 50))]:
            self.assertEqual(rgb_to_hsv_values(*rgb), hsv)

    def test_s_and_v_percentage_units(self):
        rows = [(255, 0, 0, 100), (127.5, 63.75, 63.75, 50), (63.75, 47.8125, 47.8125, 25)]
        for component in ("S", "V"):
            result = linear_fit(rows, component)
            self.assertAlmostEqual(result["slope"], 1)
            self.assertAlmostEqual(result["intercept"], 0)
            self.assertEqual(result["r_squared"], 1)
        result = linear_fit([(0, 0, 0, 0), (255, 255, 255, 100)], "V")
        self.assertEqual(result["slope"], 1)

    def test_hue_wrap(self):
        rows = [(255, 0, 4.25, 9), (255, 4.25, 0, 11)]
        result = linear_fit(rows, "H", unwrap_hue=True)
        self.assertAlmostEqual(result["points"][0][0], -1)
        self.assertAlmostEqual(result["points"][1][0], 1)
        self.assertAlmostEqual(result["slope"], 1)
        self.assertAlmostEqual(result["intercept"], 10)
        self.assertTrue(result["unwrap_hue"])
        self.assertGreater(linear_fit(rows)["points"][0][0], 350)

    def test_unknown_component(self):
        with self.assertRaises(ValueError):
            linear_fit([(255, 0, 0, 1), (0, 255, 0, 2)], "R/G")


if __name__ == "__main__":
    unittest.main()
