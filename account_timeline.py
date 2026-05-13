#!/usr/bin/env python3
"""
account_timeline.py — core module.
Builds a full deal history for an account by combining Gong transcripts
and Salesforce opportunity data into one structured object.
"""

from gong_client import (
    get_calls_for_account,
    get_transcripts,
    format_transcript,
    call_summary_line,
)
from salesforce_client import build_deal_context


def build_timeline(account_name: str) -> dict:
    """
    Return everything known about an account:
      - All Gong calls (chronological) with full transcripts
      - SF opportunity, stage history, contacts, recent tasks

    Uses SF contact emails to match generic-titled Gong calls
    ("EZFacility Demonstration", "Meeting with {Rep}", etc).
    """
    sf_context = build_deal_context(account_name)
    contact_emails = [
        c.get("Email") for c in sf_context.get("contacts", []) if c.get("Email")
    ]

    calls = get_calls_for_account(account_name, contact_emails=contact_emails)
    calls_sorted = sorted(calls, key=lambda c: c.get("started") or "")

    call_ids = [c["id"] for c in calls_sorted if c.get("id")]
    transcripts_raw = get_transcripts(call_ids)
    transcript_map = {t["callId"]: t for t in transcripts_raw}

    enriched_calls = []
    for call in calls_sorted:
        cid = call.get("id")
        transcript_text = ""
        if cid and cid in transcript_map:
            transcript_text = format_transcript(transcript_map[cid])
        enriched_calls.append({
            "id":         cid,
            "title":      call.get("title") or "Untitled",
            "date":       (call.get("started") or "")[:10],
            "duration_min": round((call.get("duration") or 0) / 60),
            "rep":        _primary_rep(call),
            "summary":    call_summary_line(call),
            "transcript": transcript_text,
        })

    return {
        "account_name": account_name,
        "call_count":   len(enriched_calls),
        "calls":        enriched_calls,
        "sf":           sf_context,
    }


def format_timeline_for_claude(timeline: dict) -> str:
    """
    Render a timeline dict as clean text ready to pass to Claude.
    Includes full transcripts so Claude has maximum context.
    """
    acct = timeline["account_name"]
    sf   = timeline["sf"]
    opp  = sf.get("opportunity") or {}

    lines = []
    lines.append(f"# Account: {acct}")
    lines.append("")

    # SF deal context
    all_opps = sf.get("all_opportunities", [])
    if all_opps:
        lines.append("## Salesforce Opportunities")
        for o in all_opps:
            mrr   = o.get("Monthly_Total__c") or 0
            stage = o.get("StageName", "Unknown")
            name  = o.get("Name", "Unknown")
            close = o.get("CloseDate", "")
            owner = (o.get("Owner") or {}).get("Name", "Unknown")
            lines.append(f"  [{name}]  Stage: {stage}  |  MRR: ${mrr:.0f}/mo  |  Close: {close}  |  {owner}")
    elif opp:
        lines.append("## Salesforce Deal")
        lines.append(f"  Stage:    {opp.get('StageName', 'Unknown')}")
        lines.append(f"  MRR:      ${opp.get('Monthly_Total__c') or 0:.0f}/mo")
        lines.append(f"  Close:    {opp.get('CloseDate', 'Unknown')}")
        lines.append(f"  Owner:    {(opp.get('Owner') or {}).get('Name', 'Unknown')}")
    else:
        if sf.get("error"):
            lines.append(f"## Salesforce  (unavailable: {sf['error']})")
        else:
            lines.append("## Salesforce  (no opportunity found)")

    if opp:
        history = sf.get("stage_history", [])
        if history:
            lines.append(f"  Stage History ({opp.get('Name', 'primary opp')}):")
            for h in history:
                lines.append(f"    {h.get('CreatedDate', '')[:10]}  →  {h.get('StageName')}")

    contacts = sf.get("contacts", [])
    if contacts:
        lines.append("")
        lines.append("## Key Contacts")
        for c in contacts:
            lines.append(f"  {c.get('Name')}  |  {c.get('Title') or 'No title'}  |  {c.get('Email') or ''}")

    # Gong call history
    lines.append("")
    lines.append(f"## Gong Call History  ({timeline['call_count']} calls)")

    if not timeline["calls"]:
        lines.append("  No calls found for this account.")
    else:
        for i, call in enumerate(timeline["calls"], 1):
            lines.append("")
            lines.append(f"### Call {i}  —  {call['date']}  |  {call['title']}  |  {call['duration_min']} min  |  {call['rep']}")
            if call["transcript"]:
                lines.append("")
                lines.append(call["transcript"])
            else:
                lines.append("  (transcript not available)")

    return "\n".join(lines)


def _primary_rep(call: dict) -> str:
    """Return the internal (EZFacility) participant's name from a call."""
    for party in (call.get("parties") or []):
        if party.get("affiliation", "").lower() in ("ezfacility", "internal", ""):
            name = party.get("name") or party.get("emailAddress") or ""
            if name:
                return name
    return "Unknown"
