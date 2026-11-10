import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from api.analysis import (
    AnalysisError,
    QuadraticModel,
    estimate_capacity,
    fit_quadratic_model,
    load_k6_csv,
    write_measurements_csv,
)


def write_k6_csv(path: Path, levels: dict[int, tuple[float, ...]]) -> None:
    rows: list[dict[str, object]] = []
    for vus, durations_ms in levels.items():
        scenario = f"level_{vus}"
        for index, duration in enumerate(durations_ms):
            rows.extend(
                [
                    {"metric_name": "http_reqs", "metric_value": 1, "scenario": scenario},
                    {
                        "metric_name": "http_req_duration",
                        "metric_value": duration,
                        "scenario": scenario,
                    },
                    {
                        "metric_name": "http_req_failed",
                        "metric_value": int(index == 0 and vus == 2),
                        "scenario": scenario,
                    },
                ]
            )
    pd.DataFrame(rows).to_csv(path, index=False)


class K6AnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp_dir.name) / "carga.csv"
        write_k6_csv(
            self.csv_path,
            {
                1: (400.0, 400.0, 400.0, 400.0),
                2: (900.0, 900.0, 900.0, 900.0),
                4: (1_800.0, 1_800.0, 1_800.0, 1_800.0),
            },
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_loads_k6_rows_and_computes_required_statistics(self) -> None:
        data = load_k6_csv(self.csv_path)
        values = data.measurements[
            ["p95_s", "failure_rate_pct", "min_s", "max_s"]
        ].to_numpy(dtype=float)

        self.assertEqual(list(data.measurements["vus"]), [1, 2, 4])
        self.assertEqual(list(data.measurements["requests"]), [4, 4, 4])
        self.assertAlmostEqual(float(values[1, 0]), 0.9)
        self.assertAlmostEqual(float(values[1, 1]), 25.0)
        self.assertLessEqual(float(values[0, 2]), float(values[0, 3]))

    def test_skips_incomplete_scenario(self) -> None:
        raw = pd.read_csv(self.csv_path)
        raw = pd.concat(
            [
                raw,
                pd.DataFrame(
                    [
                        {
                            "metric_name": "http_reqs",
                            "metric_value": 1,
                            "scenario": "level_8",
                        },
                        {
                            "metric_name": "http_req_duration",
                            "metric_value": 2_500,
                            "scenario": "level_8",
                        },
                    ]
                ),
            ],
            ignore_index=True,
        )
        raw.to_csv(self.csv_path, index=False)

        data = load_k6_csv(self.csv_path)

        self.assertNotIn(8, list(data.measurements["vus"]))
        self.assertTrue(any("level_8" in reason for reason in data.invalid_scenarios))

    def test_fits_quadratic_and_calculates_r_squared(self) -> None:
        data = load_k6_csv(self.csv_path)
        model = fit_quadratic_model(data.measurements)

        self.assertAlmostEqual(model.r_squared, 1.0, places=10)
        self.assertAlmostEqual(model.predict(1.0), 0.4, places=10)
        self.assertAlmostEqual(model.predict(2.0), 0.9, places=10)

    def test_rejects_insufficient_distinct_levels(self) -> None:
        data = load_k6_csv(self.csv_path)
        with self.assertRaisesRegex(AnalysisError, "al menos tres niveles"):
            fit_quadratic_model(data.measurements.iloc[:2])

    def test_warns_when_fit_is_poor_and_excludes_invalid_rows(self) -> None:
        measurements = pd.DataFrame(
            {
                "vus": [1, 2, 3, 4, 5, 6, 7],
                "p95_s": [0.1, 10.0, 0.1, 10.0, 0.1, 10.0, 0.0],
            }
        )

        model = fit_quadratic_model(measurements)

        self.assertTrue(any("poco representativo" in warning for warning in model.warnings))
        self.assertTrue(any("excluyeron 1 filas" in warning for warning in model.warnings))

    def test_estimates_only_when_measurements_reach_the_threshold(self) -> None:
        data = load_k6_csv(self.csv_path)
        model = fit_quadratic_model(data.measurements)

        with self.assertRaisesRegex(AnalysisError, "no alcanzan el límite"):
            estimate_capacity(model, data.measurements, max_response_time_s=2.0)

        estimate = estimate_capacity(model, data.measurements, max_response_time_s=1.0)
        self.assertGreaterEqual(estimate.root, model.min_users)
        self.assertLessEqual(estimate.root, model.max_users)
        self.assertLessEqual(model.predict(float(estimate.safe_users)), 1.0)
        self.assertEqual(estimate.safe_users, int(estimate.root))

    def test_rejects_root_outside_experimental_range(self) -> None:
        data = load_k6_csv(self.csv_path)
        model = QuadraticModel(
            a=0.0,
            b=1.0,
            c=-2.0,
            r_squared=1.0,
            min_users=1.0,
            max_users=4.0,
            valid_levels=3,
            warnings=(),
        )
        secant_result = {
            "root": 8.0,
            "iterations": 2,
            "approximate_error_pct": 0.01,
            "history": [],
        }

        with patch("api.analysis.secant_method", return_value=secant_result):
            with self.assertRaisesRegex(AnalysisError, "fuera del rango experimental"):
                estimate_capacity(model, data.measurements, max_response_time_s=1.0)

    def test_writes_normalized_summary_csv(self) -> None:
        data = load_k6_csv(self.csv_path)
        output = Path(self.temp_dir.name) / "summary" / "mediciones.csv"

        write_measurements_csv(data.measurements, output)

        summary = pd.read_csv(output)
        self.assertEqual(
            list(summary.columns),
            [
                "scenario",
                "vus",
                "requests",
                "average_s",
                "min_s",
                "max_s",
                "p95_s",
                "failure_rate_pct",
            ],
        )
        self.assertEqual(len(summary), 3)


if __name__ == "__main__":
    unittest.main()
