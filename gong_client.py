#!/usr/bin/env python3
"""
Gong API client.
Requires GONG_ACCESS_KEY and GONG_ACCESS_SECRET in environment.
"""

import base64
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests

BASE_URL = "https://api.gong.io/v2"
CALL_SEARCH_DAYS = 730  # look back 2 years when searching by account


def _auth() -> dict:
    key = os.environ.get("GONG_ACCESS_KEY", "")
    secret = os.environ.get("GONG_ACCESS_SECRET", "")
    if not key or not secret:
        raise EnvironmentError("GONG_ACCESS_KEY and GONG_ACCESS_SECRET must be set in .env")
    token = base64.b64encode(f"{key}:{secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def get_calls_in_range(from_date, to_date) -> list:
    """Return calls (with party info) between two date objects."""
    from_dt = datetime.combine(from_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    to_dt   = datetime.combine(to_date,   datetime.min.time()).replace(tzinfo=timezone.utc) + timedelta(days=1)

    calls = []
    cursor = None

    while True:
        params = {
            "fromDateTime": from_dt.isoformat(),
            "toDateTime":   to_dt.isoformat(),
        }
        if cursor:
            params["cursor"] = cursor

        resp = requests.get(f"{BASE_URL}/calls", headers=_auth(), params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        calls.extend(data.get("calls", []))

        cursor = data.get("records", {}).get("cursor")
        if not cursor:
            break

    return calls


def get_calls_for_account(account_name: str) -> list:
    """Return all calls matching account_name over the past 2 years."""
    from datetime import date
    to_date   = date.today()
    from_date = to_date - timedelta(days=CALL_SEARCH_DAYS)
    all_calls = get_calls_in_range(from_date, to_date)
    return _filter_by_account(all_calls, account_name)


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


def _filter_by_account(calls: list, account_name: str) -> list:
    """Filter calls by partial account name match on title or party affiliation."""
    name = account_name.lower()
    for suffix in [" llc", " inc", " corp", ", inc", ", llc", " ltd"]:
        name = name.replace(suffix, "")
    name = name.strip()

    matched = []
    for call in calls:
        title = (call.get("title") or "").lower()
        if name in title:
            matched.append(call)
            continue
        for party in (call.get("parties") or []):
            affiliation = (party.get("affiliation") or "").lower()
            if name in affiliation or affiliation in name:
                matched.append(call)
                break
    return matched


def format_transcript(transcript_data: dict, max_chars: Optional[int] = None) -> str:
    """Convert a Gong transcript dict into 'Speaker: text' lines."""
    lines = []
    for sentence in (transcript_data.get("transcript") or []):
        speaker = sentence.get("speakerName", "Unknown")
        text = " ".join(s.get("text", "") for s in (sentence.get("sentences") or []))
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
