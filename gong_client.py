#!/usr/bin/env python3
"""
Gong API client with session cache.

Call naming conventions at EZFacility:
  "EZFacility Demonstration"        → 1st demo (no account in title)
  "Meeting with {Rep}"              → 2nd call (no account in title)
  "Call with {Account} - {Contact}" → named call (title-matchable)
  "EZFacility Health Check"         → existing customer

Generic-titled calls are matched by attendee email via the extensive
endpoint, but only for the specific call IDs that need it — no full scan.
"""

import base64
import os
import time
from datetime import datetime, date, timezone, timedelta
from typing import Optional

import requests

BASE_URL        = "https://api.gong.io/v2"
CACHE_TTL       = 1800   # 30 min
CALL_SEARCH_DAYS = 90

GENERIC_TITLES = {
    "ezfacility demonstration", "ezfacility demo", "ezfacility meeting",
    "ezfacility discovery call", "ezfacility health check",
    "ezfacility trial account setup", "sdr booked ezfacility demo",
    "inbound call", "call", "1",
}

# Module-level cache: days_back → (timestamp, calls)
_cache: dict = {}
_users_cache: dict = {}   # {} or {"ts": ..., "users": [...]}


# ---------------------------------------------------------------------------
# Auth + HTTP helpers
# ---------------------------------------------------------------------------

def _auth() -> dict:
    key    = os.environ.get("GONG_ACCESS_KEY", "")
    secret = os.environ.get("GONG_ACCESS_SECRET", "")
    if not key or not secret:
        raise EnvironmentError("GONG_ACCESS_KEY and GONG_ACCESS_SECRET must be set")
    return {"Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode()}


def _get(url, params) -> dict:
    r = requests.get(url, headers=_auth(), params=params, timeout=20)
    if r.status_code == 429:
        time.sleep(10); r = requests.get(url, headers=_auth(), params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def _post(url, payload) -> dict:
    h = {**_auth(), "Content-Type": "application/json"}
    r = requests.post(url, headers=h, json=payload, timeout=30)
    if r.status_code == 429:
        time.sleep(10); r = requests.post(url, headers=h, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Cached call list
# ---------------------------------------------------------------------------

def _get_all_calls(days_back: int = CALL_SEARCH_DAYS) -> list:
    """Return all calls for the past N days. Paginated once, then cached for 30 min."""
    now = time.time()
    if days_back in _cache and now - _cache[days_back][0] < CACHE_TTL:
        return _cache[days_back][1]

    to_dt   = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=days_back)
    calls, cursor = [], None

    while True:
        params = {"fromDateTime": from_dt.isoformat(), "toDateTime": to_dt.isoformat()}
        if cursor:
            params["cursor"] = cursor
        data   = _get(f"{BASE_URL}/calls", params)
        calls.extend(data.get("calls", []))
        cursor = data.get("records", {}).get("cursor")
        if not cursor:
            break

    _cache[days_back] = (now, calls)
    return calls


# ---------------------------------------------------------------------------
# Rep-based lookup (for team-wide sweeps, not tied to one account)
# ---------------------------------------------------------------------------

def _get_users() -> list:
    """Gong workspace users, cached for the process lifetime — this list barely changes."""
    if not _users_cache:
        _users_cache["users"] = _get(f"{BASE_URL}/users", {}).get("users", [])
    return _users_cache["users"]


def resolve_rep_ids(rep_names: list) -> dict:
    """Map rep full names (e.g. 'Shawn Tannenbaum') to their Gong primaryUserId."""
    users = _get_users()
    by_name = {
        f"{u.get('firstName', '')} {u.get('lastName', '')}".strip().lower(): u.get("id")
        for u in users
    }
    return {name: by_name.get(name.lower()) for name in rep_names}


def get_calls_for_reps(rep_names: list, days_back: int = 7) -> list:
    """All calls in the window where one of the given reps was the primary (host) user."""
    ids = {uid for uid in resolve_rep_ids(rep_names).values() if uid}
    all_calls = _get_all_calls(days_back)
    matched = [c for c in all_calls if c.get("primaryUserId") in ids]
    return sorted(matched, key=lambda c: c.get("started") or "")


# ---------------------------------------------------------------------------
# CRM context (Salesforce Account/Opportunity linked to a call by Gong's
# native SF integration — far more reliable than title/email matching)
# ---------------------------------------------------------------------------

def get_crm_context_bulk(call_ids: list) -> dict:
    """
    Fetch Salesforce Account/Opportunity IDs + names linked to each call, plus
    external attendee emails. Gong's own SF sync only links calls to an
    Account/Opportunity — a call with a Lead that never converted (no
    Account/Opportunity exists yet) comes back with empty context, so
    external_emails is included to let callers fall back to a direct Lead
    lookup in Salesforce for those.
    Returns {call_id: {"account_id", "account_name", "opportunity_id",
    "opportunity_name", "external_emails", "external_names"}}.
    """
    if not call_ids:
        return {}
    result = {}
    for i in range(0, len(call_ids), 50):
        chunk = call_ids[i:i + 50]
        data = _post(f"{BASE_URL}/calls/extensive", {
            "filter": {"callIds": chunk},
            "contentSelector": {"context": "Extended", "exposedFields": {"parties": True}},
        })
        for call in data.get("calls", []):
            cid = (call.get("metaData") or {}).get("id")
            entry = {"account_id": None, "account_name": None,
                     "opportunity_id": None, "opportunity_name": None,
                     "external_emails": [], "external_names": []}
            for system in (call.get("context") or []):
                if system.get("system") != "Salesforce":
                    continue
                for obj in system.get("objects", []):
                    fields = {f["name"]: f.get("value") for f in (obj.get("fields") or [])}
                    if obj.get("objectType") == "Account":
                        entry["account_id"] = obj.get("objectId")
                        entry["account_name"] = fields.get("Name")
                    elif obj.get("objectType") == "Opportunity":
                        entry["opportunity_id"] = obj.get("objectId")
                        entry["opportunity_name"] = fields.get("Name")
            for party in (call.get("parties") or []):
                if party.get("affiliation") == "External":
                    if party.get("emailAddress"):
                        entry["external_emails"].append(party["emailAddress"])
                    if party.get("name"):
                        entry["external_names"].append(party["name"])
            result[cid] = entry
    return result


# ---------------------------------------------------------------------------
# Account matching
# ---------------------------------------------------------------------------

def find_calls(account_name: str, contact_emails: list = None,
               days_back: int = CALL_SEARCH_DAYS) -> list:
    """
    Find all Gong calls for an account.
    1. Title match from cached call list (instant after first run).
    2. Email match — targeted extensive fetch for generic-titled calls only.
    """
    all_calls     = _get_all_calls(days_back)
    title_matched = _match_by_title(all_calls, account_name)
    title_ids     = {c["id"] for c in title_matched}

    email_matched = []
    if contact_emails:
        # Only check generic-titled calls — avoids re-scanning named calls
        generic_ids = [
            c["id"] for c in all_calls
            if c.get("id") not in title_ids and _is_generic(c.get("title", ""))
        ]
        if generic_ids:
            email_matched = _email_match(generic_ids, contact_emails)

    combined = title_matched + email_matched
    return sorted(combined, key=lambda c: c.get("started") or "")


def _match_by_title(calls: list, account_name: str) -> list:
    name = account_name.lower()
    for s in [" llc", " inc", " corp", ", inc", ", llc", " ltd"]:
        name = name.replace(s, "")
    name = name.strip()
    return [
        c for c in calls
        if not _is_generic(c.get("title", ""))
        and name in (c.get("title") or "").lower()
    ]


def _email_match(call_ids: list, contact_emails: list) -> list:
    """Fetch extensive data for specific call IDs and match by attendee email."""
    emails  = {e.lower() for e in contact_emails if e}
    matched = []
    # Batch in chunks of 50 to stay within API limits
    for i in range(0, len(call_ids), 50):
        chunk = call_ids[i:i + 50]
        data  = _post(f"{BASE_URL}/calls/extensive", {
            "filter":          {"callIds": chunk},
            "contentSelector": {"context": "Extended", "exposedFields": {"parties": True}},
        })
        for call in data.get("calls", []):
            for party in (call.get("parties") or []):
                if (party.get("emailAddress") or "").lower() in emails:
                    matched.append(_normalize(call))
                    break
    return matched


def _normalize(call: dict) -> dict:
    """Flatten an extensive-endpoint call to the same shape as a basic call."""
    meta = call.get("metaData") or {}
    return {
        "id":       meta.get("id"),
        "title":    meta.get("title"),
        "started":  meta.get("started"),
        "duration": meta.get("duration"),
        "parties":  call.get("parties") or [],
        "url":      meta.get("url"),
    }


def _is_generic(title: str) -> bool:
    t = (title or "").lower().strip()
    return t in GENERIC_TITLES or t.startswith("meeting with") or t.startswith("sdr booked")


def find_calls_by_contact_name(contact_name: str,
                                days_back: int = CALL_SEARCH_DAYS) -> list:
    """
    Find calls by attendee name — for leads without a Salesforce account.
    Title-matches first, then scans all remaining calls via the extensive
    endpoint for a matching party name.
    """
    all_calls  = _get_all_calls(days_back)
    name_lower = contact_name.lower().strip()

    title_matched = [
        c for c in all_calls
        if name_lower in (c.get("title") or "").lower()
    ]
    title_ids = {c["id"] for c in title_matched}

    remaining_ids = [c["id"] for c in all_calls if c.get("id") not in title_ids]
    name_matched  = _name_match(remaining_ids, name_lower)

    combined = title_matched + name_matched
    return sorted(combined, key=lambda c: c.get("started") or "")


def _name_match(call_ids: list, name_lower: str) -> list:
    """Fetch extensive data for call IDs and match by attendee name."""
    matched = []
    for i in range(0, len(call_ids), 50):
        chunk = call_ids[i:i + 50]
        data  = _post(f"{BASE_URL}/calls/extensive", {
            "filter":          {"callIds": chunk},
            "contentSelector": {"context": "Extended", "exposedFields": {"parties": True}},
        })
        for call in data.get("calls", []):
            for party in (call.get("parties") or []):
                if name_lower in (party.get("name") or "").lower():
                    matched.append(_normalize(call))
                    break
    return matched


# ---------------------------------------------------------------------------
# Transcripts (lazy — fetch only what you need)
# ---------------------------------------------------------------------------

def get_transcript(call_id: str) -> str:
    """Fetch and format the transcript for a single call."""
    data = _post(f"{BASE_URL}/calls/transcript", {"filter": {"callIds": [call_id]}})
    records = data.get("callTranscripts", [])
    return _format_transcript(records[0]) if records else "(transcript not available)"


def get_transcripts_bulk(call_ids: list) -> dict:
    """Fetch transcripts for multiple calls. Returns {call_id: formatted_text}."""
    if not call_ids:
        return {}
    data    = _post(f"{BASE_URL}/calls/transcript", {"filter": {"callIds": call_ids}})
    return {t["callId"]: _format_transcript(t) for t in data.get("callTranscripts", [])}


def _format_transcript(t: dict) -> str:
    lines = []
    for s in (t.get("transcript") or []):
        text = " ".join(x.get("text", "") for x in (s.get("sentences") or []))
        if text.strip():
            lines.append(f"{s.get('speakerName', 'Unknown')}: {text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def call_line(call: dict) -> str:
    """Single-line call summary."""
    mins = round((call.get("duration") or 0) / 60)
    date = (call.get("started") or "")[:10]
    return f"{date}  |  {call.get('title') or 'Untitled'}  |  {mins} min"
