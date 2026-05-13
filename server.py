#!/usr/bin/env python3
"""
EZFacility Sales MCP Server
Exposes Gong call transcripts and deal intelligence to Claude Desktop.

Roles served:
  - Sales reps     : prep briefs, follow-up email drafts
  - Sales manager  : risk signals, rep activity, pipeline view
  - CEO (Miranda)  : cross-account patterns and pipeline health
  - Account managers: full handoff briefs
  - Onboarders     : why they bought, what was promised
"""

from dotenv import load_dotenv
load_dotenv()

from mcp.server.fastmcp import FastMCP
from account_timeline import build_timeline, format_timeline_for_claude
from gong_client import get_calls_in_range, call_summary_line
from datetime import date, timedelta

mcp = FastMCP("ezf-sales")


# =============================================================================
# CORE — available to all roles
# =============================================================================

@mcp.tool()
def get_account_timeline(account_name: str) -> str:
    """
    Full deal history for an account: every Gong call with transcript + Salesforce context.
    Use this as the foundation for any account question.
    """
    timeline = build_timeline(account_name)
    return format_timeline_for_claude(timeline)


@mcp.tool()
def list_recent_calls(days_back: int = 7, rep_name: str = "") -> str:
    """
    List recent Gong calls. Optionally filter by rep name.
    Useful for a quick view of call activity.
    """
    to_date   = date.today()
    from_date = to_date - timedelta(days=days_back)
    calls = get_calls_in_range(from_date, to_date)

    if rep_name:
        name_lower = rep_name.lower()
        calls = [
            c for c in calls
            if any(
                name_lower in (p.get("name") or "").lower()
                for p in (c.get("parties") or [])
            )
        ]

    if not calls:
        return f"No calls found in the last {days_back} days" + (f" for {rep_name}" if rep_name else "") + "."

    calls_sorted = sorted(calls, key=lambda c: c.get("started") or "", reverse=True)
    lines = [f"Calls — last {days_back} days" + (f" | {rep_name}" if rep_name else ""), ""]
    for call in calls_sorted:
        lines.append(call_summary_line(call))

    return "\n".join(lines)


# =============================================================================
# SALES REP TOOLS
# =============================================================================

@mcp.tool()
def get_prep_brief(account_name: str) -> str:
    """
    Pre-call prep brief for a rep. Surfaces: what was discussed last time,
    open questions, stated pain points, and what the prospect cares about most.
    Use before any 2nd demo or follow-up call.
    """
    timeline = build_timeline(account_name)
    calls    = timeline["calls"]
    sf       = timeline["sf"]
    opp      = sf.get("opportunity") or {}

    if not calls:
        return f"No previous Gong calls found for '{account_name}'. Go in fresh."

    last_call = calls[-1]
    all_transcripts = "\n\n---\n\n".join(
        f"[{c['date']}] {c['title']}\n{c['transcript']}"
        for c in calls if c["transcript"]
    )

    stage = opp.get("StageName", "Unknown")
    mrr   = opp.get("Monthly_Total__c") or 0

    return f"""# Prep Brief: {account_name}

## Deal Status (Salesforce)
Stage: {stage}  |  MRR: ${mrr:.0f}/mo

## Last Call
Date:     {last_call['date']}
Title:    {last_call['title']}
Duration: {last_call['duration_min']} min
Rep:      {last_call['rep']}

## Full Call History ({len(calls)} calls)
Use the transcripts below to identify:
- Pain points the prospect raised
- Features or outcomes they were most excited about
- Any objections or concerns that weren't fully resolved
- What next steps were agreed upon

{all_transcripts}
"""


@mcp.tool()
def get_followup_email_context(account_name: str) -> str:
    """
    Returns full call and deal context to draft a stage-aware follow-up email.
    Includes the latest transcript, deal stage, and contacts.
    Claude will use this to write a personalized email.
    """
    timeline = build_timeline(account_name)
    calls    = timeline["calls"]
    sf       = timeline["sf"]
    opp      = sf.get("opportunity") or {}
    contacts = sf.get("contacts", [])

    if not calls:
        return f"No Gong calls found for '{account_name}'. Cannot draft email without call context."

    last_call = calls[-1]
    stage     = opp.get("StageName", "Unknown")
    mrr       = opp.get("Monthly_Total__c") or 0

    contact_lines = "\n".join(
        f"  {c.get('Name')}  |  {c.get('Title') or 'Unknown title'}  |  {c.get('Email') or 'No email'}"
        for c in contacts
    ) or "  (no contacts found in Salesforce)"

    return f"""# Follow-up Email Context: {account_name}

## Deal Stage: {stage}  |  MRR: ${mrr:.0f}/mo

## Contacts
{contact_lines}

## Most Recent Call  ({last_call['date']}  |  {last_call['duration_min']} min)
{last_call['transcript'] or '(transcript unavailable)'}

## All Previous Calls
{"".join(f"[{c['date']}] {c['title']} ({c['duration_min']} min)\\n{c['transcript']}\\n\\n" for c in calls[:-1]) or "This was the first call."}

---
Using the above, write a follow-up email that:
1. References specific things the prospect said (use their words)
2. Addresses any open concerns
3. Confirms the agreed next step
4. Matches the tone of the conversation (formal vs casual)
5. Is appropriate for the deal stage: {stage}
"""


# =============================================================================
# MANAGER TOOLS (Arpit)
# =============================================================================

@mcp.tool()
def get_deal_risk_signals(account_name: str) -> str:
    """
    Scans all call transcripts for risk signals: competitor mentions,
    pricing pushback, stalled momentum, decision-maker concerns.
    For sales manager use.
    """
    timeline = build_timeline(account_name)
    calls    = timeline["calls"]
    sf       = timeline["sf"]
    opp      = sf.get("opportunity") or {}

    if not calls:
        return f"No calls found for '{account_name}'."

    all_transcripts = "\n\n".join(
        f"[{c['date']}] {c['title']}\n{c['transcript']}"
        for c in calls if c["transcript"]
    )

    stage = opp.get("StageName", "Unknown")

    return f"""# Risk Signal Analysis: {account_name}

## Current Stage: {stage}
## Call Count: {len(calls)}

## Full Transcript History
Review the transcripts below and flag:
- Any competitor names mentioned (Jonas, Sportsman, ClubReady, Mindbody, etc.)
- Pricing objections or budget concerns
- Signs of stalling ("we need more time", "let me check with", "not sure about the timeline")
- Decision-maker changes or new stakeholders introduced
- Promises made by the rep that may be hard to deliver
- Enthusiasm drop between calls

{all_transcripts}
"""


@mcp.tool()
def get_rep_activity_summary(rep_name: str, days_back: int = 14) -> str:
    """
    Summary of a rep's Gong call activity over the last N days.
    For manager coaching and pipeline review.
    """
    to_date   = date.today()
    from_date = to_date - timedelta(days=days_back)
    all_calls = get_calls_in_range(from_date, to_date)

    name_lower = rep_name.lower()
    rep_calls  = [
        c for c in all_calls
        if any(
            name_lower in (p.get("name") or "").lower()
            for p in (c.get("parties") or [])
        )
    ]

    if not rep_calls:
        return f"No Gong calls found for {rep_name} in the last {days_back} days."

    rep_calls_sorted = sorted(rep_calls, key=lambda c: c.get("started") or "", reverse=True)
    total_minutes    = sum(round((c.get("duration") or 0) / 60) for c in rep_calls)

    lines = [
        f"# {rep_name} — Last {days_back} Days",
        f"Total calls: {len(rep_calls)}  |  Total talk time: {total_minutes} min",
        "",
    ]
    for call in rep_calls_sorted:
        lines.append(call_summary_line(call))

    return "\n".join(lines)


# =============================================================================
# ACCOUNT MANAGER TOOLS
# =============================================================================

@mcp.tool()
def get_handoff_brief(account_name: str) -> str:
    """
    Full handoff brief for an account manager taking over a deal.
    Covers: what was sold, what was promised, key contacts, pain points,
    and any concerns raised during the sales cycle.
    """
    timeline = build_timeline(account_name)
    calls    = timeline["calls"]
    sf       = timeline["sf"]
    opp      = sf.get("opportunity") or {}
    contacts = sf.get("contacts", [])

    stage = opp.get("StageName", "Unknown")
    mrr   = opp.get("Monthly_Total__c") or 0

    contact_lines = "\n".join(
        f"  {c.get('Name')}  |  {c.get('Title') or ''}  |  {c.get('Email') or ''}"
        for c in contacts
    ) or "  No contacts in Salesforce."

    all_transcripts = "\n\n---\n\n".join(
        f"[{c['date']}] {c['title']}  ({c['duration_min']} min)  |  Rep: {c['rep']}\n{c['transcript']}"
        for c in calls if c["transcript"]
    ) or "No transcripts available."

    return f"""# Account Handoff Brief: {account_name}

## Deal Summary
Stage:  {stage}
MRR:    ${mrr:.0f}/mo
Calls:  {len(calls)} total

## Key Contacts
{contact_lines}

## Full Sales Cycle Transcripts
Review these to understand:
- Why they bought (the core problem they needed solved)
- What features or outcomes were highlighted as most important
- Specific promises or commitments made during the sales process
- Concerns or hesitations that were raised (watch for these early in onboarding)
- The prospect's communication style and preferences

{all_transcripts}
"""


# =============================================================================
# ONBOARDER TOOLS
# =============================================================================

@mcp.tool()
def get_onboarding_context(account_name: str) -> str:
    """
    Onboarding context for a new client. Explains why they bought,
    what problems they need solved, key stakeholders, and what success
    looks like to them — all sourced from the actual sales conversations.
    """
    timeline = build_timeline(account_name)
    calls    = timeline["calls"]
    sf       = timeline["sf"]
    opp      = sf.get("opportunity") or {}
    contacts = sf.get("contacts", [])

    mrr = opp.get("Monthly_Total__c") or 0

    contact_lines = "\n".join(
        f"  {c.get('Name')}  |  {c.get('Title') or ''}  |  {c.get('Email') or ''}"
        for c in contacts
    ) or "  No contacts in Salesforce."

    all_transcripts = "\n\n---\n\n".join(
        f"[{c['date']}] {c['title']}\n{c['transcript']}"
        for c in calls if c["transcript"]
    ) or "No transcripts available."

    return f"""# Onboarding Context: {account_name}

## Who They Are & What They're Paying
MRR: ${mrr:.0f}/mo

## Key Stakeholders
{contact_lines}

## Sales Conversation History
Read these transcripts and extract:
1. The specific problem they described (in their own words)
2. What their current system / process is (and why it's not working)
3. Which EZFacility features they were most excited about
4. What "success" looks like to them in 90 days
5. Any technical requirements or constraints they mentioned
6. Their facility type, size, and member profile

{all_transcripts}
"""


# =============================================================================
# EXECUTIVE TOOLS (Miranda)
# =============================================================================

@mcp.tool()
def get_pipeline_call_activity(days_back: int = 30) -> str:
    """
    High-level view of all Gong call activity across the team.
    For executive pipeline reviews. Shows volume, reps active, accounts touched.
    """
    to_date   = date.today()
    from_date = to_date - timedelta(days=days_back)
    calls     = get_calls_in_range(from_date, to_date)

    if not calls:
        return f"No calls found in the last {days_back} days."

    total_minutes = sum(round((c.get("duration") or 0) / 60) for c in calls)
    calls_sorted  = sorted(calls, key=lambda c: c.get("started") or "", reverse=True)

    lines = [
        f"# Pipeline Call Activity — Last {days_back} Days",
        f"Total calls: {len(calls)}  |  Total talk time: {total_minutes} min",
        "",
        "## All Calls (newest first)",
    ]
    for call in calls_sorted:
        lines.append(call_summary_line(call))

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
