import json
import re
from copy import deepcopy

import requests
from pydantic import ValidationError

from schemas import ShoppingRequest


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "qwen2.5:3b "

# Allowed values taken from the product catalog (styles.csv):
# articleType -> category, baseColour -> filters.color
ALLOWED_CATEGORIES = [
    "Tshirts", "Shirts", "Tops", "Tunics", "Kurtas", "Kurtis", "Kurta Sets",
    "Sweatshirts", "Sweaters", "Jackets", "Blazers", "Dresses", "Skirts",
    "Jeans", "Trousers", "Shorts", "Track Pants", "Leggings", "Capris",
    "Lounge Pants", "Night suits", "Nightdress", "Sarees", "Dupatta",
    "Bra", "Briefs", "Boxers", "Trunk", "Innerwear Vests", "Socks",
    "Casual Shoes", "Sports Shoes", "Formal Shoes", "Heels", "Flats",
    "Sandals", "Sports Sandals", "Flip Flops",
    "Watches", "Sunglasses", "Belts", "Wallets", "Ties", "Cufflinks",
    "Scarves", "Stoles", "Caps", "Handbags", "Clutches", "Backpacks",
    "Duffel Bag", "Laptop Bag", "Earrings", "Necklace and Chains", "Pendant",
    "Ring", "Bangle", "Bracelet", "Jewellery Set", "Accessory Gift Set",
]
ALLOWED_COLORS = [
    "Beige", "Black", "Blue", "Bronze", "Brown", "Burgundy", "Charcoal",
    "Coffee Brown", "Copper", "Cream", "Fluorescent Green", "Gold", "Green",
    "Grey", "Grey Melange", "Khaki", "Lavender", "Lime Green", "Magenta",
    "Maroon", "Mauve", "Metallic", "Multi", "Mushroom Brown", "Mustard",
    "Navy Blue", "Nude", "Off White", "Olive", "Orange", "Peach", "Pink",
    "Purple", "Red", "Rose", "Rust", "Sea Green", "Silver", "Skin", "Steel",
    "Tan", "Taupe", "Teal", "Turquoise Blue", "White", "Yellow",
]

SYSTEM_PROMPT = """
You are the request-understanding component of an AI Shopping Assistant.

Convert the customer's shopping message into a JSON object containing
exactly these top-level fields:

- category: string
- search_query: string
- filters: object with color, brand, size
- budget: object with min, max, currency
- language: "en"

Rules:
1. Understand English shopping requests only. Do not translate other languages.
2. Extract every product attribute and budget detail explicitly stated in the
    customer's message; do not leave an explicitly stated attribute null.
3. Budget interpretation examples:
    - "under 400" -> min=null, max=400
    - "below 500" -> min=null, max=500
    - "over 400" -> min=400, max=null
    - "between 200 and 400" -> min=200, max=400
    - "at least 1000" -> min=1000, max=null
4. Use null only when information is not provided and cannot reasonably be
    inferred. Do not guess missing product preferences.
5. Use EGP as the default currency when no currency is specified.
6. Represent prices as numbers, not strings.
7. Always set "language" to "en".
8. Keep search_query concise and useful for product retrieval.
9. Do not invent a brand, size, color, or budget.
10. Return only a JSON object with exactly the required fields. Do not include
    Markdown or explanations.
11. Before extracting details, infer and correct likely spelling mistakes in
    the customer's request using its surrounding words and shopping context.
    Use the corrected interpretation for category, color, brand, size, gender,
    budget, and search_query. Preserve proper nouns and do not guess when the
    intended word or attribute is ambiguous.
12. Extract the color, brand, size, and gender when explicitly stated or
    reasonably inferable from the request.
13. search_query must contain only the product keywords: product type, color,
    material or style, and brand. Do NOT put prices, budget words (under, over,
    between, max, EGP), sizes, or filler words (for, a, I need) in it.
"""

SYSTEM_PROMPT += (
    """
Allowed values (copy them exactly, including capital letters and spaces):

14. category must be EXACTLY ONE value from this list, or null if the message
    does not mention any product type:
    """
    + ", ".join(ALLOWED_CATEGORIES)
    + """

15. filters.color must be EXACTLY ONE value from this list, or null if no color
    is mentioned:
    """
    + ", ".join(ALLOWED_COLORS)
    + """

16. Map the customer's words to the closest allowed value. Examples:
    "t-shirt" -> "Tshirts", "navy" -> "Navy Blue", "olive green" -> "Olive",
    "sneakers" or "running shoes" -> "Sports Shoes", "formal shoes" ->
    "Formal Shoes", "hoodie" -> "Sweatshirts", "sports bra" -> "Bra".
    Never output a category or color that is not in the lists above.
"""
)

SPELLING_CORRECTION_PROMPT = """
Correct only clear spelling or typing mistakes in an English shopping request.
Use context to infer the intended words. Preserve the request's meaning, proper
nouns, quantities, and budget; do not add or remove details. Leave ambiguous
words unchanged. Return only a JSON object with a string field named
corrected_message.
"""


def _match_allowed(value: str, allowed: list[str]) -> str:
    """Return the allowed value that equals `value` ignoring case/spacing."""
    wanted = " ".join(value.lower().split())
    for item in allowed:
        if item.lower() == wanted:
            return item
    return value


def _singularized_words(value: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", value.casefold())
    return [word[:-1] if len(word) > 3 and word.endswith("s") else word for word in words]


def _infer_category(search_query: object) -> str | None:
    if not isinstance(search_query, str):
        return None

    query_words = _singularized_words(search_query)
    matches = []
    for category in ALLOWED_CATEGORIES:
        category_words = _singularized_words(category)
        width = len(category_words)
        if any(
            query_words[index:index + width] == category_words
            for index in range(len(query_words) - width + 1)
        ):
            matches.append(category)
    return matches[0] if len(matches) == 1 else None


class OllamaConnectionError(RuntimeError):
    """Raised when the local Ollama service cannot be reached."""


class OllamaTimeoutError(OllamaConnectionError):
    """Raised when an Ollama request exceeds its timeout."""


class OllamaResponseError(RuntimeError):
    """Raised when Ollama returns an unexpected API response."""


class ModelJSONError(OllamaResponseError):
    """Raised when the model response content is not valid JSON."""


def get_model_output(
    message: str,
    model_name: str = MODEL_NAME,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
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
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": system_prompt},
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
    """This function converts the JSON string returned by the Qwen model into a Python object 
    (dictionary) so the rest of your code can work with it."""
    try:
        return json.loads(model_output)
    except (ValueError, TypeError) as exc:
        raise ModelJSONError("Ollama returned invalid JSON.") from exc


def _correct_spelling(message: str, model_name: str) -> str:
    correction = decode_model_output(
        get_model_output(message, model_name, SPELLING_CORRECTION_PROMPT)
    )
    if isinstance(correction, dict):
        corrected_message = correction.get("corrected_message")
        if isinstance(corrected_message, str) and corrected_message.strip():
            return corrected_message.strip()
    return message


def postprocess_model_output(message: str, parsed_output: object) -> object:
    """Apply deterministic category, color, and language normalization."""
    parsed_output = deepcopy(parsed_output)
    if isinstance(parsed_output, dict):
        search_query = parsed_output.get("search_query")
        if not isinstance(search_query, str) or not search_query.strip():
            search_query = message.strip()
            parsed_output["search_query"] = search_query

        # Fix only capitalization/spacing of allowed values (e.g. "tshirts" ->
        # "Tshirts"). Values outside the lists are left as the model wrote them,
        # so wrong outputs stay visible when you compare models.
        category = parsed_output.get("category")
        if isinstance(category, str):
            parsed_output["category"] = _match_allowed(category, ALLOWED_CATEGORIES)
        if not isinstance(parsed_output.get("category"), str) or not parsed_output["category"].strip():
            inferred_category = _infer_category(search_query)
            if inferred_category is not None:
                parsed_output["category"] = inferred_category
        filters = parsed_output.get("filters")
        if isinstance(filters, dict) and isinstance(filters.get("color"), str):
            filters["color"] = _match_allowed(filters["color"], ALLOWED_COLORS)

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
    corrected_message = _correct_spelling(message, model_name)
    parsed_output = parse_model_output(
        corrected_message,
        get_model_output(corrected_message, model_name),
    )

    if not isinstance(parsed_output, dict):
        raise OllamaResponseError("Ollama response must contain a JSON object.")

    try:
        request = ShoppingRequest.model_validate(parsed_output)
    except ValidationError as exc:
        print(exc)
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