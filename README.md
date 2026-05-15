# EZFacility Sales MCP

Connects Claude Desktop to your Gong call transcripts and Salesforce deals.
Every role in the revenue org gets deal intelligence — without copy-pasting transcripts manually.

---

## Who This Is For

| Role | What you can ask Claude |
|---|---|
| **Sales rep** | "Write my follow-up email for Granite State" |
| **Sales manager** | "What are the risk signals in the ABC deal?" |
| **CEO** | "Show me all call activity from the last 30 days" |
| **Account manager** | "Get me the full handoff brief for XYZ" |
| **Onboarder** | "Why did Riverside Fitness buy and what did we promise?" |

---

## Setup

### Prerequisites

- macOS
- Python 3 — download from [python.org/downloads](https://www.python.org/downloads/) if you don't have it
- Claude Desktop installed
- Gong API credentials (from your Gong admin)
- Your Salesforce email, password, and security token

### Step 1 — Download this folder

Click the green **Code** button above → **Download ZIP** → unzip it → you'll have a folder called `ezf-sales-mcp-main`.

### Step 2 — Open a terminal in that folder

- On Mac: right-click the folder → **New Terminal at Folder**
- In VS Code: open the folder, then press `` Ctrl+` ``

### Step 3 — Run setup

```bash
./setup.sh
```

The script will:
- Install everything automatically
- Ask for your Gong and Salesforce credentials
- Save them securely to a `.env` file on your machine
- Update your Claude Desktop config

### Step 4 — Restart Claude Desktop

Quit and reopen Claude Desktop. The EZF Sales tools will connect automatically.

**Test it:** Type `get account summary for Concord Swim` in Claude.

---

## Available Tools

| Tool | When to use it |
|---|---|
| `get_account_summary` | Fast overview — deal stage, MRR, contacts, call list (no transcripts) |
| `get_call_transcript` | Full transcript for a specific call (1 = most recent) |
| `get_full_context` | Deep analysis — summary + all transcripts |
| `list_recent_calls` | Quick view of call activity across the team |
| `get_prep_brief` | Before a call — deal status + most recent transcript |
| `get_followup_email` | After a call — drafts a personalized follow-up email |
| `get_deal_risk` | A deal feels off — scans transcripts for red flags |
| `get_pipeline_activity` | Manager/exec view of all call activity |

---

## Example Prompts

```
Get account summary for Granite State Indoor Range.

Write a follow-up email for my last call with ABC Fitness.

What did we promise Riverside Fitness during the sales cycle?

Show me risk signals in the Nuva Amenity deal.

List all calls from the last 14 days.
```

---

## Notes

- **Your `.env` file is never committed to git.** Each person on the team uses their own credentials.
- **Salesforce security token:** go to SF → top-right avatar → Settings → Personal → Reset My Security Token. It gets emailed to you.
- **Gong API key:** ask your Gong admin to generate a read-only API key from Gong Settings → API.

---

## Team Setup

Each person:
1. Downloads the ZIP from GitHub
2. Runs `./setup.sh` and enters their own credentials
3. Restarts Claude Desktop

Questions? Slack @arpit.
