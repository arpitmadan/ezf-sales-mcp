#!/bin/bash
# EZFacility Sales MCP — one-command setup
set -e

echo ""
echo "Setting up EZF Sales MCP..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "Done. Next steps:"
echo ""
echo "  1. Copy .env.example to .env and fill in your credentials:"
echo "       cp .env.example .env"
echo ""
echo "  2. Add this to your Claude Desktop config (~/.claude/claude_desktop_config.json):"
echo ""
echo '       "ezf-sales": {'
echo '         "command": "'$(pwd)'/venv/bin/python",'
echo '         "args": ["'$(pwd)'/server.py"]'
echo '       }'
echo ""
echo "  3. Restart Claude Desktop."
echo ""
