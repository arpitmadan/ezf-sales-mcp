#!/usr/bin/env python3
"""
EZFacility Sales MCP Server
Serves reps, managers, AMs, onboarders, and executives.
"""

from dotenv import load_dotenv
load_dotenv()

import os
from mcp.server.fastmcp import FastMCP
from account_timeline import get_summary, get_context, get_single_transcript
from gong_client import _get_all_calls, call_line, find_calls_by_contact_name, get_transcript
from product_gaps import build_report_prompt
from datetime import date, timedelta

mcp = FastMCP("ezf-sales")

SALES_TEAM = ["Shawn Tannenbaum", "Safwan Khan", "Dwayne Larson", "Arpit Madan"]
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "product_gaps")


# ---------------------------------------------------------------------------
# CORE
# ---------------------------------------------------------------------------

@mcp.tool()
def get_account_summary(account_name: str) -> str:
    """
    Fast account overview: deal stage, MRR, contacts, and call list.
    No transcripts — use get_call_transcript or get_full_context for those.
    Start here for any account question.
    """
    return get_summary(account_name)


@mcp.tool()
def get_call_transcript(account_name: str, call_number: int = 1) -> str:
    """
    Full transcript for one call. call_number: 1 = most recent, 2 = second most recent.
    Use get_account_summary first to see how many calls exist.
    """
    return get_single_transcript(account_name, call_number)


@mcp.tool()
def get_full_context(account_name: str) -> str:
    """
    Account summary plus all transcripts. Use for deep analysis,
    handoff briefs, onboarding context, or risk review.
    Slower than get_account_summary — only call when transcripts are needed.
    """
    return get_context(account_name)


@mcp.tool()
def list_recent_calls(days_back: int = 7) -> str:
    """List all Gong calls from the last N days across the team."""
    calls = _get_all_calls(days_back)
    if not calls:
        return f"No calls in the last {days_back} days."
    calls_sorted = sorted(calls, key=lambda c: c.get("started") or "", reverse=True)
    lines = [f"Calls — last {days_back} days ({len(calls)} total)", ""]
    lines += [call_line(c) for c in calls_sorted]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LEAD TOOLS (no Salesforce account required)
# ---------------------------------------------------------------------------

@mcp.tool()
def list_lead_calls(contact_name: str, days_back: int = 30) -> str:
    """
    List Gong calls for a lead or contact who has no Salesforce account yet.
    Searches by attendee name across all calls. Use before get_lead_transcript.
    """
    calls = find_calls_by_contact_name(contact_name, days_back)
    if not calls:
        return f"No calls found with '{contact_name}' as an attendee in the last {days_back} days."
    lines = [f"Calls for '{contact_name}' — last {days_back} days ({len(calls)} total)", ""]
    for i, c in enumerate(reversed(calls), 1):
        lines.append(f"  {i}. {call_line(c)}")
    return "\n".join(lines)


@mcp.tool()
def get_lead_transcript(contact_name: str, call_number: int = 1, days_back: int = 30) -> str:
    """
    Transcript for a lead who has no Salesforce account yet. Searches by attendee name.
    call_number: 1 = most recent. Use list_lead_calls first to see available calls.
    """
    calls = find_calls_by_contact_name(contact_name, days_back)
    if not calls:
        return f"No calls found with '{contact_name}' as an attendee in the last {days_back} days."
    total = len(calls)
    idx = total - call_number
    if idx < 0 or idx >= total:
        return f"Call {call_number} not found. Found {total} call(s) for '{contact_name}'."
    call = calls[idx]
    cid  = call.get("id")
    text = get_transcript(cid) if cid else "(no call ID)"
    return f"## {call_line(call)}\n\n{text}"


# ---------------------------------------------------------------------------
# REP TOOLS
# ---------------------------------------------------------------------------

@mcp.tool()
def get_prep_brief(account_name: str) -> str:
    """
    Pre-call prep for a rep. Shows deal status and the most recent call transcript.
    Use before any follow-up call or 2nd demo.
    """
    summary = get_summary(account_name)
    transcript = get_single_transcript(account_name, call_number=1)
    return f"{summary}\n\n---\n\n## Most Recent Call Transcript\n\n{transcript}"


@mcp.tool()
def get_followup_email(account_name: str) -> str:
    """
    Draft a follow-up email using the latest call transcript and deal context.
    Returns context + instructions for Claude to write the email.
    """
    summary    = get_summary(account_name)
    transcript = get_single_transcript(account_name, call_number=1)

    return f"""{summary}

---

## Latest Call Transcript
{transcript}

---

Write a follow-up email that:
1. References specific things the prospect said (use their words)
2. Addresses any open concerns or questions raised
3. Confirms the agreed next step clearly
4. Matches the tone of the conversation
5. Is concise — no fluff
"""


# ---------------------------------------------------------------------------
# MANAGER / EXEC TOOLS
# ---------------------------------------------------------------------------

@mcp.tool()
def get_deal_risk(account_name: str) -> str:
    """
    Full transcript history with a risk analysis prompt.
    Flags competitors, pricing pushback, stalled momentum, decision-maker issues.
    """
    return get_context(account_name) + """

---

Review the transcripts above and identify:
- Competitor mentions (ClubReady, Mindbody, Jonas, MemberSplash, etc.)
- Pricing objections or budget hesitation
- Stall signals ("need more time", "check with my partner", "not sure on timeline")
- Promises made by the rep that may be hard to fulfill
- Decision-maker gaps (who hasn't been on a call yet?)
- Enthusiasm trend across calls
"""


@mcp.tool()
def get_pipeline_activity(days_back: int = 30) -> str:
    """
    All Gong call activity across the team for the last N days.
    For manager and executive pipeline reviews.
    """
    calls = _get_all_calls(days_back)
    if not calls:
        return f"No calls in the last {days_back} days."

    total_min = sum(round((c.get("duration") or 0) / 60) for c in calls)
    lines = [
        f"Pipeline Activity — last {days_back} days",
        f"{len(calls)} calls  |  {total_min} min total",
        "",
    ]
    lines += [call_line(c) for c in sorted(calls, key=lambda c: c.get("started") or "", reverse=True)]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PRODUCT TEAM TOOLS
# ---------------------------------------------------------------------------

@mcp.tool()
def get_product_gap_report(days_back: int = 7) -> str:
    """
    Scans the sales team's Gong calls from the last N days for moments where
    a missing EZFacility capability blocked a deal. Returns transcripts,
    account value, and industry for every matched call, plus instructions
    for extracting a structured table (account, missing functionality, call
    link, opportunity value, industry, competitor mentioned).

    For Delaney/Priyanka on the product team — after reading the table this
    produces, call save_product_gap_report with the markdown table to persist it.
    """
    return build_report_prompt(SALES_TEAM, days_back)


@mcp.tool()
def save_product_gap_report(markdown_table: str, week_label: str = "") -> str:
    """
    Save the product-gap table (from get_product_gap_report) to a local file
    so it doesn't need to be re-run to look back at a prior week.
    week_label: e.g. "2026-07-16" — defaults to today's date.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    label = week_label or date.today().isoformat()
    path = os.path.join(REPORTS_DIR, f"{label}.md")
    with open(path, "w") as f:
        f.write(markdown_table)
    return f"Saved to {path}"


if __name__ == "__main__":
    mcp.run()
