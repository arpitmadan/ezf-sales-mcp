# EZFacility Sales MCP

Connects Claude Desktop to your Gong call transcripts and Salesforce deals.
Every role in the revenue org gets the right context for their job — without copy-pasting transcripts manually.

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

## Prerequisites

- macOS (Windows support coming)
- Python 3.10 or newer — check with `python3 --version`
- Claude Desktop installed
- Gong API credentials (from your Gong admin)
- Salesforce credentials

---

## Setup (5 minutes)

### Step 1 — Clone the repo

```bash
git clone https://github.com/arpitmadan/ezf-sales-mcp.git
cd ezf-sales-mcp
```

### Step 2 — Run setup

```bash
chmod +x setup.sh
./setup.sh
```

This creates a virtual environment and installs all dependencies.

### Step 3 — Add your credentials

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in:

```
GONG_ACCESS_KEY=        ← from Gong Settings → API
GONG_ACCESS_SECRET=     ← from Gong Settings → API
SF_USERNAME=            ← your Salesforce email
SF_PASSWORD=            ← your Salesforce password
SF_SECURITY_TOKEN=      ← Salesforce Settings → Reset Security Token
```

### Step 4 — Add to Claude Desktop

Open `~/.claude/claude_desktop_config.json` (create it if it doesn't exist).

Add `ezf-sales` inside the `mcpServers` block — replace `/path/to` with the actual folder path:

```json
{
  "mcpServers": {
    "ezf-sales": {
      "command": "/path/to/ezf-sales-mcp/venv/bin/python",
      "args": ["/path/to/ezf-sales-mcp/server.py"]
    }
  }
}
```

> **Tip:** Run `./setup.sh` — it prints the exact config snippet with the correct paths for your machine.

### Step 5 — Restart Claude Desktop

Quit and reopen Claude Desktop. The EZF Sales tools will appear automatically.

---

## Available Tools

| Tool | Use it when... |
|---|---|
| `get_account_timeline` | You need everything about an account |
| `list_recent_calls` | You want a quick view of call activity |
| `get_prep_brief` | Before any call — surfaces what was discussed before |
| `get_followup_email_context` | After a call — drafts a personalized follow-up |
| `get_deal_risk_signals` | A deal feels off — scan for red flags |
| `get_rep_activity_summary` | Manager coaching / pipeline review |
| `get_handoff_brief` | AM taking over an account |
| `get_onboarding_context` | Onboarder getting up to speed |
| `get_pipeline_call_activity` | Exec-level activity overview |

---

## Example Prompts

```
What pain points did Granite State Indoor Range mention across all their calls?

Write a follow-up email for my call with ABC Fitness today.

What did we promise Riverside Fitness during the sales cycle?

Show me risk signals in the Nuva Amenity deal.

Give me a handoff brief for Mountain View Recreation — I'm their new AM.
```

---

## Notes

- **Gong admin required** for API key generation. Ask your admin for a read-only key.
- **Salesforce MCP users:** if you already have an SF MCP connected to Claude Desktop, you can skip the SF credentials — use this server for Gong and your existing SF MCP for deal data.
- The `.env` file is gitignored and never committed. Each team member adds their own credentials.

---

## Team Setup

Each team member:
1. Clones the repo
2. Runs `./setup.sh`
3. Adds their own `.env` with their credentials
4. Updates their Claude Desktop config

One repo, everyone connects with their own keys.
