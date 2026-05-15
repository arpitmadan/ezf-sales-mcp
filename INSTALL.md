# EZFacility Sales MCP — Team Setup Guide

Before you start, message **@arpit on Slack** to get the Gong API key and secret.
You'll also need your own Salesforce login credentials.

---

## Mac Setup

### Step 1 — Check if Python is installed

1. Open **VS Code**
2. Press **Ctrl+`** (the backtick key, top-left of your keyboard) to open the terminal
3. Type this and press Enter:
   ```
   python3 --version
   ```
4. If you see something like `Python 3.11.2` — you're good, skip to Step 2.
   If you see `command not found` — go to [python.org/downloads](https://www.python.org/downloads/), download the latest version, and install it. Then come back here.

---

### Step 2 — Download the EZF Sales MCP folder

1. Go to: **github.com/arpitmadan/ezf-sales-mcp**
2. Click the green **Code** button
3. Click **Download ZIP**
4. Open your Downloads folder and double-click the ZIP to unzip it
5. You'll now have a folder called **ezf-sales-mcp-main**

---

### Step 3 — Open the folder in VS Code

1. Open **VS Code**
2. Click **File** → **Open Folder**
3. Find and select the **ezf-sales-mcp-main** folder
4. Click **Open**

---

### Step 4 — Run setup

1. Press **Ctrl+`** to open the terminal inside VS Code
2. Type this and press Enter:
   ```
   bash setup.sh
   ```
3. Press **Enter** when prompted to continue
4. Enter the **Gong Access Key** and **Gong Access Secret** (get these from @arpit)
5. Enter your **Salesforce email**, **Salesforce password**, and **Salesforce security token**

> **Where's my Salesforce security token?**
> Log into Salesforce → click your avatar (top right) → Settings → scroll to **Personal** → **Reset My Security Token** → click the button → check your email.

---

### Step 5 — Restart Claude Desktop

Quit Claude Desktop completely and reopen it.

**To test it worked:** Type `get account summary for Concord Swim` in Claude.
If you see deal info and call history, you're all set.

---
---

## Windows Setup

### Step 1 — Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/) and download the latest version
2. Run the installer
3. **Important:** On the first screen, check the box that says **"Add Python to PATH"** before clicking Install Now

---

### Step 2 — Install Git for Windows

Git for Windows gives you the terminal (Git Bash) that the setup script needs.

1. Go to [git-scm.com/download/win](https://git-scm.com/download/win) — the download starts automatically
2. Run the installer, click **Next** through all the screens (defaults are fine)

---

### Step 3 — Install VS Code (if you don't have it)

Download from [code.visualstudio.com](https://code.visualstudio.com/) and install it.

---

### Step 4 — Download the EZF Sales MCP folder

1. Go to: **github.com/arpitmadan/ezf-sales-mcp**
2. Click the green **Code** button
3. Click **Download ZIP**
4. Open your Downloads folder and right-click the ZIP → **Extract All** → **Extract**
5. You'll now have a folder called **ezf-sales-mcp-main**

---

### Step 5 — Open the folder in VS Code

1. Open **VS Code**
2. Click **File** → **Open Folder**
3. Find and select the **ezf-sales-mcp-main** folder
4. Click **Select Folder**

---

### Step 6 — Switch the terminal to Git Bash

VS Code on Windows uses PowerShell by default — we need Git Bash instead.

1. Press **Ctrl+`** to open the terminal
2. Click the **dropdown arrow** next to the `+` sign in the top-right of the terminal panel
3. Click **Git Bash**

You should now see a `$` prompt instead of `PS >`

---

### Step 7 — Run setup

1. In the Git Bash terminal, type this and press Enter:
   ```
   bash setup.sh
   ```
2. Press **Enter** when prompted to continue
3. Enter the **Gong Access Key** and **Gong Access Secret** (get these from @arpit)
4. Enter your **Salesforce email**, **Salesforce password**, and **Salesforce security token**

> **Where's my Salesforce security token?**
> Log into Salesforce → click your avatar (top right) → Settings → scroll to **Personal** → **Reset My Security Token** → click the button → check your email.

---

### Step 8 — Restart Claude Desktop

Quit Claude Desktop completely and reopen it.

**To test it worked:** Type `get account summary for Concord Swim` in Claude.
If you see deal info and call history, you're all set.

---

## Troubleshooting

**"bash: setup.sh: Permission denied"**
Run `bash setup.sh` instead of `./setup.sh`.

**"python not found" on Windows after installing Python**
Close the terminal, open a new one, and try again. The PATH update needs a fresh terminal.

**Claude Desktop doesn't show EZF Sales tools after restart**
The config file may not have updated. Message @arpit with a screenshot of your terminal output.

**"Invalid credentials" error when testing in Claude**
Double-check your Salesforce security token — it resets every time you change your SF password.

---

Questions? Slack **@arpit**.
