#!/bin/bash
# EZFacility Sales MCP — one-command setup
# Works on macOS and Windows (Git Bash)
set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── OS detection ─────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
  IS_WINDOWS=true
  PYTHON_CMD="python"
  VENV_ACTIVATE="$REPO_DIR/venv/Scripts/activate"
  PYTHON_EXEC="$REPO_DIR/venv/Scripts/python.exe"
  CLAUDE_CONFIG="$(cygpath -u "$APPDATA")/Claude/claude_desktop_config.json"
else
  IS_WINDOWS=false
  PYTHON_CMD="python3"
  VENV_ACTIVATE="$REPO_DIR/venv/bin/activate"
  PYTHON_EXEC="$REPO_DIR/venv/bin/python"
  CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
fi

# ── Formatting helpers ────────────────────────────────────────────────────────
bold()  { printf '\033[1m%s\033[0m' "$*"; }
green() { printf '\033[32m%s\033[0m' "$*"; }
red()   { printf '\033[31m%s\033[0m' "$*"; }
dim()   { printf '\033[2m%s\033[0m' "$*"; }

header() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  $(bold "$1")"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

step() { echo ""; echo "  $(bold "→") $1"; }
ok()   { echo "  $(green "✓") $1"; }
warn() { echo "  $(red "!") $1"; }

# ── Welcome ───────────────────────────────────────────────────────────────────
header "EZFacility Sales MCP Setup"
echo ""
echo "  This will set up the EZF Sales MCP on your computer."
echo "  Takes about 2 minutes. You'll need your API credentials ready."
echo ""
echo "  $(dim "Press Enter to continue or Ctrl+C to cancel.")"
read -r

# ── Step 1: Python check ──────────────────────────────────────────────────────
step "Checking Python..."
if ! command -v "$PYTHON_CMD" &>/dev/null; then
  warn "Python not found."
  echo ""
  if [ "$IS_WINDOWS" = true ]; then
    echo "  Please install Python from: https://www.python.org/downloads/"
    echo "  IMPORTANT: During install, check 'Add Python to PATH' before clicking Install."
  else
    echo "  Please install Python from: https://www.python.org/downloads/"
  fi
  echo "  Then close this terminal, open a new one, and run setup again."
  echo ""
  exit 1
fi
PYTHON_VERSION=$("$PYTHON_CMD" --version 2>&1)
ok "Found $PYTHON_VERSION"

# ── Step 2: Virtual environment ───────────────────────────────────────────────
step "Creating Python environment..."
cd "$REPO_DIR"
"$PYTHON_CMD" -m venv venv
source "$VENV_ACTIVATE"
ok "Environment ready"

# ── Step 3: Install packages ──────────────────────────────────────────────────
step "Installing packages (this may take a minute)..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Packages installed"

# ── Step 4: Credentials ───────────────────────────────────────────────────────
header "API Credentials"

if [ -f "$REPO_DIR/.env" ]; then
  echo ""
  echo "  An existing .env file was found."
  echo "  $(dim "Press Enter to keep it, or type 'new' to re-enter credentials:")"
  read -r RECRED
  if [ "$RECRED" != "new" ]; then
    ok "Using existing credentials"
    SKIP_CREDS=true
  fi
fi

if [ "$SKIP_CREDS" != "true" ]; then
  echo ""
  echo "  You'll need 2 things from Gong and 3 from Salesforce."
  echo "  $(dim "(Your input is hidden as you type — that's normal)")"
  echo ""

  echo "  $(bold "Gong API")"
  echo "  $(dim "Ask @arpit on Slack for the Gong Access Key and Secret")"
  echo ""
  printf "  Gong Access Key:    "
  read -r GONG_KEY
  printf "  Gong Access Secret: "
  read -rs GONG_SECRET
  echo ""
  echo ""

  echo "  $(bold "Salesforce")"
  echo "  $(dim "Your SF login email, password, and security token")"
  echo "  $(dim "Security token: SF → top-right avatar → Settings → Personal → Reset My Security Token")"
  echo ""
  printf "  SF Email:           "
  read -r SF_USER
  printf "  SF Password:        "
  read -rs SF_PASS
  echo ""
  printf "  SF Security Token:  "
  read -rs SF_TOKEN
  echo ""
  echo ""

  if [ -z "$GONG_KEY" ] || [ -z "$GONG_SECRET" ] || [ -z "$SF_USER" ] || [ -z "$SF_PASS" ] || [ -z "$SF_TOKEN" ]; then
    warn "One or more credentials were left blank. Please run setup again."
    exit 1
  fi

  cat > "$REPO_DIR/.env" <<EOF
GONG_ACCESS_KEY=$GONG_KEY
GONG_ACCESS_SECRET=$GONG_SECRET
SF_USERNAME=$SF_USER
SF_PASSWORD=$SF_PASS
SF_SECURITY_TOKEN=$SF_TOKEN
SF_DOMAIN=login
EOF

  ok "Credentials saved to .env"
fi

# ── Step 5: Claude Desktop config ────────────────────────────────────────────
header "Claude Desktop Configuration"

# On Windows, Claude Desktop needs native Windows paths in the config
if [ "$IS_WINDOWS" = true ]; then
  CONFIG_PYTHON_PATH="$(cygpath -w "$PYTHON_EXEC")"
  CONFIG_SERVER_PATH="$(cygpath -w "$REPO_DIR/server.py")"
  # Use forward slashes (Claude Desktop on Windows accepts both)
  CONFIG_PYTHON_PATH="${CONFIG_PYTHON_PATH//\\//}"
  CONFIG_SERVER_PATH="${CONFIG_SERVER_PATH//\\//}"
else
  CONFIG_PYTHON_PATH="$PYTHON_EXEC"
  CONFIG_SERVER_PATH="$REPO_DIR/server.py"
fi

if [ ! -f "$CLAUDE_CONFIG" ]; then
  step "Claude Desktop config not found — creating it..."
  mkdir -p "$(dirname "$CLAUDE_CONFIG")"
  cat > "$CLAUDE_CONFIG" <<EOF
{
  "mcpServers": {
    "ezf-sales": {
      "command": "$CONFIG_PYTHON_PATH",
      "args": ["$CONFIG_SERVER_PATH"]
    }
  }
}
EOF
  ok "Config created"
else
  step "Updating Claude Desktop config..."
  "$PYTHON_CMD" - "$CLAUDE_CONFIG" "$CONFIG_PYTHON_PATH" "$CONFIG_SERVER_PATH" <<'PYEOF'
import sys, json

config_path, python_path, server_path = sys.argv[1], sys.argv[2], sys.argv[3]

with open(config_path, "r") as f:
    config = json.load(f)

config.setdefault("mcpServers", {})
config["mcpServers"]["ezf-sales"] = {
    "command": python_path,
    "args": [server_path]
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
PYEOF
  ok "Claude Desktop config updated"
fi

# ── Step 6: Validate ──────────────────────────────────────────────────────────
header "Validating Setup"

step "Testing Python environment..."
if "$PYTHON_EXEC" -c "import mcp, requests, simple_salesforce, dotenv" 2>/dev/null; then
  ok "All packages installed correctly"
else
  warn "Package check failed. Try closing and reopening the terminal, then run setup again."
fi

step "Checking .env file..."
if [ -f "$REPO_DIR/.env" ] && grep -q "GONG_ACCESS_KEY" "$REPO_DIR/.env"; then
  ok ".env file looks good"
else
  warn ".env file missing or incomplete"
fi

step "Checking Claude Desktop config..."
if grep -q "ezf-sales" "$CLAUDE_CONFIG" 2>/dev/null; then
  ok "ezf-sales found in Claude Desktop config"
else
  warn "ezf-sales not found in Claude Desktop config — may need manual update"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  $(green "✓ Setup complete!")"
echo ""
echo "  $(bold "Last step:") Quit and reopen Claude Desktop."
echo "  Then type: $(bold "get account summary for Concord Swim")"
echo "  to verify everything is working."
echo ""
echo "  $(dim "Need help? Slack @arpit")"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
