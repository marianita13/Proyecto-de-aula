import unittest

from api.main import estimate_users_for_limit, secant_function, secant_method


class SecantMethodTests(unittest.TestCase):
    def test_secant_method_solves_the_instructive_example(self) -> None:
        def f(x: float) -> float:
            return 0.00002 * x * x + 0.003 * x - 1.8

        result = secant_method(f, 200.0, 250.0, tol=1e-8, max_iter=20)

        self.assertAlmostEqual(float(result["root"]), 234.23292192014313, places=6)
        self.assertGreaterEqual(int(result["iterations"]), 3)

    def test_estimate_users_for_limit_returns_a_safe_capacity(self) -> None:
        estimate = estimate_users_for_limit(max_response_time=2.0, x0=200.0, x1=250.0)

        self.assertAlmostEqual(float(estimate["root"]), 234.2329219201431, places=6)
        self.assertEqual(int(estimate["max_users_under_limit"]), 234)

    def test_secant_function_matches_the_documented_model(self) -> None:
        self.assertAlmostEqual(secant_function(0.0), -1.8, places=6)
        self.assertAlmostEqual(secant_function(234), 0.0, delta=0.1)


if __name__ == "__main__":
    unittest.main()
