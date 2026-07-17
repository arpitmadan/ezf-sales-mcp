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

import csv
import os

from gong_client import get_calls_for_reps, get_crm_context_bulk, get_transcripts_bulk, call_line
from salesforce_client import get_accounts_by_id, get_opportunities_by_id, get_leads_by_email

PAYMENT_PROCESSING_MRR = 250  # every opp carries this in payment-processing revenue on top of software MRR

# One running dataset, not a file per week — lets the product team filter by
# quarter/half/year later instead of stitching separate weekly files together.
LOG_COLUMNS = ["week_of", "account", "missing_functionality", "gong_call_link",
               "opportunity_value", "industry", "competitor_mentioned", "rep", "call_date"]
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "product_gaps_log.csv")


def build_report_packets(rep_names: list, days_back: int = 7) -> list:
    """
    One packet per call: {rep, date, url, account_name, industry, arr_total,
    stage, transcript}.

    A deal that died before any Account/Opportunity existed — e.g. the rep
    disqualified the lead ("Not a Good Fit") right after this call — is one
    of the most useful signals for this report, not noise to drop. Gong's
    own CRM context only links calls to an Account/Opportunity, so those
    calls come back with empty context; they're matched to a Salesforce Lead
    directly by attendee email instead. Only a call with truly no SF trace
    at all (no Account, no Lead) falls back to Gong's own attendee data.
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

    unlinked_emails = [
        e for ctx in context.values() if not ctx.get("account_id")
        for e in ctx.get("external_emails", [])
    ]
    leads = get_leads_by_email(unlinked_emails)

    rep_by_id = {v: k for k, v in _resolve_reps(rep_names).items()}

    packets = []
    for c in calls:
        cid = c.get("id")
        ctx = context.get(cid, {})
        acct_id = ctx.get("account_id")

        if acct_id:
            acct = accounts.get(acct_id, {})
            opp = opps.get(ctx.get("opportunity_id"), {})
            software_arr = opp.get("arr", 0)  # Annual_Revenue__c — excludes setup/activation fee
            arr_total = software_arr + (PAYMENT_PROCESSING_MRR * 12) if software_arr else None
            account_name = acct.get("name") or ctx.get("account_name")
            industry = acct.get("industry")
            stage = opp.get("stage")
        else:
            lead = next(
                (leads[e.lower()] for e in ctx.get("external_emails", []) if e.lower() in leads),
                None,
            )
            arr_total = None
            if lead:
                account_name = lead.get("company") or lead.get("name")
                industry = lead.get("industry")
                stage = f"No opportunity — Lead status: {lead.get('status') or 'unknown'}"
            else:
                # No SF trace at all — best-effort name from the call itself.
                account_name = (ctx.get("external_names") or [c.get("title") or "Unknown"])[0]
                industry = None
                stage = "Not found in Salesforce"

        packets.append({
            "rep": rep_by_id.get(c.get("primaryUserId"), "Unknown"),
            "date": (c.get("started") or "")[:10],
            "url": c.get("url"),
            "account_name": account_name,
            "industry": industry,
            "opportunity_stage": stage,
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
        arr = f"${p['arr_total']:,.0f}" if p["arr_total"] else "N/A — no opportunity created"
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


def _parse_markdown_table(markdown_table: str) -> list:
    """Rows from a '| Account | ... |' table, in LOG_COLUMNS[1:] order (no week_of)."""
    rows = []
    for line in markdown_table.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0].lower() == "account":
            continue  # header
        if len(cells) == len(LOG_COLUMNS) - 1:
            rows.append(cells)
    return rows


def append_report_rows(markdown_table: str, week_label: str) -> str:
    """
    Append the extracted table's rows to the running log, stamped with
    week_label. Rows are deduped by (gong_call_link, missing_functionality)
    so re-running the same week twice doesn't create duplicate entries.
    """
    rows = _parse_markdown_table(markdown_table)
    if not rows:
        return "No rows found in that table — nothing to save."

    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    existing_keys = set()
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, newline="") as f:
            for r in csv.DictReader(f):
                existing_keys.add((r.get("gong_call_link"), r.get("missing_functionality")))

    is_new_file = not os.path.exists(LOG_PATH)
    added, skipped = 0, 0
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new_file:
            writer.writerow(LOG_COLUMNS)
        for cells in rows:
            key = (cells[2], cells[1])  # (gong_call_link, missing_functionality)
            if key in existing_keys:
                skipped += 1
                continue
            writer.writerow([week_label] + cells)
            existing_keys.add(key)
            added += 1

    return f"Saved {added} new row(s) to {LOG_PATH} (week_of={week_label}, {skipped} duplicate(s) skipped)."


def read_report_history(start_date: str = "", end_date: str = "") -> str:
    """
    All logged rows with call_date in [start_date, end_date] (inclusive,
    either bound optional) — for quarterly/semi-annual/annual rollups
    instead of re-scanning Gong.
    """
    if not os.path.exists(LOG_PATH):
        return "No product-gap history saved yet — run get_product_gap_report first."

    with open(LOG_PATH, newline="") as f:
        rows = list(csv.DictReader(f))

    if start_date:
        rows = [r for r in rows if r.get("call_date", "") >= start_date]
    if end_date:
        rows = [r for r in rows if r.get("call_date", "") <= end_date]

    if not rows:
        return f"No product-gap rows found between {start_date or '(earliest)'} and {end_date or '(latest)'}."

    lines = [
        f"# Product Gap History — {len(rows)} rows"
        f" ({start_date or 'earliest'} to {end_date or 'latest'})",
        "",
        "| " + " | ".join(LOG_COLUMNS) + " |",
        "|" + "---|" * len(LOG_COLUMNS),
    ]
    for r in rows:
        lines.append("| " + " | ".join(r.get(c, "") for c in LOG_COLUMNS) + " |")

    return "\n".join(lines)
