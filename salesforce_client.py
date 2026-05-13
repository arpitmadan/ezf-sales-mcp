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
