from pydantic import ValidationError
from schemas import Budget, ShoppingRequest

# Test 1: Valid shopping request
request = ShoppingRequest(
    category="handbag",
    search_query="black handbag for university",
    filters={"color": "black", "occasion": "university"},
    budget={"max": 1500, "currency": "EGP"},
    language="en",
)
print("PASS: Valid request")

# Test 2: Invalid budget range
try:
    Budget(min=2000, max=1500)
    raise AssertionError("Invalid budget was accepted")
except ValidationError:
    print("PASS: Invalid budget rejected")

print("All tests passed!")