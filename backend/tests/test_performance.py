"""Tests for the performance score API.

MySQL/ClickHouse calls are mocked; no real database is touched.
Run: python -m unittest discover -s tests -v
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core import performance_score
from app.main import app

MYSQL_ROWS = [
    {"business_entity": "Food", "main_customer": 2},
    {"business_entity": "Food", "main_customer": 11653225},
]

CH_ROWS = [
    {"customer_id": 2, "created_date": "2026-09-07", "city": "Tehran", "orders_cnt": 100, "InSlot": 0.994},
    {"customer_id": 11653225, "created_date": "2026-09-07", "city": "Tehran", "orders_cnt": 50, "InSlot": 0.94},
]


class PerformanceAPITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _mock_sources(self, mysql_rows=MYSQL_ROWS, ch_rows=None):
        if ch_rows is None:
            ch_rows = [dict(row) for row in CH_ROWS]
        mysql_patcher = patch.object(performance_score, "execute_mysql_query", return_value=mysql_rows)
        ch_patcher = patch.object(performance_score, "execute_clickhouse_query", return_value=ch_rows)
        mysql_mock = mysql_patcher.start()
        ch_mock = ch_patcher.start()
        self.addCleanup(mysql_patcher.stop)
        self.addCleanup(ch_patcher.stop)
        return mysql_mock, ch_mock

    def test_score_endpoint_returns_city_and_business_entity(self):
        self._mock_sources()
        response = self.client.get("/api/performance/score/Tehran/Food")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["city"], "Tehran")
        self.assertEqual(body["business_entity"], "Food")
        self.assertIn("score", body)

    def test_score_endpoint_requires_both_path_parameters(self):
        self.assertEqual(self.client.get("/api/performance/score/Tehran").status_code, 404)
        self.assertEqual(self.client.get("/api/performance/score").status_code, 404)

    def test_score_endpoint_rejects_blank_values(self):
        response = self.client.get("/api/performance/score/Tehran/%20%20%20")
        self.assertEqual(response.status_code, 400)
        response = self.client.get("/api/performance/score/%20%20/Food")
        self.assertEqual(response.status_code, 400)

    def test_unknown_business_entity_falls_back_to_score_1(self):
        self._mock_sources()
        response = self.client.get("/api/performance/score/Tehran/Unknown")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 1)

    def test_missing_data_falls_back_to_score_1(self):
        for mysql_rows, ch_rows in [([], CH_ROWS), (MYSQL_ROWS, []), (MYSQL_ROWS, None), (None, CH_ROWS)]:
            with self.subTest(mysql_rows=mysql_rows, ch_rows=ch_rows):
                with patch.object(
                    performance_score, "execute_mysql_query", return_value=mysql_rows
                ), patch.object(
                    performance_score, "execute_clickhouse_query", return_value=ch_rows
                ):
                    response = self.client.get("/api/performance/score/Tehran/Food")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["score"], 1)

    def test_clickhouse_query_receives_rendered_sql(self):
        _, ch = self._mock_sources()
        response = self.client.get("/api/performance/score/Tehran/Food")
        self.assertEqual(response.status_code, 200, response.text)
        query = ch.call_args.kwargs["sql"]
        self.assertIn("2, 11653225", query)
        self.assertIn("Tehran", query)


if __name__ == "__main__":
    unittest.main()
