#!/usr/bin/env python3
"""
Salesforce client — pulls deal context for a given account name.
Uses the same credentials pattern as the DailyStandup repo.
"""

import os
from simple_salesforce import Salesforce


def connect() -> Salesforce:
    return Salesforce(
        username=os.environ.get("SF_USERNAME"),
        password=os.environ.get("SF_PASSWORD"),
        security_token=os.environ.get("SF_SECURITY_TOKEN"),
        domain=os.environ.get("SF_DOMAIN", "login"),
    )


def get_opportunity(sf: Salesforce, account_name: str) -> dict | None:
    """
    Return the primary (software) opportunity for an account.
    Prefers non-EZPayments opps — EZPayments is a separate payments opp
    with $0 MRR and should not be treated as the main deal.
    Falls back to most recent if only EZPayments exists.
    """
    safe = account_name.replace("'", "\\'")
    results = sf.query_all(f"""
        SELECT Id, Name, StageName, Monthly_Total__c, CloseDate,
               Owner.Name, CreatedDate, Description, Type
        FROM Opportunity
        WHERE Account.Name LIKE '%{safe}%'
        ORDER BY CreatedDate DESC
    """)["records"]

    if not results:
        return None

    # Prefer the main software opp over EZPayments
    software_opps = [r for r in results if "ezpayment" not in (r.get("Name") or "").lower()
                     and "payfac" not in (r.get("StageName") or "").lower()]
    return software_opps[0] if software_opps else results[0]


def get_all_opportunities(sf: Salesforce, account_name: str) -> list:
    """Return all opportunities for an account — useful for full deal context."""
    safe = account_name.replace("'", "\\'")
    return sf.query_all(f"""
        SELECT Id, Name, StageName, Monthly_Total__c, CloseDate,
               Owner.Name, CreatedDate, Description
        FROM Opportunity
        WHERE Account.Name LIKE '%{safe}%'
        ORDER BY CreatedDate DESC
    """)["records"]


def get_opportunity_history(sf: Salesforce, opp_id: str) -> list:
    """Return stage history for an opportunity."""
    results = sf.query_all(f"""
        SELECT StageName, CreatedDate
        FROM OpportunityHistory
        WHERE OpportunityId = '{opp_id}'
        ORDER BY CreatedDate ASC
    """)["records"]
    return results


def get_contacts(sf: Salesforce, account_name: str) -> list:
    """Return contacts associated with the account."""
    safe = account_name.replace("'", "\\'")
    results = sf.query_all(f"""
        SELECT Name, Title, Email, Phone
        FROM Contact
        WHERE Account.Name LIKE '%{safe}%'
        ORDER BY Name ASC
        LIMIT 10
    """)["records"]
    return results


def get_recent_tasks(sf: Salesforce, account_name: str, days_back: int = 90) -> list:
    """Return recent tasks/activities logged against the account."""
    safe = account_name.replace("'", "\\'")
    results = sf.query_all(f"""
        SELECT Subject, Status, Type, Owner.Name, CreatedDate, Description
        FROM Task
        WHERE What.Name LIKE '%{safe}%'
        AND CreatedDate = LAST_N_DAYS:{days_back}
        ORDER BY CreatedDate DESC
        LIMIT 20
    """)["records"]
    return results


def build_deal_context(account_name: str) -> dict:
    """
    Return a structured dict of all SF deal context for an account.
    Returns empty structure on any connection/query failure.
    """
    try:
        sf   = connect()
        opp  = get_opportunity(sf, account_name)
        all_opps = get_all_opportunities(sf, account_name)

        history  = get_opportunity_history(sf, opp["Id"]) if opp else []
        contacts = get_contacts(sf, account_name)
        tasks    = get_recent_tasks(sf, account_name)

        return {
            "opportunity":      opp,
            "all_opportunities": all_opps,
            "stage_history":    history,
            "contacts":         contacts,
            "recent_tasks":     tasks,
        }
    except Exception as e:
        return {
            "opportunity": None,
            "stage_history": [],
            "contacts": [],
            "recent_tasks": [],
            "error": str(e),
        }
