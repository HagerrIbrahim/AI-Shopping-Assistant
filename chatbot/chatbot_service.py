
import json
import re
from copy import deepcopy

import requests
from pydantic import ValidationError

from schemas import ShoppingRequest


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b"
OCCASION_PATTERN = re.compile(
    r"\b(university|work|wedding|party|travel|everyday(?:\s+use)?)\b",
    re.IGNORECASE,
)


SYSTEM_PROMPT = """
You are the request-understanding component of an AI Shopping Assistant.

Convert the customer's shopping message into a JSON object containing
exactly these top-level fields:

- category: string
- search_query: string
- filters: object with color, brand, size, occasion
- budget: object with min, max, currency
- language: "en"

Rules:
1. Understand English shopping requests only. Do not translate other languages.
2. Extract every product attribute and budget detail explicitly stated in the
    customer's message; do not leave an explicitly stated attribute null.
3. Set filters.occasion when a use or occasion is mentioned, including
    university, work, wedding, party, travel, and everyday use. For example,
    "for university" means occasion is "university".
4. Interpret "under X" as budget.max X and "over X" as budget.min X.
5. Use null only when information is not provided and cannot reasonably be
    inferred. Do not guess missing product preferences.
6. Use EGP as the default currency when no currency is specified.
7. Represent prices as numbers, not strings.
8. Always set "language" to "en".
9. Keep search_query concise and useful for product retrieval.
10. Do not invent a brand, size, color, occasion, or budget.
11. Return only a JSON object with exactly the required fields. Do not include
    Markdown or explanations.
"""


def _extract_explicit_occasion(message: str) -> str | None:
    match = OCCASION_PATTERN.search(message)
    if match is None:
        return None

    return " ".join(match.group(1).lower().split())


class OllamaConnectionError(RuntimeError):
    """Raised when the local Ollama service cannot be reached."""


class OllamaTimeoutError(OllamaConnectionError):
    """Raised when an Ollama request exceeds its timeout."""


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns an unexpected API response."""


class ModelJSONError(OllamaResponseError):
    """Raised when the model response content is not valid JSON."""


def get_model_output(message: str, model_name: str = MODEL_NAME) -> str:
    """Send a message to Ollama and return its raw response content."""
    if not message.strip():
        raise ValueError("Customer message cannot be empty.")
    if any(character.isalpha() and not character.isascii() for character in message):
        raise ValueError(
            "Please enter your shopping request in English using English letters."
        )

    payload = {
        "model": model_name,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()

    except requests.Timeout as exc:
        raise OllamaTimeoutError("Ollama request timed out after 120 seconds.") from exc
    except requests.RequestException as exc:
        raise OllamaConnectionError(
            "Could not connect to Ollama. Check that Ollama is running "
            "and the model is downloaded."
        ) from exc

    try:
        response_data = response.json()
        model_output = response_data["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaResponseError(
            "Ollama returned an unexpected response format."
        ) from exc

    if not isinstance(model_output, str):
        raise OllamaResponseError("Ollama response content must be a string.")

    return model_output


def decode_model_output(model_output: str) -> object:
    """Parse the model's JSON without applying service post-processing."""
    try:
        return json.loads(model_output)
    except (ValueError, TypeError) as exc:
        raise ModelJSONError("Ollama returned invalid JSON.") from exc


def postprocess_model_output(message: str, parsed_output: object) -> object:
    """Apply the existing deterministic occasion and language normalization."""
    parsed_output = deepcopy(parsed_output)
    if isinstance(parsed_output, dict):
        explicit_occasion = _extract_explicit_occasion(message)
        if explicit_occasion is not None:
            filters = parsed_output.get("filters")
            if filters is None:
                filters = {}
            if isinstance(filters, dict):
                filters["occasion"] = explicit_occasion
                parsed_output["filters"] = filters

        # Language is fixed by the service, not classified by the model.
        parsed_output["language"] = "en"

    return parsed_output


def parse_model_output(message: str, model_output: str) -> object:
    """Parse model JSON and apply the same deterministic service normalizations."""
    return postprocess_model_output(message, decode_model_output(model_output))


def understand_request(
    message: str,
    model_name: str = MODEL_NAME,
) -> ShoppingRequest:
    """Convert a customer message into a validated shopping request."""
    model_output = get_model_output(message, model_name)
    parsed_output = parse_model_output(message, model_output)

    if not isinstance(parsed_output, dict):
        raise OllamaResponseError("Ollama response must contain a JSON object.")

    try:
        request = ShoppingRequest.model_validate(parsed_output)
    except ValidationError as exc:
        raise RuntimeError(
            "Ollama returned data that did not match the ShoppingRequest schema."
        ) from exc

    return request


if __name__ == "__main__":
    customer_message = input("Enter a shopping request: ")

    try:
        shopping_request = understand_request(customer_message)

        print("\nValidated shopping request:")
        print(
            json.dumps(
                shopping_request.model_dump(),
                indent=2,
                ensure_ascii=False,
            )
        )

    except (ValueError, RuntimeError) as exc:
        print(f"\nError: {exc}")
