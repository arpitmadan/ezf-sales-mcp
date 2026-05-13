#!/usr/bin/env python3
"""
account_timeline.py

Two modes:
  get_summary()  — fast, compact, no transcripts (~200 tokens)
  get_context()  — full transcripts for deep analysis
"""

from gong_client import find_calls, get_transcripts_bulk, get_transcript, call_line
from salesforce_client import build_deal_context


def get_summary(account_name: str) -> str:
    """
    Fast account overview: SF deal + call list. No transcripts.
    Use this first — ask for transcripts only if needed.
    """
    sf   = build_deal_context(account_name)
    contacts = sf.get("contacts", [])
    calls    = find_calls(
        account_name,
        contact_emails=[c.get("Email") for c in contacts if c.get("Email")]
    )

    lines = [f"# {account_name}", ""]

    # Opportunities
    all_opps = sf.get("all_opportunities", [])
    if all_opps:
        for o in all_opps:
            mrr   = o.get("Monthly_Total__c") or 0
            stage = o.get("StageName", "Unknown")
            owner = (o.get("Owner") or {}).get("Name", "")
            close = o.get("CloseDate", "")
            name  = o.get("Name", "")
            lines.append(f"{name}  |  {stage}  |  ${mrr:.0f}/mo  |  Close {close}  |  {owner}")
    else:
        lines.append(sf.get("error") or "No opportunities found.")

    # Contacts
    if contacts:
        lines.append("")
        lines.append("Contacts: " + "  |  ".join(
            f"{c.get('Name')} ({c.get('Title') or 'no title'})  {c.get('Email') or ''}"
            for c in contacts
        ))

    # Calls
    lines.append("")
    lines.append(f"Calls ({len(calls)}):")
    if calls:
        for i, c in enumerate(reversed(calls), 1):
            lines.append(f"  {i}. {call_line(c)}")
    else:
        lines.append("  No calls found.")

    return "\n".join(lines)


def get_context(account_name: str, call_indices: list = None) -> str:
    """
    Full context with transcripts. Fetches all transcripts unless
    call_indices is specified (1-based, 1 = most recent).
    """
    sf       = build_deal_context(account_name)
    contacts = sf.get("contacts", [])
    calls    = find_calls(
        account_name,
        contact_emails=[c.get("Email") for c in contacts if c.get("Email")]
    )

    if call_indices:
        # Convert 1-based (most-recent-first) to list index
        total   = len(calls)
        indices = [total - i for i in call_indices if 1 <= i <= total]
        selected = [calls[i] for i in indices]
    else:
        selected = calls

    call_ids     = [c["id"] for c in selected if c.get("id")]
    transcripts  = get_transcripts_bulk(call_ids)

    lines = [get_summary(account_name), "", "---", ""]

    for c in selected:
        cid  = c.get("id")
        text = transcripts.get(cid, "(transcript not available)")
        lines.append(f"## {call_line(c)}")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def get_single_transcript(account_name: str, call_index: int = 1) -> str:
    """
    Return one transcript by index (1 = most recent).
    Lightweight — only fetches the one call needed.
    """
    sf       = build_deal_context(account_name)
    contacts = sf.get("contacts", [])
    calls    = find_calls(
        account_name,
        contact_emails=[c.get("Email") for c in contacts if c.get("Email")]
    )

    if not calls:
        return f"No calls found for '{account_name}'."

    total = len(calls)
    idx   = total - call_index
    if idx < 0 or idx >= total:
        return f"Call {call_index} not found. This account has {total} call(s)."

    call = calls[idx]
    cid  = call.get("id")
    text = get_transcript(cid) if cid else "(no call ID)"

    return f"## {call_line(call)}\n\n{text}"
