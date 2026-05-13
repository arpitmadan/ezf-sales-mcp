#!/usr/bin/env python3
"""
Gong API client.
Requires GONG_ACCESS_KEY and GONG_ACCESS_SECRET in environment.

EZFacility call naming conventions:
  "EZFacility Demonstration"        → 1st demo (no account in title)
  "EZFacility Demo"                 → 1st demo variant
  "EZFacility Discovery Call"       → SDR / discovery
  "Meeting with {Rep}"              → 2nd call (no account in title)
  "EZFacility Meeting"              → 2nd call variant
  "Call with {Account} - {Contact}" → any named call (matchable by title)
  "EZFacility Health Check"         → existing customer

Generic titles ("EZFacility Demonstration", "Meeting with {Rep}") require
email-based matching via the extensive API endpoint.
"""

import base64
import os
import time
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import requests

BASE_URL = "https://api.gong.io/v2"
CALL_SEARCH_DAYS = 180
RATE_LIMIT_BACKOFF = 10

# Titles that never contain account info — must match by attendee email
GENERIC_TITLES = {
    "ezfacility demonstration",
    "ezfacility demo",
    "ezfacility meeting",
    "ezfacility discovery call",
    "ezfacility health check",
    "ezfacility trial account setup",
    "sdr booked ezfacility demo",
    "inbound call",
    "call",
    "1",
}


def _auth() -> dict:
    key = os.environ.get("GONG_ACCESS_KEY", "")
    secret = os.environ.get("GONG_ACCESS_SECRET", "")
    if not key or not secret:
        raise EnvironmentError("GONG_ACCESS_KEY and GONG_ACCESS_SECRET must be set in .env")
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _post_with_retry(url, headers, payload, timeout=30) -> dict:
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code == 429:
        time.sleep(RATE_LIMIT_BACKOFF)
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _get_with_retry(url, headers, params, timeout=20) -> dict:
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    if resp.status_code == 429:
        time.sleep(RATE_LIMIT_BACKOFF)
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def get_calls_in_range(from_date, to_date) -> list:
    """Return calls between two date objects, paginating with backoff."""
    from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    to_dt   = datetime.combine(to_date,   datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)

    calls, cursor = [], None
    while True:
        params = {"fromDateTime": from_dt.isoformat(), "toDateTime": to_dt.isoformat()}
        if cursor:
            params["cursor"] = cursor
        data   = _get_with_retry(f"{BASE_URL}/calls", _auth(), params)
        calls.extend(data.get("calls", []))
        cursor = data.get("records", {}).get("cursor")
        if not cursor:
            break
    return calls


def get_calls_extensive_by_emails(contact_emails: list, from_date, to_date) -> list:
    """
    Use the extensive endpoint to find calls where any attendee matches
    one of the contact_emails. Paginates fully.
    Returns calls normalized to the same structure as get_calls_in_range.
    """
    if not contact_emails:
        return []

    from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    to_dt   = datetime.combine(to_date,   datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)
    emails  = {e.lower() for e in contact_emails if e}

    headers = {**_auth(), "Content-Type": "application/json"}
    calls, cursor = [], None

    while True:
        payload = {
            "filter": {
                "fromDateTime": from_dt.isoformat(),
                "toDateTime":   to_dt.isoformat(),
            },
            "contentSelector": {
                "context": "Extended",
                "exposedFields": {"parties": True},
            },
        }
        if cursor:
            payload["cursor"] = cursor

        data = _post_with_retry(f"{BASE_URL}/calls/extensive", headers, payload)

        for call in data.get("calls", []):
            for party in (call.get("parties") or []):
                if (party.get("emailAddress") or "").lower() in emails:
                    calls.append(_normalize_extensive_call(call))
                    break

        cursor = data.get("records", {}).get("cursor")
        if not cursor:
            break

    return calls


def _normalize_extensive_call(call: dict) -> dict:
    """
    Flatten an extensive-endpoint call into the same shape as a basic call.
    metaData fields → top-level; parties stay; sf_account_name extracted from context.
    """
    meta    = call.get("metaData") or {}
    parties = call.get("parties") or []

    # Extract SF account name from context if available
    sf_account = None
    for obj in (call.get("context") or []):
        for sf_obj in (obj.get("objects") or []):
            if sf_obj.get("objectType") == "Account":
                for field in (sf_obj.get("fields") or []):
                    if field.get("name") == "Name":
                        sf_account = field.get("value")

    return {
        "id":           meta.get("id"),
        "title":        meta.get("title"),
        "started":      meta.get("started"),
        "duration":     meta.get("duration"),
        "parties":      parties,
        "sf_account":   sf_account,
        "url":          meta.get("url"),
    }


def get_calls_for_account(
    account_name: str,
    contact_emails: list = None,
    days_back: int = CALL_SEARCH_DAYS,
) -> list:
    """
    Return all Gong calls for an account.

    Strategy:
    1. Title match — catches "Call with {Account} - {Contact}" format
    2. Email match — catches generic "EZFacility Demonstration" / "Meeting with {Rep}"
       calls where the prospect attended but the title has no account name
    """
    to_date   = date.today()
    from_date = to_date - timedelta(days=days_back)

    all_calls     = get_calls_in_range(from_date, to_date)
    title_matched = _filter_by_title(all_calls, account_name)
    title_ids     = {c.get("id") for c in title_matched}

    email_matched = []
    if contact_emails:
        raw_email_calls = get_calls_extensive_by_emails(contact_emails, from_date, to_date)
        # deduplicate against title matches
        email_matched = [c for c in raw_email_calls if c.get("id") not in title_ids]

    combined = title_matched + email_matched
    return sorted(combined, key=lambda c: c.get("started") or "")


def get_transcripts(call_ids: list) -> list:
    """Return transcript dicts for the given call IDs."""
    if not call_ids:
        return []
    resp = requests.post(
        f"{BASE_URL}/calls/transcript",
        headers={**_auth(), "Content-Type": "application/json"},
        json={"filter": {"callIds": call_ids}},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("callTranscripts", [])


def _filter_by_title(calls: list, account_name: str) -> list:
    """Match calls where the title contains the account name."""
    name = account_name.lower()
    for suffix in [" llc", " inc", " corp", ", inc", ", llc", " ltd"]:
        name = name.replace(suffix, "")
    name = name.strip()

    matched = []
    for call in calls:
        title = (call.get("title") or "").lower().strip()
        # skip generic titles — email matching handles those
        if title in GENERIC_TITLES or title.startswith("meeting with"):
            continue
        if name in title:
            matched.append(call)
    return matched


def _is_generic_title(title: str) -> bool:
    t = (title or "").lower().strip()
    return t in GENERIC_TITLES or t.startswith("meeting with") or t.startswith("sdr booked")


def format_transcript(transcript_data: dict, max_chars: Optional[int] = None) -> str:
    """Convert a Gong transcript dict into 'Speaker: text' lines."""
    lines = []
    for sentence in (transcript_data.get("transcript") or []):
        speaker = sentence.get("speakerName", "Unknown")
        text    = " ".join(s.get("text", "") for s in (sentence.get("sentences") or []))
        if text.strip():
            lines.append(f"{speaker}: {text}")

    full = "\n".join(lines)
    if max_chars and len(full) > max_chars:
        return full[:max_chars] + "\n[... transcript truncated ...]"
    return full


def call_summary_line(call: dict) -> str:
    """One-line summary of a call for timeline display."""
    title    = call.get("title") or "Untitled"
    started  = call.get("started") or ""
    duration = call.get("duration") or 0
    minutes  = round(duration / 60)
    date_str = started[:10] if started else "unknown date"
    return f"{date_str}  |  {title}  |  {minutes} min"
