"""Tests for the allocator / rule / listing lookups.

The upstream services are never called: ``requests.get`` is mocked, so these
run anywhere and only exercise the normalization, filtering and error mapping
in ``app.api.incentive_lookups``.
Run: python -m unittest discover -s tests -v
"""

import unittest
from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

from app.api import incentive_lookups as lookups
from app.main import app

BASE = "/api/incentive-lookups"


def response(payload, status=200):
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = payload
    mock.raise_for_status.side_effect = (
        None if status < 400 else requests.HTTPError(f"{status} error")
    )
    return mock


class LookupAPITests(unittest.TestCase):
    def setUp(self):
        for name, value in {
            "ALLOCATOR_NAMES_URL": "http://allocators.test/allocator/names",
            "RULE_NAMES_URL": "http://rules.test/rules/names",
            "LISTING_QUERIES_URL": "http://listings.test/queries",
        }.items():
            patcher = patch.object(lookups, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.get = patch.object(lookups.requests, "get").start()
        self.addCleanup(patch.stopall)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def read(self, path, **params):
        res = self.client.get(f"{BASE}/{path}", params=params)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    def test_plain_list_of_names_is_normalized_and_filtered(self):
        self.get.return_value = response([
            "foodZooket-kerman-3T-range-base", "foodZooket-kish-1T-base", "  ",
            "foodZooket-kerman-3T-range-base",  # duplicate, case-insensitive
        ])
        data = self.read("allocators")
        self.assertEqual(data["kind"], "allocators")
        self.assertEqual(data["source"], "http://allocators.test/allocator/names")
        self.assertEqual(data["total"], 2)
        self.assertEqual([r["name"] for r in data["rows"]],
                         ["foodZooket-kerman-3T-range-base", "foodZooket-kish-1T-base"])

        self.get.return_value = response(["foodZooket-kerman-3T-range-base", "foodZooket-kish-1T-base"])
        kerman = self.read("allocators", q="KERMAN")
        self.assertEqual(kerman["term"], "KERMAN")
        self.assertEqual([r["name"] for r in kerman["rows"]], ["foodZooket-kerman-3T-range-base"])
        self.assertEqual(kerman["matched"], 1)

    def test_wrapped_and_object_payloads_are_normalized(self):
        for payload, expected in [
            ({"names": ["a", "b"]}, ["a", "b"]),
            ({"data": [{"name": "a"}, {"name": "b"}]}, ["a", "b"]),
            ({"results": [{"id": "rule-1"}, {"id": "rule-2"}]}, ["rule-1", "rule-2"]),
            ({"response": [{"value": "a", "extra": 1}]}, ["a"]),
            ([{"allocator": "a"}, {"label": "b"}, 7], ["a", "b", "7"]),
            ({"tehran": ["listing-a", "listing-b"]}, ["listing-a", "listing-b"]),
        ]:
            with self.subTest(payload=payload):
                self.get.return_value = response(payload)
                self.assertEqual([r["name"] for r in self.read("rules")["rows"]], expected)

    def test_empty_and_unusable_payloads_give_an_empty_list(self):
        for payload in [[], {}, {"names": []}, None, [None, ""]]:
            with self.subTest(payload=payload):
                self.get.return_value = response(payload)
                data = self.read("rules")
                self.assertEqual(data["rows"], [])
                self.assertEqual(data["total"], 0)

    def test_limit_caps_the_returned_names_and_reports_the_truncation(self):
        self.get.return_value = response([f"rule-{i}" for i in range(50)])
        data = self.read("rules", limit=10)
        self.assertEqual(len(data["rows"]), 10)
        self.assertEqual(data["matched"], 50)
        self.assertTrue(data["truncated"])

    def test_listings_are_fetched_per_city(self):
        self.get.return_value = response(["tehran-daily-foodZooket", "tehran-weekly-foodZooket"])
        data = self.read("listings", city="tehran")
        self.assertEqual(self.get.call_args[0][0], "http://listings.test/queries/tehran")
        self.assertEqual(data["kind"], "listings")
        self.assertEqual([r["name"] for r in data["rows"]],
                         ["tehran-daily-foodZooket", "tehran-weekly-foodZooket"])

    def test_listings_require_a_city(self):
        for params in [{}, {"city": ""}, {"city": "   "}]:
            with self.subTest(params=params):
                res = self.client.get(f"{BASE}/listings", params=params)
                self.assertEqual(res.status_code, 400, res.text)
                self.assertIn("city", res.json()["message"])
        self.get.assert_not_called()

    def test_an_unreachable_service_is_reported_as_a_bad_gateway(self):
        for exc in [requests.ConnectionError("no route to host"), requests.Timeout("timed out")]:
            with self.subTest(exc=type(exc).__name__):
                self.get.side_effect = exc
                res = self.client.get(f"{BASE}/allocators")
                self.assertEqual(res.status_code, 502, res.text)
                body = res.json()
                self.assertEqual(body["status"], "error")
                self.assertEqual(body["kind"], "allocators")
                self.assertIn("allocators service", body["message"])

    def test_an_upstream_error_status_is_reported_as_a_bad_gateway(self):
        self.get.return_value = response({"error": "nope"}, status=500)
        res = self.client.get(f"{BASE}/rules")
        self.assertEqual(res.status_code, 502, res.text)
        self.assertIn("rules service", res.json()["message"])

    def test_limit_is_capped_and_the_request_times_out(self):
        self.get.return_value = response([f"rule-{i}" for i in range(lookups.MAX_LIMIT + 20)])
        data = self.read("rules", limit=lookups.MAX_LIMIT + 500)
        self.assertEqual(len(data["rows"]), lookups.MAX_LIMIT)
        self.assertEqual(self.get.call_args.kwargs["timeout"], lookups.REQUEST_TIMEOUT)

    def test_a_non_numeric_limit_is_rejected_by_the_api(self):
        res = self.client.get(f"{BASE}/rules", params={"limit": "abc"})
        self.assertEqual(res.status_code, 422, res.text)
        self.get.assert_not_called()
