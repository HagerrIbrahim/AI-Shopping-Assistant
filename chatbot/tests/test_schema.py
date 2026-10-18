import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chatbot_service import MODEL_NAME, OLLAMA_URL, understand_request
from schemas import Budget, ShoppingRequest


class ShoppingRequestTests(unittest.TestCase):
    def test_valid_english_request(self):
        request = ShoppingRequest(
            category="handbag",
            search_query="black handbag for university",
            filters={"color": "black", "occasion": "university"},
            budget={"max": 1500, "currency": "EGP"},
            language="en",
        )

        self.assertEqual(request.language, "en")
        self.assertEqual(request.budget.max, 1500)

    def test_language_defaults_to_english(self):
        request = ShoppingRequest(category="bag", search_query="everyday bag")

        self.assertEqual(request.language, "en")

    def test_invalid_language_is_rejected(self):
        for language in ("ar", "mixed"):
            with self.subTest(language=language):
                with self.assertRaises(ValidationError):
                    ShoppingRequest(
                        category="bag",
                        search_query="everyday bag",
                        language=language,
                    )

    def test_invalid_budget_range_is_rejected(self):
        with self.assertRaises(ValidationError):
            Budget(min=2000, max=1500)

    def test_optional_fields_default_when_missing(self):
        request = ShoppingRequest(category="bag", search_query="everyday bag")

        self.assertIsNone(request.filters.color)
        self.assertIsNone(request.filters.brand)
        self.assertIsNone(request.filters.size)
        self.assertIsNone(request.filters.occasion)
        self.assertIsNone(request.budget.min)
        self.assertIsNone(request.budget.max)
        self.assertEqual(request.budget.currency, "EGP")

    def test_unexpected_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            ShoppingRequest(
                category="bag",
                search_query="everyday bag",
                language="en",
                unexpected="value",
            )

    def test_unexpected_nested_fields_are_rejected(self):
        with self.assertRaises(ValidationError):
            ShoppingRequest(
                category="bag",
                search_query="everyday bag",
                filters={"pattern": "striped"},
            )


class ShoppingServiceTests(unittest.TestCase):
    def make_response(self, content):
        response = Mock()
        response.json.return_value = {"message": {"content": content}}
        return response

    @patch("chatbot_service.requests.post")
    def test_service_forces_language_to_english(self, post):
        post.return_value = self.make_response(
            json.dumps(
                {
                    "category": "handbag",
                    "search_query": "black handbag",
                    "language": "ar",
                }
            )
        )

        result = understand_request("Find a black handbag")

        self.assertEqual(result.language, "en")
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], OLLAMA_URL)
        self.assertEqual(post.call_args.kwargs["json"]["model"], MODEL_NAME)

    @patch("chatbot_service.requests.post")
    def test_explicit_occasion_is_filled_when_model_returns_null(self, post):
        post.return_value = self.make_response(
            json.dumps(
                {
                    "category": "handbag",
                    "search_query": "black handbag",
                    "filters": {"color": "black", "occasion": None},
                    "budget": {"max": 1500, "currency": "EGP"},
                }
            )
        )

        result = understand_request(
            "I need a black handbag for university, under 1500 EGP"
        )

        self.assertEqual(result.filters.color, "black")
        self.assertEqual(result.filters.occasion, "university")
        self.assertEqual(result.budget.max, 1500)

    @patch("chatbot_service.requests.post")
    def test_empty_message_is_rejected_without_request(self, post):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            understand_request("  \n")

        post.assert_not_called()

    @patch("chatbot_service.requests.post")
    def test_non_english_script_is_rejected_without_request(self, post):
        with self.assertRaisesRegex(ValueError, "in English"):
            understand_request("أريد حقيبة سوداء")

        post.assert_not_called()

    @patch("chatbot_service.requests.post")
    def test_invalid_model_json_has_clear_error(self, post):
        post.return_value = self.make_response("not json")

        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            understand_request("Find a black handbag")

    @patch("chatbot_service.requests.post")
    def test_schema_error_has_clear_error(self, post):
        post.return_value = self.make_response(
            json.dumps(
                {
                    "category": "handbag",
                    "search_query": "black handbag",
                    "filters": {"unexpected": "value"},
                }
            )
        )

        with self.assertRaisesRegex(RuntimeError, "ShoppingRequest schema"):
            understand_request("Find a black handbag")

    @patch("chatbot_service.requests.post")
    def test_connection_error_has_clear_error(self, post):
        post.side_effect = requests.ConnectionError("offline")

        with self.assertRaisesRegex(RuntimeError, "Could not connect to Ollama"):
            understand_request("Find a black handbag")

    @patch("chatbot_service.requests.post")
    def test_timeout_has_clear_error(self, post):
        post.side_effect = requests.Timeout("slow response")

        with self.assertRaisesRegex(RuntimeError, "timed out"):
            understand_request("Find a black handbag")


if __name__ == "__main__":
    unittest.main()
