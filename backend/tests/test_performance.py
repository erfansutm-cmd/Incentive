"""Tests for the performance score API and calculation.

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
    {"business_entity": "Grocery", "main_customer": 999},
]

# Thresholds from metrics_config:
#   2         -> [0.996, 0.994, 0.990, 0.985]
#   11653225  -> [0.98, 0.96, 0.95, 0.93]
CH_ROWS = [
    {"customer_id": 2, "created_date": "2026-09-07", "city": "Tehran", "orders_cnt": 100, "InSlot": 0.994},
    {"customer_id": 2, "created_date": "2026-09-08", "city": "Tehran", "orders_cnt": 100, "InSlot": 0.992},
    {"customer_id": 11653225, "created_date": "2026-09-07", "city": "Tehran", "orders_cnt": 50, "InSlot": 0.94},
]


def ch_rows_generic_columns():
    # Legacy positional aliases in performance_query.sql SELECT order:
    # customer_id, created_date, city, orders_cnt, InSlot.
    return [
        {"col_0": 2, "col_1": "2026-09-07", "col_2": "Tehran", "col_3": 200, "col_4": 0.993},
        {"col_0": 11653225, "col_1": "2026-09-07", "col_2": "Tehran", "col_3": 50, "col_4": 0.94},
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

    def test_score_endpoint_returns_calculated_score(self):
        # customer 2 avg = 0.993 -> score 3; 11653225 avg = 0.94 -> score 4;
        # final = worst = 4.
        self._mock_sources()
        response = self.client.get("/api/performance/score/Tehran/Food")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(), {"city": "Tehran", "business_entity": "Food", "score": 4}
        )

    def test_score_endpoint_supports_generic_column_names(self):
        self._mock_sources(ch_rows=ch_rows_generic_columns())
        response = self.client.get("/api/performance/score/Tehran/Food")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["score"], 4)

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

    def test_customers_without_thresholds_fall_back_to_score_1(self):
        # Grocery -> customer 999 has no SLA_THRESHOLDS_METRIC entry.
        with patch.object(
            performance_score, "execute_mysql_query", return_value=MYSQL_ROWS
        ), patch.object(
            performance_score,
            "execute_clickhouse_query",
            return_value=[{"customer_id": 999, "orders_cnt": 10, "InSlot": 0.5}],
        ):
            response = self.client.get("/api/performance/score/Tehran/Grocery")
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

    def test_source_errors_fall_back_to_score_1(self):
        for failing, healthy_rows in [("execute_mysql_query", CH_ROWS), ("execute_clickhouse_query", MYSQL_ROWS)]:
            healthy = "execute_clickhouse_query" if failing == "execute_mysql_query" else "execute_mysql_query"
            with self.subTest(failing=failing):
                with patch.object(
                    performance_score, failing, side_effect=RuntimeError("db down")
                ), patch.object(performance_score, healthy, return_value=healthy_rows):
                    response = self.client.get("/api/performance/score/Tehran/Food")
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["score"], 1)

    def test_city_with_quote_is_escaped_in_clickhouse_query(self):
        _, ch = self._mock_sources()
        response = self.client.get("/api/performance/score/O'Hare/Food")
        self.assertEqual(response.status_code, 200, response.text)
        query = ch.call_args.kwargs["sql"]
        self.assertIn("O\\'Hare", query)
        self.assertNotIn("O'Hare", query.replace("O\\'Hare", ""))


class PerformanceCalculationTests(unittest.TestCase):
    def test_threshold_boundaries(self):
        thresholds = [0.996, 0.994, 0.990, 0.985]
        cases = [
            (1.0, 1),
            (0.996, 1),
            (0.9959, 2),
            (0.994, 2),
            (0.993, 3),
            (0.990, 3),
            (0.989, 4),
            (0.985, 4),
            (0.984, 5),
            (0.0, 5),
        ]
        for inslot, expected in cases:
            with self.subTest(inslot=inslot):
                self.assertEqual(performance_score._score_from_inslot(inslot, thresholds), expected)

    def test_orders_weighted_average(self):
        with patch.object(performance_score, "execute_mysql_query", return_value=MYSQL_ROWS), patch.object(
            performance_score,
            "execute_clickhouse_query",
            return_value=[
                # Weighted avg = (0.999 * 300 + 0.90 * 100) / 400 = 0.97425 -> score 5.
                {"customer_id": 2, "orders_cnt": 300, "InSlot": 0.999},
                {"customer_id": 2, "orders_cnt": 100, "InSlot": 0.90},
            ],
        ):
            self.assertEqual(performance_score.get_city_performance_score("Tehran", "Food"), 5)

    def test_invalid_rows_are_skipped(self):
        with patch.object(performance_score, "execute_mysql_query", return_value=MYSQL_ROWS), patch.object(
            performance_score,
            "execute_clickhouse_query",
            return_value=[
                {"customer_id": "junk", "orders_cnt": 10, "InSlot": 0.1},
                {"customer_id": 2, "orders_cnt": 10, "InSlot": None},
                {"customer_id": 2, "orders_cnt": 10, "InSlot": 0.997},
            ],
        ):
            # Only the last row is usable: 0.997 -> score 1.
            self.assertEqual(performance_score.get_city_performance_score("Tehran", "Food"), 1)


if __name__ == "__main__":
    unittest.main()
