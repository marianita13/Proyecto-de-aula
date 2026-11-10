import math
import unittest

from fastapi.testclient import TestClient

from api.main import WORK_ITERATIONS, app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_work_returns_timing_and_checksum(self) -> None:
        response = self.client.get("/work")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["work_iterations"], WORK_ITERATIONS)
        self.assertGreaterEqual(result["server_time_ms"], 0)
        self.assertTrue(math.isfinite(result["server_time_ms"]))
        self.assertIsInstance(result["checksum"], int)


if __name__ == "__main__":
    unittest.main()
