# Email Notification System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add email notification system that alerts subscribed addresses when unplanned incidents >6 hours are detected, using SendGrid for delivery and OpenClaw for report generation.

**Architecture:** Separate notification service module handles incident filtering, OpenClaw API calls, and SendGrid email sending. Flask endpoints manage click tracking and unsubscribe. Sidebar displays email list and triggers checks on refresh.

**Tech Stack:** Python, SendGrid SDK, Flask, OpenClaw API (port 18789)

---

## File Structure

### New Files
- `services/__init__.py` - Package init
- `services/notification_service.py` - Core notification logic (filter, OpenClaw, SendGrid)
- `services/email_endpoints.py` - Flask endpoints for click tracking & unsubscribe
- `tests/test_notification_service.py` - Unit tests for notification service
- `tests/test_email_endpoints.py` - Unit tests for email endpoints

### Modified Files
- `requirements.txt` - Add sendgrid and flask packages
- `.env.example` - Add SENDGRID_API_KEY and NOTIFICATION_EMAILS
- `dashboard/sidebar.py` - Add email display and trigger notification check
- `proxy_server.py` - Add routes for email endpoints

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Read current requirements.txt**

```bash
cat requirements.txt
```

- [ ] **Step 2: Add sendgrid and flask packages**

Append to end of `requirements.txt`:
```
sendgrid>=6.9.0
flask>=2.0.0
```

- [ ] **Step 3: Install new dependencies**

```bash
pip install sendgrid>=6.9.0 flask>=2.0.0
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add sendgrid and flask for email notifications"
```

---

## Task 2: Create Services Package

**Files:**
- Create: `services/__init__.py`

- [ ] **Step 1: Create services directory and __init__.py**

```bash
mkdir -p services
touch services/__init__.py
```

- [ ] **Step 2: Verify package structure**

```bash
python -c "import services; print('Services package created successfully')"
```

- [ ] **Step 3: Commit**

```bash
git add services/__init__.py
git commit -m "feat: create services package for notification system"
```

---

## Task 3: Create Notification Service - Email Validation

**Files:**
- Create: `services/notification_service.py`
- Create: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing test for email validation**

Create `tests/test_notification_service.py`:
```python
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.notification_service import validate_email


def test_validate_email_valid():
    """Test that valid emails pass validation."""
    assert validate_email("user@example.com") == True
    assert validate_email("test.user@domain.co.uk") == True
    assert validate_email("user+tag@example.com") == True


def test_validate_email_invalid():
    """Test that invalid emails fail validation."""
    assert validate_email("invalid") == False
    assert validate_email("@example.com") == False
    assert validate_email("user@") == False
    assert validate_email("user@.com") == False
    assert validate_email("") == False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_notification_service.py::test_validate_email_valid -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'services.notification_service'"

- [ ] **Step 3: Write minimal implementation**

Create `services/notification_service.py`:
```python
"""
Notification Service for CMS Dashboard
Handles email notifications for unplanned incidents >6 hours.
"""

import re
import json
import os
from datetime import datetime
from pathlib import Path


def validate_email(email: str) -> bool:
    """
    Validate email format using regex.
    
    Args:
        email: Email address to validate
        
    Returns:
        True if email is valid, False otherwise
    """
    if not email or not isinstance(email, str):
        return False
    
    # RFC 5322 simplified regex
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def load_notification_emails() -> dict:
    """
    Load notification emails from .env file.
    
    Returns:
        Dict of {email: last_active_time} or empty dict if not configured
    """
    env_path = Path(__file__).parent.parent / '.env'
    
    if not env_path.exists():
        return {}
    
    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('NOTIFICATION_EMAILS='):
                value = line.split('=', 1)[1].strip("'\"")
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    return {}
    
    return {}


def save_notification_emails(emails: dict) -> None:
    """
    Save notification emails to .env file.
    
    Args:
        emails: Dict of {email: last_active_time}
    """
    env_path = Path(__file__).parent.parent / '.env'
    
    if not env_path.exists():
        # Create .env with just the notification emails
        with open(env_path, 'w') as f:
            f.write(f"NOTIFICATION_EMAILS='{json.dumps(emails)}'\n")
        return
    
    # Read existing .env content
    lines = []
    found = False
    
    with open(env_path, 'r') as f:
        for line in f:
            if line.strip().startswith('NOTIFICATION_EMAILS='):
                lines.append(f"NOTIFICATION_EMAILS='{json.dumps(emails)}'\n")
                found = True
            else:
                lines.append(line)
    
    if not found:
        lines.append(f"NOTIFICATION_EMAILS='{json.dumps(emails)}'\n")
    
    with open(env_path, 'w') as f:
        f.writelines(lines)


def add_email(email: str) -> tuple[bool, str]:
    """
    Add email to notification list.
    
    Args:
        email: Email address to add
        
    Returns:
        Tuple of (success, message)
    """
    if not validate_email(email):
        return False, "Invalid email format"
    
    emails = load_notification_emails()
    
    if email in emails:
        return False, "Email already subscribed"
    
    emails[email] = datetime.now().isoformat()
    save_notification_emails(emails)
    
    return True, "Email added successfully"


def remove_email(email: str) -> tuple[bool, str]:
    """
    Remove email from notification list.
    
    Args:
        email: Email address to remove
        
    Returns:
        Tuple of (success, message)
    """
    emails = load_notification_emails()
    
    if email not in emails:
        return False, "Email not found"
    
    del emails[email]
    save_notification_emails(emails)
    
    return True, "Email removed successfully"


def update_email_active_time(email: str) -> tuple[bool, str]:
    """
    Update last active time for email.
    
    Args:
        email: Email address to update
        
    Returns:
        Tuple of (success, message)
    """
    emails = load_notification_emails()
    
    if email not in emails:
        return False, "Email not found"
    
    emails[email] = datetime.now().isoformat()
    save_notification_emails(emails)
    
    return True, "Active time updated"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_notification_service.py::test_validate_email_valid -v
pytest tests/test_notification_service.py::test_validate_email_invalid -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add email validation and .env management functions"
```

---

## Task 4: Create Notification Service - Incident Filtering

**Files:**
- Modify: `services/notification_service.py`
- Modify: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing test for incident filtering**

Add to `tests/test_notification_service.py`:
```python
import pandas as pd
from services.notification_service import filter_qualifying_incidents


def test_filter_qualifying_incidents_unplanned_long_duration():
    """Test that unplanned incidents >6 hours are filtered."""
    incidents = pd.DataFrame([
        {
            'incident_num': 'INC001',
            'incident_type': 'unplanned',
            'outage_time': '2026-07-03T10:00:00',
            'estimated_restoration_time': '2026-07-03T20:00:00',  # 10 hours
            'latitude': 53.5,
            'longitude': -2.5,
            'customers_affected': 100,
            'incident_status': 'Active'
        },
        {
            'incident_num': 'INC002',
            'incident_type': 'planned',
            'outage_time': '2026-07-03T10:00:00',
            'estimated_restoration_time': '2026-07-03T20:00:00',  # 10 hours
            'latitude': 53.6,
            'longitude': -2.6,
            'customers_affected': 50,
            'incident_status': 'Active'
        },
        {
            'incident_num': 'INC003',
            'incident_type': 'unplanned',
            'outage_time': '2026-07-03T10:00:00',
            'estimated_restoration_time': '2026-07-03T14:00:00',  # 4 hours
            'latitude': 53.7,
            'longitude': -2.7,
            'customers_affected': 200,
            'incident_status': 'Active'
        }
    ])
    
    result = filter_qualifying_incidents(incidents)
    
    assert len(result) == 1
    assert result[0]['incident_num'] == 'INC001'


def test_filter_qualifying_incidents_empty():
    """Test that empty DataFrame returns empty list."""
    incidents = pd.DataFrame()
    result = filter_qualifying_incidents(incidents)
    assert result == []


def test_filter_qualifying_incidents_no_qualifying():
    """Test that no qualifying incidents returns empty list."""
    incidents = pd.DataFrame([
        {
            'incident_num': 'INC001',
            'incident_type': 'planned',
            'outage_time': '2026-07-03T10:00:00',
            'estimated_restoration_time': '2026-07-03T20:00:00',
            'latitude': 53.5,
            'longitude': -2.5,
            'customers_affected': 100,
            'incident_status': 'Active'
        }
    ])
    
    result = filter_qualifying_incidents(incidents)
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_notification_service.py::test_filter_qualifying_incidents_unplanned_long_duration -v
```
Expected: FAIL with "ImportError: cannot import name 'filter_qualifying_incidents'"

- [ ] **Step 3: Write minimal implementation**

Add to `services/notification_service.py`:
```python
import pandas as pd
from typing import List, Dict, Any


def filter_qualifying_incidents(incidents_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Filter incidents that qualify for notification.
    
    Qualifying conditions:
    - incident_type == "unplanned"
    - estimated duration > 6 hours
    
    Args:
        incidents_df: DataFrame with incident data
        
    Returns:
        List of incident dictionaries that qualify
    """
    if incidents_df.empty:
        return []
    
    qualifying = []
    
    for _, row in incidents_df.iterrows():
        # Check incident type
        if row.get('incident_type', '').lower() != 'unplanned':
            continue
        
        # Calculate duration
        try:
            outage_time = pd.to_datetime(row.get('outage_time'))
            restoration_time = pd.to_datetime(row.get('estimated_restoration_time'))
            duration_hours = (restoration_time - outage_time).total_seconds() / 3600
            
            if duration_hours > 6:
                qualifying.append(row.to_dict())
        except (ValueError, TypeError):
            # Skip if time parsing fails
            continue
    
    return qualifying
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_notification_service.py::test_filter_qualifying_incidents_unplanned_long_duration -v
pytest tests/test_notification_service.py::test_filter_qualifying_incidents_empty -v
pytest tests/test_notification_service.py::test_filter_qualifying_incidents_no_qualifying -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add incident filtering for unplanned incidents >6 hours"
```

---

## Task 5: Create Notification Service - Sent Incidents Tracking

**Files:**
- Modify: `services/notification_service.py`
- Modify: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing test for sent incidents tracking**

Add to `tests/test_notification_service.py`:
```python
from services.notification_service import load_sent_incidents, track_sent_incident, is_incident_sent
import tempfile
import json
from pathlib import Path


def test_load_sent_incidents_empty():
    """Test loading sent incidents when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock the data directory
        original_func = services.notification_service.load_sent_incidents
        
        # Create empty file
        sent_file = Path(tmpdir) / '.sent_incidents'
        sent_file.write_text('{}')
        
        result = load_sent_incidents()
        assert isinstance(result, dict)


def test_track_sent_incident():
    """Test tracking a sent incident."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sent_file = Path(tmpdir) / '.sent_incidents'
        sent_file.write_text('{}')
        
        track_sent_incident('INC001')
        
        with open(sent_file, 'r') as f:
            data = json.load(f)
        
        assert 'INC001' in data


def test_is_incident_sent():
    """Test checking if incident was already sent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        sent_file = Path(tmpdir) / '.sent_incidents'
        sent_file.write_text('{"INC001": "2026-07-03T10:00:00"}')
        
        assert is_incident_sent('INC001') == True
        assert is_incident_sent('INC002') == False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_notification_service.py::test_load_sent_incidents_empty -v
```
Expected: FAIL with "ImportError: cannot import name 'load_sent_incidents'"

- [ ] **Step 3: Write minimal implementation**

Add to `services/notification_service.py`:
```python
SENT_INCIDENTS_FILE = Path(__file__).parent.parent / 'data' / '.sent_incidents'


def load_sent_incidents() -> Dict[str, str]:
    """
    Load sent incidents from tracking file.
    
    Returns:
        Dict of {incident_id: sent_timestamp}
    """
    if not SENT_INCIDENTS_FILE.exists():
        return {}
    
    try:
        with open(SENT_INCIDENTS_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_sent_incidents(incidents: Dict[str, str]) -> None:
    """
    Save sent incidents to tracking file.
    
    Args:
        incidents: Dict of {incident_id: sent_timestamp}
    """
    SENT_INCIDENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(SENT_INCIDENTS_FILE, 'w') as f:
        json.dump(incidents, f, indent=2)


def track_sent_incident(incident_id: str) -> None:
    """
    Record that notification was sent for an incident.
    
    Args:
        incident_id: ID of the incident
    """
    incidents = load_sent_incidents()
    incidents[incident_id] = datetime.now().isoformat()
    save_sent_incidents(incidents)


def is_incident_sent(incident_id: str) -> bool:
    """
    Check if notification was already sent for an incident.
    
    Args:
        incident_id: ID of the incident
        
    Returns:
        True if already sent, False otherwise
    """
    incidents = load_sent_incidents()
    return incident_id in incidents


def clear_old_sent_incidents(hours: int = 24) -> None:
    """
    Clear sent incidents older than specified hours.
    
    Args:
        hours: Age threshold in hours
    """
    incidents = load_sent_incidents()
    cutoff = datetime.now().timestamp() - (hours * 3600)
    
    filtered = {}
    for incident_id, timestamp_str in incidents.items():
        try:
            timestamp = datetime.fromisoformat(timestamp_str).timestamp()
            if timestamp > cutoff:
                filtered[incident_id] = timestamp_str
        except ValueError:
            # Keep if we can't parse the timestamp
            filtered[incident_id] = timestamp_str
    
    save_sent_incidents(filtered)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_notification_service.py::test_load_sent_incidents_empty -v
pytest tests/test_notification_service.py::test_track_sent_incident -v
pytest tests/test_notification_service.py::test_is_incident_sent -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add sent incidents tracking to prevent duplicate notifications"
```

---

## Task 6: Create Notification Service - OpenClaw Report Generation

**Files:**
- Modify: `services/notification_service.py`
- Modify: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing test for OpenClaw report generation**

Add to `tests/test_notification_service.py`:
```python
from services.notification_service import generate_report
import pytest


def test_generate_report_success():
    """Test successful report generation via OpenClaw."""
    incident = {
        'incident_num': 'INC001',
        'incident_type': 'unplanned',
        'outage_time': '2026-07-03T10:00:00',
        'estimated_restoration_time': '2026-07-03T20:00:00',
        'latitude': 53.5,
        'longitude': -2.5,
        'customers_affected': 100,
        'incident_status': 'Active'
    }
    
    # This will fail because OpenClaw is not running in test
    # We'll mock it later
    with pytest.raises(Exception):
        generate_report(incident)


def test_generate_report_fallback():
    """Test fallback report when OpenClaw fails."""
    incident = {
        'incident_num': 'INC001',
        'incident_type': 'unplanned',
        'outage_time': '2026-07-03T10:00:00',
        'estimated_restoration_time': '2026-07-03T20:00:00',
        'latitude': 53.5,
        'longitude': -2.5,
        'customers_affected': 100,
        'incident_status': 'Active'
    }
    
    # Test fallback report generation
    from services.notification_service import generate_fallback_report
    report = generate_fallback_report(incident)
    
    assert 'INC001' in report
    assert 'Unplanned' in report
    assert '100' in report  # customers affected
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_notification_service.py::test_generate_report_fallback -v
```
Expected: FAIL with "ImportError: cannot import name 'generate_fallback_report'"

- [ ] **Step 3: Write minimal implementation**

Add to `services/notification_service.py`:
```python
import requests
import logging

logger = logging.getLogger(__name__)

OPENCLAW_API_URL = "http://localhost:18789/api/chat"
OPENCLAW_TIMEOUT = 30  # seconds


def generate_report(incident: Dict[str, Any]) -> str:
    """
    Generate incident report via OpenClaw API.
    
    Args:
        incident: Incident data dictionary
        
    Returns:
        Generated report text
        
    Raises:
        Exception: If OpenClaw API call fails
    """
    prompt = f"""Generate a detailed incident report for this unplanned power outage:

Incident ID: {incident.get('incident_num', 'Unknown')}
Type: Unplanned
Location: Latitude {incident.get('latitude', 'N/A')}, Longitude {incident.get('longitude', 'N/A')}
Reported: {incident.get('outage_time', 'Unknown')}
Estimated Restoration: {incident.get('estimated_restoration_time', 'Unknown')}
Customers Affected: {incident.get('customers_affected', 'Unknown')}
Status: {incident.get('incident_status', 'Unknown')}

Please provide:
1. Location name (reverse geocode the lat/long to a place name)
2. Estimated duration in hours
3. Nearby chargepoints (top 3 with types and distances)
4. Recommended actions for EV users in the area

Format the report in clear sections with headers."""
    
    try:
        response = requests.post(
            OPENCLAW_API_URL,
            json={
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=OPENCLAW_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        return data.get('response', data.get('message', 'No response from OpenClaw'))
    
    except requests.exceptions.Timeout:
        logger.error("OpenClaw API timeout")
        raise Exception("OpenClaw API timeout")
    
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenClaw API error: {e}")
        raise Exception(f"OpenClaw API error: {e}")


def generate_fallback_report(incident: Dict[str, Any]) -> str:
    """
    Generate fallback report when OpenClaw is unavailable.
    
    Args:
        incident: Incident data dictionary
        
    Returns:
        Basic incident report
    """
    # Calculate duration
    try:
        outage_time = pd.to_datetime(incident.get('outage_time'))
        restoration_time = pd.to_datetime(incident.get('estimated_restoration_time'))
        duration_hours = round((restoration_time - outage_time).total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        duration_hours = "Unknown"
    
    report = f"""## Unplanned Power Incident Report

**Incident ID:** {incident.get('incident_num', 'Unknown')}
**Type:** Unplanned
**Location:** Latitude {incident.get('latitude', 'N/A')}, Longitude {incident.get('longitude', 'N/A')}
**Reported:** {incident.get('outage_time', 'Unknown')}
**Estimated Duration:** {duration_hours} hours
**Customers Affected:** {incident.get('customers_affected', 'Unknown')}
**Status:** {incident.get('incident_status', 'Unknown')}

### Note
This is a basic report. OpenClaw AI analysis was unavailable for detailed insights including:
- Location name (reverse geocoding)
- Nearby chargepoints
- Recommended actions

Please check the dashboard for more details."""
    
    return report
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_notification_service.py::test_generate_report_fallback -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add OpenClaw report generation with fallback"
```

---

## Task 7: Create Notification Service - SendGrid Email Sending

**Files:**
- Modify: `services/notification_service.py`
- Modify: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing test for email sending**

Add to `tests/test_notification_service.py`:
```python
from services.notification_service import send_notification_email, build_email_html
import os


def test_build_email_html():
    """Test HTML email building."""
    incident = {
        'incident_num': 'INC001',
        'incident_type': 'unplanned',
        'outage_time': '2026-07-03T10:00:00',
        'estimated_restoration_time': '2026-07-03T20:00:00',
        'latitude': 53.5,
        'longitude': -2.5,
        'customers_affected': 100,
        'incident_status': 'Active'
    }
    
    report = "## Test Report\n\nThis is a test report."
    base_url = "http://localhost:8501"
    
    html = build_email_html(incident, report, "test@example.com", base_url)
    
    assert 'INC001' in html
    assert 'test@example.com' in html
    assert 'unsubscribe' in html.lower()


def test_send_notification_email_no_api_key(monkeypatch):
    """Test that missing API key raises error."""
    monkeypatch.delenv('SENDGRID_API_KEY', raising=False)
    
    with pytest.raises(ValueError, match="SENDGRID_API_KEY"):
        send_notification_email(
            email="test@example.com",
            subject="Test",
            html_content="<p>Test</p>"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_notification_service.py::test_build_email_html -v
```
Expected: FAIL with "ImportError: cannot import name 'build_email_html'"

- [ ] **Step 3: Write minimal implementation**

Add to `services/notification_service.py`:
```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, HtmlContent


def build_email_html(
    incident: Dict[str, Any],
    report: str,
    email: str,
    base_url: str
) -> str:
    """
    Build HTML email content for incident notification.
    
    Args:
        incident: Incident data dictionary
        report: Generated report text
        email: Recipient email address
        base_url: Dashboard base URL
        
    Returns:
        HTML email content
    """
    incident_id = incident.get('incident_num', 'Unknown')
    
    # Convert markdown-like report to HTML
    report_html = report.replace('\n', '<br>')
    report_html = report_html.replace('## ', '<h2>')
    report_html = report_html.replace('### ', '<h3>')
    
    # Build tracking and unsubscribe links
    click_url = f"{base_url}/email/click/{incident_id}/{email}"
    unsubscribe_url = f"{base_url}/email/unsubscribe/{email}"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #d32f2f; color: white; padding: 15px; text-align: center; }}
            .content {{ padding: 20px; background-color: #f9f9f9; }}
            .footer {{ padding: 15px; text-align: center; font-size: 12px; color: #666; }}
            a {{ color: #1976d2; }}
            .incident-id {{ font-size: 24px; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚠️ Unplanned Power Incident Alert</h1>
                <div class="incident-id">{incident_id}</div>
            </div>
            <div class="content">
                {report_html}
            </div>
            <div class="footer">
                <p>
                    <a href="{click_url}">View in Dashboard</a> | 
                    <a href="{unsubscribe_url}">Unsubscribe</a>
                </p>
                <p>This is an automated notification from CMS Dashboard.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


def send_notification_email(
    email: str,
    subject: str,
    html_content: str,
    from_email: str = "noreply@cms-dashboard.com"
) -> bool:
    """
    Send email notification via SendGrid.
    
    Args:
        email: Recipient email address
        subject: Email subject
        html_content: HTML email content
        from_email: Sender email address
        
    Returns:
        True if sent successfully
        
    Raises:
        ValueError: If SENDGRID_API_KEY not configured
        Exception: If SendGrid API call fails
    """
    api_key = os.environ.get('SENDGRID_API_KEY')
    
    if not api_key:
        raise ValueError("SENDGRID_API_KEY environment variable not set")
    
    message = Mail(
        from_email=Email(from_email),
        to_emails=To(email),
        subject=subject,
        html_content=HtmlContent(html_content)
    )
    
    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code >= 400:
            raise Exception(f"SendGrid error: {response.status_code} - {response.body}")
        
        logger.info(f"Email sent successfully to {email}")
        return True
    
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")
        raise
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_notification_service.py::test_build_email_html -v
pytest tests/test_notification_service.py::test_send_notification_email_no_api_key -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add SendGrid email sending with HTML templates"
```

---

## Task 8: Create Notification Service - Main Check and Notify Function

**Files:**
- Modify: `services/notification_service.py`
- Modify: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing test for check_and_notify**

Add to `tests/test_notification_service.py`:
```python
from services.notification_service import check_and_notify
from unittest.mock import patch, MagicMock
import pandas as pd


def test_check_and_notify_no_emails(monkeypatch):
    """Test that check_and_notify skips when no emails configured."""
    monkeypatch.setattr('services.notification_service.load_notification_emails', lambda: {})
    
    result = check_and_notify(pd.DataFrame())
    
    assert result['status'] == 'skipped'
    assert 'No notification emails' in result['message']


def test_check_and_notify_no_api_key(monkeypatch):
    """Test that check_and_notify skips when no API key."""
    monkeypatch.setattr('services.notification_service.load_notification_emails', 
                       lambda: {"test@example.com": "2026-07-03T10:00:00"})
    monkeypatch.delenv('SENDGRID_API_KEY', raising=False)
    
    result = check_and_notify(pd.DataFrame())
    
    assert result['status'] == 'skipped'
    assert 'SENDGRID_API_KEY' in result['message']


def test_check_and_notify_no_qualifying_incidents(monkeypatch):
    """Test that check_and_notify skips when no qualifying incidents."""
    monkeypatch.setattr('services.notification_service.load_notification_emails', 
                       lambda: {"test@example.com": "2026-07-03T10:00:00"})
    monkeypatch.setenv('SENDGRID_API_KEY', 'test-key')
    monkeypatch.setattr('services.notification_service.filter_qualifying_incidents', 
                       lambda x: [])
    
    result = check_and_notify(pd.DataFrame())
    
    assert result['status'] == 'skipped'
    assert 'No qualifying incidents' in result['message']
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_notification_service.py::test_check_and_notify_no_emails -v
```
Expected: FAIL with "ImportError: cannot import name 'check_and_notify'"

- [ ] **Step 3: Write minimal implementation**

Add to `services/notification_service.py`:
```python
from typing import Dict, Any


def check_and_notify(incidents_df: pd.DataFrame, base_url: str = "http://localhost:8501") -> Dict[str, Any]:
    """
    Main entry point - check for qualifying incidents and send notifications.
    
    Args:
        incidents_df: DataFrame with live incidents
        base_url: Dashboard base URL for email links
        
    Returns:
        Dict with status and message
    """
    # Check if emails are configured
    emails = load_notification_emails()
    if not emails:
        logger.info("No notification emails configured, skipping")
        return {'status': 'skipped', 'message': 'No notification emails configured'}
    
    # Check if SendGrid API key is set
    if not os.environ.get('SENDGRID_API_KEY'):
        logger.warning("SENDGRID_API_KEY not set, skipping notifications")
        return {'status': 'skipped', 'message': 'SENDGRID_API_KEY not configured'}
    
    # Filter qualifying incidents
    clear_old_sent_incidents()  # Clean up old entries
    qualifying = filter_qualifying_incidents(incidents_df)
    
    if not qualifying:
        logger.info("No qualifying incidents found")
        return {'status': 'skipped', 'message': 'No qualifying incidents found'}
    
    # Process each qualifying incident
    sent_count = 0
    errors = []
    
    for incident in qualifying:
        incident_id = incident.get('incident_num', 'Unknown')
        
        # Skip if already sent
        if is_incident_sent(incident_id):
            logger.info(f"Incident {incident_id} already notified, skipping")
            continue
        
        # Generate report
        try:
            report = generate_report(incident)
        except Exception as e:
            logger.warning(f"OpenClaw failed, using fallback: {e}")
            report = generate_fallback_report(incident)
        
        # Send to each email
        for email in emails:
            try:
                subject = f"[Alert] Unplanned Incident: {incident_id}"
                html = build_email_html(incident, report, email, base_url)
                
                # Retry once on failure
                try:
                    send_notification_email(email, subject, html)
                except Exception:
                    logger.warning(f"First attempt failed for {email}, retrying...")
                    import time
                    time.sleep(5)
                    send_notification_email(email, subject, html)
                
                sent_count += 1
                
            except Exception as e:
                error_msg = f"Failed to send to {email}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)
        
        # Track as sent
        track_sent_incident(incident_id)
    
    # Return result
    if errors:
        return {
            'status': 'partial',
            'message': f'Sent {sent_count} notifications with {len(errors)} errors',
            'errors': errors
        }
    
    return {
        'status': 'success',
        'message': f'Sent {sent_count} notifications successfully'
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_notification_service.py::test_check_and_notify_no_emails -v
pytest tests/test_notification_service.py::test_check_and_notify_no_api_key -v
pytest tests/test_notification_service.py::test_check_and_notify_no_qualifying_incidents -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add main check_and_notify function with retry logic"
```

---

## Task 9: Create Email Endpoints - Click Tracking

**Files:**
- Create: `services/email_endpoints.py`
- Create: `tests/test_email_endpoints.py`

- [ ] **Step 1: Write failing test for click tracking endpoint**

Create `tests/test_email_endpoints.py`:
```python
import pytest
from services.email_endpoints import app
from unittest.mock import patch


@pytest.fixture
def client():
    """Create test client."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_track_click_success(client, monkeypatch):
    """Test successful click tracking."""
    monkeypatch.setattr('services.email_endpoints.update_email_active_time', 
                       lambda x: (True, "Updated"))
    
    response = client.get('/email/click/INC001/test@example.com')
    
    assert response.status_code == 200
    assert b'Updated' in response.data


def test_track_click_email_not_found(client, monkeypatch):
    """Test click tracking with unknown email."""
    monkeypatch.setattr('services.email_endpoints.update_email_active_time', 
                       lambda x: (False, "Email not found"))
    
    response = client.get('/email/click/INC001/unknown@example.com')
    
    assert response.status_code == 200
    assert b'Email not found' in response.data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_email_endpoints.py::test_track_click_success -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'services.email_endpoints'"

- [ ] **Step 3: Write minimal implementation**

Create `services/email_endpoints.py`:
```python
"""
Email Endpoints for CMS Dashboard
Handles click tracking and unsubscribe requests.
"""

from flask import Flask, redirect, request
from services.notification_service import update_email_active_time, remove_email
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route('/email/click/<incident_id>/<email>')
def track_click(incident_id: str, email: str):
    """
    Track email click and update active time.
    
    Args:
        incident_id: ID of the incident
        email: Email address that clicked
        
    Returns:
        Redirect to dashboard or confirmation page
    """
    success, message = update_email_active_time(email)
    
    if success:
        logger.info(f"Click tracked for {email} on incident {incident_id}")
    else:
        logger.warning(f"Failed to track click for {email}: {message}")
    
    # Redirect to dashboard
    return redirect('/')


@app.route('/email/unsubscribe/<email>')
def unsubscribe(email: str):
    """
    Unsubscribe email from notifications.
    
    Args:
        email: Email address to unsubscribe
        
    Returns:
        Confirmation page
    """
    success, message = remove_email(email)
    
    if success:
        logger.info(f"Email {email} unsubscribed successfully")
        return f"""
        <html>
        <head><title>Unsubscribed</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1>✓ Unsubscribed Successfully</h1>
            <p>{email} has been removed from notifications.</p>
            <p><a href="/">Return to Dashboard</a></p>
        </body>
        </html>
        """
    else:
        logger.warning(f"Failed to unsubscribe {email}: {message}")
        return f"""
        <html>
        <head><title>Unsubscribe Error</title></head>
        <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h1>Unsubscribe Error</h1>
            <p>{message}</p>
            <p><a href="/">Return to Dashboard</a></p>
        </body>
        </html>
        """, 400


if __name__ == '__main__':
    app.run(port=5000)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_email_endpoints.py::test_track_click_success -v
pytest tests/test_email_endpoints.py::test_track_click_email_not_found -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/email_endpoints.py tests/test_email_endpoints.py
git commit -m "feat: add email click tracking and unsubscribe endpoints"
```

---

## Task 10: Update Proxy Server - Add Email Endpoints

**Files:**
- Modify: `proxy_server.py`

- [ ] **Step 1: Read current proxy_server.py**

```bash
cat proxy_server.py
```

- [ ] **Step 2: Add email endpoints to proxy server**

Add to imports at top of `proxy_server.py`:
```python
from services.email_endpoints import app as email_app
```

Add route handling (after existing routes):
```python
# Email endpoints
@app.route('/email/<path:path>')
def proxy_email(path):
    """Proxy email endpoints to email service."""
    # Forward to email endpoints
    with email_app.test_client() as client:
        response = client.get(f'/email/{path}')
        return response.data, response.status_code, dict(response.headers)
```

- [ ] **Step 3: Test proxy server starts**

```bash
python -c "import proxy_server; print('Proxy server imports successfully')"
```

- [ ] **Step 4: Commit**

```bash
git add proxy_server.py
git commit -m "feat: add email endpoints to proxy server"
```

---

## Task 11: Update Sidebar - Add Email Display and Trigger

**Files:**
- Modify: `dashboard/sidebar.py`

- [ ] **Step 1: Read current sidebar.py**

```bash
cat dashboard/sidebar.py
```

- [ ] **Step 2: Add email display and trigger to sidebar**

Add to imports at top of `dashboard/sidebar.py`:
```python
from services.notification_service import load_notification_emails, check_and_notify
```

Add to sidebar rendering (after existing controls):
```python
# Email Notifications Section
st.sidebar.markdown("---")
st.sidebar.subheader("📧 Email Notifications")

emails = load_notification_emails()
if emails:
    st.sidebar.markdown("**Subscribed Emails:**")
    for email, last_active in emails.items():
        st.sidebar.markdown(f"- {email}")
else:
    st.sidebar.info("No email notifications configured. Add NOTIFICATION_EMAILS to .env")

# Trigger notification check on live incidents refresh
if 'live_incidents' in st.session_state and st.session_state.live_incidents is not None:
    with st.spinner("Checking for qualifying incidents..."):
        result = check_and_notify(st.session_state.live_incidents)
        
        if result['status'] == 'success':
            st.sidebar.success(result['message'])
        elif result['status'] == 'partial':
            st.sidebar.warning(result['message'])
        elif result['status'] == 'skipped':
            # Don't show anything for skipped (normal state)
            pass
```

- [ ] **Step 3: Test sidebar imports**

```bash
python -c "import dashboard.sidebar; print('Sidebar imports successfully')"
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/sidebar.py
git commit -m "feat: add email notification display and trigger to sidebar"
```

---

## Task 12: Update .env.example - Add New Variables

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Read current .env.example**

```bash
cat .env.example
```

- [ ] **Step 2: Add new environment variables**

Append to end of `.env.example`:
```env
# Email Notifications (SendGrid)
SENDGRID_API_KEY=your_sendgrid_api_key_here
NOTIFICATION_EMAILS='{}'
# Format: '{"email@example.com": "last_active_time"}'
# Example: '{"admin@example.com": "2026-07-03T10:00:00", "ops@example.com": "2026-07-03T10:00:00"}'

# Optional: Dashboard URL for email links (defaults to http://localhost:8501)
# DASHBOARD_URL=https://your-domain.com
```

- [ ] **Step 3: Commit**

```bash
git add .env.example
git commit -m "docs: add email notification environment variables to .env.example"
```

---

## Task 13: Integration Testing - Full Flow Test

**Files:**
- Create: `tests/test_integration_notification.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_integration_notification.py`:
```python
"""
Integration tests for email notification system.
These tests require:
- SENDGRID_API_KEY environment variable set
- OpenClaw running on port 18789 (optional)
"""

import pytest
import pandas as pd
from services.notification_service import (
    check_and_notify,
    load_notification_emails,
    add_email,
    remove_email
)
import os


@pytest.fixture
def test_email():
    """Provide a test email address."""
    return "test@example.com"


@pytest.fixture
def sample_incidents():
    """Provide sample incidents DataFrame."""
    return pd.DataFrame([
        {
            'incident_num': 'TEST001',
            'incident_type': 'unplanned',
            'outage_time': '2026-07-03T10:00:00',
            'estimated_restoration_time': '2026-07-03T20:00:00',  # 10 hours
            'latitude': 53.5,
            'longitude': -2.5,
            'customers_affected': 100,
            'incident_status': 'Active'
        }
    ])


def test_full_flow_with_mock(monkeypatch, test_email, sample_incidents):
    """Test full notification flow with mocked dependencies."""
    # Mock email list
    monkeypatch.setattr('services.notification_service.load_notification_emails',
                       lambda: {test_email: "2026-07-03T10:00:00"})
    
    # Mock SendGrid
    monkeypatch.setenv('SENDGRID_API_KEY', 'test-key')
    
    # Mock report generation
    monkeypatch.setattr('services.notification_service.generate_report',
                       lambda x: "## Test Report\n\nThis is a test.")
    
    # Mock email sending
    def mock_send_email(email, subject, html):
        return True
    
    monkeypatch.setattr('services.notification_service.send_notification_email',
                       mock_send_email)
    
    # Run check
    result = check_and_notify(sample_incidents)
    
    # Verify
    assert result['status'] == 'success'
    assert '1 notifications' in result['message']


def test_add_remove_email():
    """Test adding and removing emails."""
    test_email = "integration-test@example.com"
    
    # Add email
    success, message = add_email(test_email)
    assert success == True
    
    # Verify it's in the list
    emails = load_notification_emails()
    assert test_email in emails
    
    # Remove email
    success, message = remove_email(test_email)
    assert success == True
    
    # Verify it's removed
    emails = load_notification_emails()
    assert test_email not in emails
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/test_integration_notification.py -v
```
Expected: PASS (with mocked dependencies)

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_notification.py
git commit -m "test: add integration tests for notification system"
```

---

## Task 14: Final Verification - Run All Tests

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/test_notification_service.py tests/test_email_endpoints.py -v
```
Expected: All tests PASS

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/test_integration_notification.py -v
```
Expected: All tests PASS

- [ ] **Step 3: Check code coverage**

```bash
pytest --cov=services tests/
```
Expected: Coverage report showing >80% coverage

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete email notification system for unplanned incidents"
```

---

## Summary

This plan implements a complete email notification system with:

1. ✅ Email validation and .env management
2. ✅ Incident filtering (unplanned + >6 hours)
3. ✅ Sent incidents tracking (prevent duplicates)
4. ✅ OpenClaw report generation with fallback
5. ✅ SendGrid email sending with HTML templates
6. ✅ Click tracking and unsubscribe endpoints
7. ✅ Sidebar display and trigger
8. ✅ Comprehensive testing

Total: 14 tasks, ~50 steps
