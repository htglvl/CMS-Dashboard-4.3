# Email Notification System for Unplanned Incidents

**Date:** 2026-07-03  
**Status:** Draft  
**Author:** ZCode  

## Overview

Add an email notification system to the CMS Dashboard that automatically alerts subscribed email addresses when a qualifying live incident is detected. The system uses SendGrid for email delivery and OpenClaw for generating intelligent incident reports.

## Requirements

### Functional Requirements

1. **Email Management**
   - Store notification emails in `.env` as serialized JSON
   - Format: `{"email@example.com": "last_active_time"}`
   - Sidebar UI displays current email list
   - Click tracking updates `last_active_time`
   - Unsubscribe removes email from `.env`

2. **Incident Detection**
   - Trigger on live incidents refresh (existing mechanism)
   - Filter conditions:
     - `incident_type == "unplanned"`
     - Estimated duration > 6 hours
   - Track sent incidents to prevent duplicates

3. **Report Generation**
   - Call OpenClaw LLM API (port 18789) for each qualifying incident
   - Report includes:
     - Location (place name via reverse geocoding, NOT lat/long)
     - Estimated duration
     - Nearby chargepoints (top 3)
     - Chargepoint types
     - Recommended actions

4. **Email Delivery**
   - Use SendGrid API (key-based auth, no login)
   - HTML formatted emails
   - Include click tracking links
   - Include unsubscribe link

### Non-Functional Requirements

- **Reliability:** Retry once on SendGrid failure
- **Performance:** Don't block UI during email sending
- **Logging:** All errors logged to `logs/notification.log`
- **User Feedback:** Toast notifications for success/failure

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Streamlit Dashboard                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  sidebar.py                                               │  │
│  │  - Display email list from .env                           │  │
│  │  - Trigger check on live incidents refresh                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  services/notification_service.py                         │  │
│  │  1. Filter: unplanned + >6 hours                         │  │
│  │  2. Call OpenClaw API for report                          │  │
│  │  3. Send email via SendGrid                               │  │
│  │  4. Track sent incidents                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  services/email_endpoints.py                              │  │
│  │  - /email/click/<id> - Update active time                 │  │
│  │  - /email/unsubscribe/<email> - Remove from .env          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. New Files

#### `services/__init__.py`
Empty package init file.

#### `services/notification_service.py`
Core notification logic:

```python
# Key functions:
def check_and_notify():
    """Main entry point - called from sidebar on refresh"""
    
def filter_qualifying_incidents(incidents_df) -> list:
    """Filter for unplanned incidents >6 hours"""
    
def generate_report(incident) -> str:
    """Call OpenClaw API to generate incident report"""
    
def send_notification(email: str, report: str, incident_id: str):
    """Send email via SendGrid"""
    
def track_sent_incident(incident_id: str):
    """Record that notification was sent"""
```

#### `services/email_endpoints.py`
Flask endpoints for email tracking:

```python
# Endpoints:
@app.route('/email/click/<incident_id>/<email>')
def track_click(incident_id, email):
    """Update last_active_time for email"""
    
@app.route('/email/unsubscribe/<email>')
def unsubscribe(email):
    """Remove email from .env NOTIFICATION_EMAILS"""
```

### 2. Modified Files

#### `dashboard/sidebar.py`
Add to sidebar:
- Display list of notification emails (read-only)
- Call `check_and_notify()` on live incidents refresh

#### `.env.example`
Add:
```env
SENDGRID_API_KEY=your_sendgrid_api_key_here
NOTIFICATION_EMAILS='{}'
```

#### `requirements.txt`
Add:
```
sendgrid>=6.9.0
flask>=2.0.0
```

#### `proxy_server.py`
Add routes for email endpoints (port 8501).

## Data Flow

### Incident Detection & Notification

```
1. Live incidents refresh triggers check_and_notify()

2. Load NOTIFICATION_EMAILS from .env
   - If empty or SENDGRID_API_KEY not set, skip

3. Fetch live incidents (existing mechanism)

4. Filter qualifying incidents:
   - incident_type == "unplanned"
   - estimated_restoration_time - outage_time > 6 hours

5. Load sent incidents from data/.sent_incidents
   - Skip already-sent incidents

6. For each new qualifying incident:
   a. Generate report via OpenClaw API:
      - Prompt: "Generate incident report with:
        * Location (reverse geocode lat/long)
        * Estimated duration
        * Nearby chargepoints (top 3 with types)
        * Recommended actions"
      
   b. For each email in NOTIFICATION_EMAILS:
      - Construct HTML email with report
      - Add click tracking link: /email/click/{incident_id}/{email}
      - Add unsubscribe link: /email/unsubscribe/{email}
      - Send via SendGrid API
      
   c. Track incident as sent in data/.sent_incidents

7. Show success/failure toast in sidebar
```

### Email Click Tracking

```
1. User clicks link in email
2. GET /email/click/{incident_id}/{email}
3. Load NOTIFICATION_EMAILS from .env
4. Update last_active_time for email
5. Save back to .env
6. Redirect to dashboard
```

### Unsubscribe

```
1. User clicks unsubscribe link
2. GET /email/unsubscribe/{email}
3. Load NOTIFICATION_EMAILS from .env
4. Remove email key
5. Save back to .env
6. Show confirmation page
```

## Error Handling

### Email Sending Failures
- Log error to `logs/notification.log`
- Retry once after 5 seconds
- Show warning toast: "Failed to send notification to {email}"
- Continue processing other emails

### OpenClaw API Failures
- Timeout after 30 seconds
- Fall back to basic report (without LLM analysis):
  ```
  Incident: {incident_num}
  Type: Unplanned
  Location: {lat}, {long}
  Duration: {hours} hours
  Status: {status}
  ```
- Log error: "OpenClaw API timeout, using fallback report"

### Missing Configuration
- If `SENDGRID_API_KEY` not set:
  - Log: "SENDGRID_API_KEY not configured, skipping notifications"
  - Skip silently (no toast)
  
- If `NOTIFICATION_EMAILS` empty:
  - Log: "No notification emails configured"
  - Skip silently (no toast)

### Duplicate Prevention
- Store sent incidents in `data/.sent_incidents` (JSON):
  ```json
  {
    "incident_123": "2026-07-03T10:00:00",
    "incident_456": "2026-07-03T11:00:00"
  }
  ```
- Clear entries older than 24 hours on each check

## Email Template

### Subject
```
[Alert] Unplanned Incident: {incident_num} - {place_name}
```

### Body (HTML)
```html
<h2>Unplanned Power Incident Alert</h2>

<p><strong>Incident ID:</strong> {incident_num}</p>
<p><strong>Location:</strong> {place_name}</p>
<p><strong>Reported:</strong> {outage_time}</p>
<p><strong>Estimated Duration:</strong> {duration} hours</p>
<p><strong>Customers Affected:</strong> {customers_affected}</p>
<p><strong>Status:</strong> {incident_status}</p>

<h3>Nearby Chargepoints</h3>
<ul>
  {for each chargepoint}
  <li>{name} - {type} ({distance}km away)</li>
</ul>

<h3>Recommended Actions</h3>
<p>{actions from OpenClaw report}</p>

<hr>
<p><small>
  <a href="{base_url}/email/click/{incident_id}/{email}">View in Dashboard</a> |
  <a href="{base_url}/email/unsubscribe/{email}">Unsubscribe</a>
</small></p>
```

## Dependencies

### Python Packages
- `sendgrid>=6.9.0` - SendGrid API client
- `flask>=2.0.0` - Web framework for endpoints

### External Services
- **SendGrid Account** - For email delivery
  - Free tier: 100 emails/day
  - Requires API key
  
- **OpenClaw Gateway** - For report generation
  - Running on port 18789
  - Must have access to tools: geocode, query_charging_sites, query_outages

## Testing

### Unit Tests
1. `test_filter_qualifying_incidents()` - Test incident filtering logic
2. `test_generate_report()` - Test OpenClaw API call with mock
3. `test_send_notification()` - Test SendGrid API call with mock
4. `test_track_sent_incident()` - Test incident tracking

### Integration Tests
1. Test full flow with real SendGrid (test email)
2. Test click tracking endpoint
3. Test unsubscribe endpoint

### Manual Testing
1. Configure test email in `.env`
2. Create mock unplanned incident >6 hours
3. Verify email received with correct report
4. Click tracking link, verify active time updated
5. Click unsubscribe, verify email removed from `.env`

## Resolved Questions

1. **Base URL for links:** Use `http://localhost:8501` for development. For production, read from `DASHBOARD_URL` env var (defaults to localhost if not set).
2. **Rate limiting:** No rate limiting for now - one email per incident per email address. Track in `data/.sent_incidents` to prevent duplicates.
3. **Email validation:** Yes, validate email format using regex before adding to `.env`. Show error toast if invalid.

## Success Criteria

1. ✅ Email stored in `.env` as JSON
2. ✅ Unplanned incidents >6 hours trigger email
3. ✅ OpenClaw generates report with place name (not lat/long)
4. ✅ Email includes nearby chargepoints and actions
5. ✅ Click tracking updates active time
6. ✅ Unsubscribe removes email from `.env`
7. ✅ Errors logged and user notified via toast
