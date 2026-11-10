import math
import unittest

from api.secant import secant_method


class SecantMethodTests(unittest.TestCase):
    def test_secant_converges_to_square_root_of_two(self) -> None:
        result = secant_method(lambda value: value * value - 2, 1.0, 2.0)

        self.assertAlmostEqual(result["root"], math.sqrt(2), delta=1e-5)
        self.assertGreater(result["iterations"], 0)
        self.assertLessEqual(result["approximate_error_pct"], 0.05)
        self.assertEqual(len(result["history"]), result["iterations"])
        self.assertLessEqual(result["history"][-1]["approximate_error_pct"], 0.05)

    def test_secant_rejects_zero_denominator(self) -> None:
        with self.assertRaisesRegex(ValueError, "denominador es cero"):
            secant_method(lambda value: value * 0.0 + 1.0, 0.0, 1.0)

    def test_secant_rejects_equal_or_non_finite_initial_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "deben ser distintas"):
            secant_method(lambda value: value, 1.0, 1.0)
        with self.assertRaisesRegex(ValueError, "deben ser finitas"):
            secant_method(lambda value: value, math.inf, 1.0)
        with self.assertRaisesRegex(ValueError, "valor no finito"):
            secant_method(lambda _value: math.nan, 0.0, 1.0)

    def test_secant_reports_non_convergence(self) -> None:
        with self.assertRaisesRegex(ValueError, "No se alcanzó el error aproximado"):
            secant_method(
                lambda value: value * value + value + 1,
                -2.0,
                -1.0,
                tolerance_percent=1e-12,
                max_iterations=1,
            )


if __name__ == "__main__":
    unittest.main()
