#!/usr/bin/env python3
"""
Salesforce client — parallel queries for deal context.
EZPayments opps (Payfac stage) are secondary; main software opp is preferred.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from simple_salesforce import Salesforce


def _sf() -> Salesforce:
    return Salesforce(
        username=os.environ.get("SF_USERNAME"),
        password=os.environ.get("SF_PASSWORD"),
        security_token=os.environ.get("SF_SECURITY_TOKEN"),
        domain=os.environ.get("SF_DOMAIN", "login"),
    )


def build_deal_context(account_name: str) -> dict:
    """
    Fetch all SF deal context in parallel.
    Returns opportunity, all_opportunities, stage_history, contacts, recent_tasks.
    """
    try:
        sf = _sf()
        safe = account_name.replace("'", "\\'")

        with ThreadPoolExecutor(max_workers=3) as ex:
            f_opps     = ex.submit(_all_opps,    sf, safe)
            f_contacts = ex.submit(_contacts,    sf, safe)
            f_tasks    = ex.submit(_recent_tasks, sf, safe)
            all_opps = f_opps.result()
            contacts = f_contacts.result()
            tasks    = f_tasks.result()

        opp     = _primary_opp(all_opps)
        history = _stage_history(sf, opp["Id"]) if opp else []

        return {
            "opportunity":       opp,
            "all_opportunities": all_opps,
            "stage_history":     history,
            "contacts":          contacts,
            "recent_tasks":      tasks,
        }
    except Exception as e:
        return {
            "opportunity": None, "all_opportunities": [],
            "stage_history": [], "contacts": [],
            "recent_tasks": [], "error": str(e),
        }


def _all_opps(sf, safe_name: str) -> list:
    return sf.query_all(f"""
        SELECT Id, Name, StageName, Monthly_Total__c, CloseDate, Owner.Name, CreatedDate
        FROM Opportunity
        WHERE Account.Name LIKE '%{safe_name}%'
        ORDER BY CreatedDate DESC
    """)["records"]


def _primary_opp(opps: list) -> dict | None:
    """Prefer the main software opp over EZPayments."""
    if not opps:
        return None
    software = [o for o in opps
                if "ezpayment" not in (o.get("Name") or "").lower()
                and "payfac"    not in (o.get("StageName") or "").lower()]
    return software[0] if software else opps[0]


def _stage_history(sf, opp_id: str) -> list:
    return sf.query_all(f"""
        SELECT StageName, CreatedDate FROM OpportunityHistory
        WHERE OpportunityId = '{opp_id}' ORDER BY CreatedDate ASC
    """)["records"]


def _contacts(sf, safe_name: str) -> list:
    return sf.query_all(f"""
        SELECT Name, Title, Email, Phone FROM Contact
        WHERE Account.Name LIKE '%{safe_name}%'
        ORDER BY Name ASC LIMIT 10
    """)["records"]


def _recent_tasks(sf, safe_name: str) -> list:
    return sf.query_all(f"""
        SELECT Subject, Status, Type, Owner.Name, CreatedDate
        FROM Task
        WHERE What.Name LIKE '%{safe_name}%'
        AND CreatedDate = LAST_N_DAYS:90
        ORDER BY CreatedDate DESC LIMIT 10
    """)["records"]


# ---------------------------------------------------------------------------
# Batch lookups keyed by ID — for sweeping many accounts/opps at once
# (e.g. the weekly product-gap report), instead of one lookup per account.
# ---------------------------------------------------------------------------

def get_accounts_by_id(account_ids: list) -> dict:
    """
    {account_id: {"name", "industry"}} for a batch of Account IDs.
    Industry__c on the Account is often left blank by reps, even though the
    original Lead that converted into it usually has Lead_Industry__c filled
    in — so any account missing Industry__c is backfilled from its converted
    Lead as a fallback.
    """
    ids = sorted({a for a in account_ids if a})
    if not ids:
        return {}
    sf = _sf()
    id_list = ",".join(f"'{i}'" for i in ids)
    records = sf.query_all(f"""
        SELECT Id, Name, Industry__c FROM Account WHERE Id IN ({id_list})
    """)["records"]
    result = {
        r["Id"]: {"name": r.get("Name"), "industry": r.get("Industry__c")}
        for r in records
    }

    missing = [aid for aid, a in result.items() if not a["industry"]]
    if missing:
        result.update(_backfill_industry_from_lead(sf, missing, result))

    return result


def _backfill_industry_from_lead(sf, account_ids: list, accounts: dict) -> dict:
    id_list = ",".join(f"'{i}'" for i in account_ids)
    leads = sf.query_all(f"""
        SELECT ConvertedAccountId, Lead_Industry__c FROM Lead
        WHERE ConvertedAccountId IN ({id_list}) AND Lead_Industry__c != null
    """)["records"]
    updated = dict(accounts)
    for lead in leads:
        aid = lead["ConvertedAccountId"]
        updated[aid] = {**updated[aid], "industry": lead.get("Lead_Industry__c")}
    return updated


def get_leads_by_email(emails: list) -> dict:
    """
    {email_lower: {"name", "company", "industry", "status"}} for unconverted
    Leads matching the given attendee emails. This is the fallback path for
    calls with a prospect who never became an Account/Opportunity — e.g. the
    rep disqualified them ("Not a Good Fit") before any SF record beyond the
    Lead was created. Gong's own CRM context can't find these (it only links
    calls to an Account/Opportunity), so this is a direct Lead lookup.
    """
    addrs = sorted({e.lower() for e in emails if e})
    if not addrs:
        return {}
    sf = _sf()
    id_list = ",".join(f"'{a}'" for a in addrs)
    records = sf.query_all(f"""
        SELECT Name, Company, Lead_Industry__c, Status, Email
        FROM Lead WHERE Email IN ({id_list})
    """)["records"]
    return {
        r["Email"].lower(): {
            "name": r.get("Name"),
            "company": r.get("Company"),
            "industry": r.get("Lead_Industry__c"),
            "status": r.get("Status"),
        }
        for r in records if r.get("Email")
    }


def get_opportunities_by_id(opportunity_ids: list) -> dict:
    """
    {opp_id: {"name", "stage", "mrr", "arr", "competitors_field"}} for a batch
    of Opportunity IDs. arr excludes setup/activation fee (Annual_Revenue__c
    is a formula field = Monthly_Total__c * 12; activation fee is separate).
    """
    ids = sorted({o for o in opportunity_ids if o})
    if not ids:
        return {}
    sf = _sf()
    id_list = ",".join(f"'{i}'" for i in ids)
    records = sf.query_all(f"""
        SELECT Id, Name, StageName, Monthly_Total__c, Annual_Revenue__c, Competitors__c
        FROM Opportunity WHERE Id IN ({id_list})
    """)["records"]
    return {
        r["Id"]: {
            "name": r.get("Name"),
            "stage": r.get("StageName"),
            "mrr": r.get("Monthly_Total__c") or 0,
            "arr": r.get("Annual_Revenue__c") or 0,
            "competitors_field": r.get("Competitors__c"),
        }
        for r in records
    }
