#!/usr/bin/env python3
"""
Weekly product-gap report.

Scans the sales team's Gong calls for a date window, links each call to its
Salesforce Account/Opportunity via Gong's native CRM context (no title
guessing), and returns a compiled per-call packet — transcript + account
value + industry — along with an extraction prompt. The assistant reading
this (Claude, in whoever's chat calls the tool) does the actual language
understanding: spotting "the platform can't do X" moments and competitor
mentions in the transcript. That's not something to hardcode in Python.
"""

from gong_client import get_calls_for_reps, get_crm_context_bulk, get_transcripts_bulk, call_line
from salesforce_client import get_accounts_by_id, get_opportunities_by_id

PAYMENT_PROCESSING_MRR = 250  # every opp carries this in payment-processing revenue on top of software MRR


def build_report_packets(rep_names: list, days_back: int = 7) -> list:
    """
    One packet per call: {rep, date, url, account_name, industry, arr_total,
    stage, transcript}. Calls with no linked SF Account are skipped — there's
    no account to route a product gap back to.
    """
    calls = get_calls_for_reps(rep_names, days_back)
    if not calls:
        return []

    call_ids = [c["id"] for c in calls if c.get("id")]
    context = get_crm_context_bulk(call_ids)
    transcripts = get_transcripts_bulk(call_ids)

    account_ids = [ctx["account_id"] for ctx in context.values() if ctx.get("account_id")]
    opp_ids = [ctx["opportunity_id"] for ctx in context.values() if ctx.get("opportunity_id")]
    accounts = get_accounts_by_id(account_ids)
    opps = get_opportunities_by_id(opp_ids)

    rep_by_id = {v: k for k, v in _resolve_reps(rep_names).items()}

    packets = []
    for c in calls:
        cid = c.get("id")
        ctx = context.get(cid, {})
        acct_id = ctx.get("account_id")
        if not acct_id:
            continue  # no SF account linked — nothing to route back to R&D

        acct = accounts.get(acct_id, {})
        opp = opps.get(ctx.get("opportunity_id"), {})
        software_arr = opp.get("arr", 0)  # Annual_Revenue__c — excludes setup/activation fee
        arr_total = software_arr + (PAYMENT_PROCESSING_MRR * 12) if software_arr else None

        packets.append({
            "rep": rep_by_id.get(c.get("primaryUserId"), "Unknown"),
            "date": (c.get("started") or "")[:10],
            "url": c.get("url"),
            "account_name": acct.get("name") or ctx.get("account_name"),
            "industry": acct.get("industry"),
            "opportunity_stage": opp.get("stage"),
            "arr_total": arr_total,
            "transcript": transcripts.get(cid, "(transcript not available)"),
        })

    return packets


def _resolve_reps(rep_names: list) -> dict:
    from gong_client import resolve_rep_ids
    return resolve_rep_ids(rep_names)


def build_report_prompt(rep_names: list, days_back: int = 7) -> str:
    """Compiled call data + extraction instructions, ready to hand to an LLM."""
    packets = build_report_packets(rep_names, days_back)
    if not packets:
        return f"No calls with a linked Salesforce account found for {', '.join(rep_names)} in the last {days_back} days."

    lines = [
        f"# Weekly Product Gap Scan — {len(packets)} calls, last {days_back} days",
        f"Reps: {', '.join(rep_names)}",
        "",
    ]
    for p in packets:
        arr = f"${p['arr_total']:,.0f}" if p["arr_total"] else "unknown"
        lines.append(f"## {p['account_name']}  |  {p['date']}  |  {p['rep']}")
        lines.append(
            f"Industry: {p['industry'] or 'unknown'}  |  "
            f"Opportunity value (ARR + $3,000 payment processing): {arr}  |  "
            f"Stage: {p['opportunity_stage'] or 'unknown'}  |  "
            f"Call: {p['url']}"
        )
        lines.append("")
        lines.append(p["transcript"])
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("""
## Instructions

Read every transcript above. For each call, identify any moment where the
prospect raised a need EZFacility's platform doesn't currently meet, and
that appears to be slowing down or blocking the deal — not vague wishlist
chatter, but a specific capability gap tied to their decision.

Also flag whether a competitor was named in the call (ClubReady, Mindbody,
Jonas, MemberSplash, Amilia, Acuity, or any other platform mentioned as an
alternative).

Produce a markdown table with these exact columns, one row per distinct
missing functionality found (an account can have more than one row):

| Account | Missing Functionality | Gong Call Link | Opportunity Value | Industry | Competitor Mentioned | Rep | Call Date |

- Opportunity Value: use the ARR figure given above for that account.
- Competitor Mentioned: name it, or "None" if none was mentioned.
- Skip calls where no real functionality gap came up — don't force a row.
- Be specific in "Missing Functionality" — quote or closely paraphrase what
  the prospect actually said, don't generalize it into a vague category.
""")

    return "\n".join(lines)
