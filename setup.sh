#!/bin/bash
# setup.sh - One-command setup for the trading bot

set -e

echo "========================================"
echo "  Forex Trading Bot - Setup"
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.10+."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python version: $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and fill in your credentials"
echo "2. Run: source venv/bin/activate && python main.py"
echo ""
echo "Required: OANDA practice account + API key"
echo "Optional: Telegram bot token, Groq API key"
echo ""
