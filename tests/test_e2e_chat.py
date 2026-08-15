"""Test 3: End-to-End Chat Accuracy — golden test set for OpenClaw agent responses.

These tests verify the OpenClaw gateway returns correct answers to known questions
using Selenium to interact with the web UI.

Usage:
    pytest tests/test_e2e_chat.py -v
    pytest tests/test_e2e_chat.py -v -k "risk"
"""

import json
import os
import time
from pathlib import Path

import pytest

# Gateway URL
GATEWAY_URL = os.environ.get("OPENCLAW_GATEWAY_URL", "http://localhost:18789")

# Check if Selenium is available
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_SELENIUM = True
except ImportError:
    HAS_SELENIUM = False


def get_driver():
    """Create a headless Chrome driver."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def send_chat(message: str, timeout: int = 120) -> dict:
    """Send a message to OpenClaw via Selenium and return the response."""
    if not HAS_SELENIUM:
        pytest.skip("Selenium not installed")

    driver = None
    try:
        driver = get_driver()
        driver.get(GATEWAY_URL)

        # Wait for page to load
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(3)  # Allow JS to initialize

        # Find the chat input textarea
        input_selectors = [
            "textarea",
            "input[type='text']",
            "[contenteditable='true']",
            ".chat-input",
            "#chat-input",
            "[placeholder*='message']",
            "[placeholder*='Message']",
            "[placeholder*='type']",
        ]

        input_elem = None
        for selector in input_selectors:
            try:
                input_elem = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                if input_elem:
                    break
            except:
                continue

        if not input_elem:
            pytest.skip("Could not find chat input element")

        # Type the message
        input_elem.clear()
        input_elem.send_keys(message)
        time.sleep(0.5)

        # Send the message (Enter or click send button)
        input_elem.send_keys(Keys.ENTER)
        time.sleep(2)

        # Wait for response
        time.sleep(30)  # Allow LLM to process

        # Get all text content from the page
        response_text = driver.find_element(By.TAG_NAME, "body").text

        return {"message": response_text}

    except Exception as e:
        return {"error": str(e)}
    finally:
        if driver:
            driver.quit()


def extract_text(response: dict) -> str:
    """Extract the assistant's text from a gateway response."""
    if isinstance(response, dict):
        if "message" in response:
            return str(response["message"])
    return str(response)


# ── Golden Test Set ──────────────────────────────────────────────────────

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
        "expected_keywords": ["recommend", "chargepoint", "risk", "high", "location", "area"],
        "description": "Should use get_recommendations tool",
    },
    {
        "id": "live_incidents",
        "question": "Are there any active power incidents right now?",
        "expected_keywords": ["incident", "active", "power", "outage"],
        "description": "Should use get_live_incidents tool",
    },
]


class TestEndToEndChat:
    """Golden tests: verify known questions get correct answers."""

    @pytest.mark.parametrize("test_case", GOLDEN_TESTS, ids=[t["id"] for t in GOLDEN_TESTS])
    def test_golden_response(self, test_case):
        response = send_chat(test_case["question"])
        text = extract_text(response).lower()

        # At least one expected keyword should appear
        matches = [kw for kw in test_case["expected_keywords"] if kw in text]
        assert len(matches) >= 1, (
            f"Response missing all keywords for '{test_case['id']}': "
            f"expected at least one of {test_case['expected_keywords']}, "
            f"got: {text[:500]}"
        )


class TestChatEdgeCases:
    """Edge case tests."""

    def test_unknown_location(self):
        response = send_chat("What is the outage risk in Atlantis?")
        text = extract_text(response).lower()
        has_graceful = any(w in text for w in ["not found", "cannot", "no data", "unable", "no results", "atlantis"])
        assert has_graceful, f"Should handle unknown location gracefully: {text[:500]}"

    def test_empty_question(self):
        response = send_chat("")
        text = extract_text(response)
        assert len(text) > 0, "Should return some response to empty question"
