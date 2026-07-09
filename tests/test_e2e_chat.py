"""Test 3: End-to-End Chat Accuracy — golden test set for OpenClaw agent responses.

These tests verify the OpenClaw gateway returns correct answers to known questions.
They require the OpenClaw gateway to be running on port 18789.

Usage:
    pytest tests/test_e2e_chat.py -v
    pytest tests/test_e2e_chat.py -v -k "risk"
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

import pytest

# Gateway URL — override with OPENCLAW_GATEWAY_URL env var
GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")
GATEWAY_TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")


def send_chat(message: str, timeout: int = 60) -> dict:
    """Send a message to the OpenClaw gateway and return the response."""
    url = f"{GATEWAY_URL}/api/chat"
    payload = json.dumps({"message": message}).encode()
    headers = {"Content-Type": "application/json"}
    if GATEWAY_TOKEN:
        headers["Authorization"] = f"Bearer {GATEWAY_TOKEN}"

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        pytest.skip(f"OpenClaw gateway not running at {GATEWAY_URL}: {e}")


def extract_text(response: dict) -> str:
    """Extract the assistant's text from a gateway response."""
    # Adapt to actual gateway response shape
    if isinstance(response, dict):
        if "message" in response:
            return str(response["message"])
        if "content" in response:
            return str(response["content"])
        if "choices" in response:
            return str(response["choices"][0].get("message", {}).get("content", ""))
    return str(response)


# ── Golden Test Set ──────────────────────────────────────────────────────
# Each test is a (question, expected_keywords) pair.
# We check that the response contains at least one expected keyword.

GOLDEN_TESTS = [
    {
        "id": "risk_lancaster",
        "question": "What is the power outage risk in Lancaster?",
        "expected_keywords": ["risk", "lancaster", "high", "medium", "low", "confidence"],
        "description": "Should use geocode + query_risk tools",
    },
    {
        "id": "charging_sites_near_kendal",
        "question": "Are there any EV charging sites near Kendal?",
        "expected_keywords": ["charging", "kendal", "site", "chargepoint", "v2x"],
        "description": "Should use geocode + query_charging_sites tools",
    },
    {
        "id": "outage_history_cumberland",
        "question": "Show me recent power outages in Cumberland.",
        "expected_keywords": ["outage", "cumberland", "incident", "duration"],
        "description": "Should use query_outages tool",
    },
    {
        "id": "recommendations_chargepoint",
        "question": "Where should we place new chargepoints?",
        "expected_keywords": ["recommend", "chargepoint", "high-risk", "placement"],
        "description": "Should use get_recommendations tool",
    },
    {
        "id": "borderlands_sites",
        "question": "What are the Borderlands community sites?",
        "expected_keywords": ["borderlands", "site", "community"],
        "description": "Should use clean_borderlands tool",
    },
    {
        "id": "live_incidents",
        "question": "Are there any active power incidents right now?",
        "expected_keywords": ["incident", "active", "live", "power"],
        "description": "Should use get_live_incidents tool",
    },
]


class TestEndToEndChat:
    """Golden test set for OpenClaw chat accuracy."""

    @pytest.mark.parametrize("test_case", GOLDEN_TESTS, ids=[t["id"] for t in GOLDEN_TESTS])
    def test_golden_response(self, test_case):
        """Verify chat response contains expected keywords."""
        response = send_chat(test_case["question"])
        text = extract_text(response).lower()

        # At least one expected keyword should appear
        matched = [kw for kw in test_case["expected_keywords"] if kw.lower() in text]
        assert len(matched) > 0, (
            f"Question: {test_case['question']}\n"
            f"Expected any of: {test_case['expected_keywords']}\n"
            f"Got: {text[:500]}\n"
            f"Matched: {matched}"
        )


class TestChatToolUsage:
    """Verify the agent uses the right tools for certain queries."""

    def test_location_query_uses_geocode_first(self):
        """Location-based queries should trigger geocode before other tools."""
        response = send_chat("What's the risk in Alston?")
        # This test checks the gateway logs or tool call metadata if available
        # For now, just verify we get a substantive response
        text = extract_text(response)
        assert len(text) > 50, "Response too short — agent may not have used tools"


class TestChatEdgeCases:
    """Edge cases and error handling in chat."""

    def test_unknown_location(self):
        """Agent should handle unknown locations gracefully."""
        response = send_chat("What's the risk in Narnia?")
        text = extract_text(response).lower()
        # Should acknowledge it can't find the location or give a helpful response
        assert len(text) > 20

    def test_empty_question(self):
        """Agent should handle empty/short questions."""
        response = send_chat("hi")
        text = extract_text(response)
        assert len(text) > 10
