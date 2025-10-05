#!/bin/bash

# Helios Trading System V3.0 - Startup Script
# This script starts the application with proper environment setup

echo "=================================================="
echo "  Helios Trading System V3.0 - Starting Up"
echo "=================================================="
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  WARNING: .env file not found!"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "✓ .env file created. Please edit it with your actual credentials."
    echo ""
    echo "Required variables to configure:"
    echo "  - POSTGRES_PASSWORD"
    echo "  - VALR_API_KEY"
    echo "  - VALR_API_SECRET"
    echo "  - ANTHROPIC_API_KEY (for LLM)"
    echo "  - OPENAI_API_KEY (for LLM backup)"
    echo ""
    read -p "Press Enter to continue after editing .env file..."
fi

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"
echo ""

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing/updating dependencies..."
pip install -q -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Create necessary directories
echo "Creating directories..."
mkdir -p logs models database/migrations tests
echo "✓ Directories created"
echo ""

# Check if database is running (optional)
echo "Checking database connectivity..."
if command -v psql &> /dev/null; then
    if psql -h localhost -U helios -d helios_v3 -c "SELECT 1" &> /dev/null; then
        echo "✓ PostgreSQL connection successful"
    else
        echo "⚠️  WARNING: Cannot connect to PostgreSQL"
        echo "Make sure PostgreSQL is running and credentials are correct"
    fi
else
    echo "⚠️  psql not found, skipping database check"
fi
echo ""

echo "=================================================="
echo "  Starting Helios Trading System V3.0"
echo "=================================================="
echo ""

# Start the application
python main_v3.py
