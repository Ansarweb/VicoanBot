#!/bin/bash

set -e

echo "Starting VicoanBot..."

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Starting bot..."
python bot.py
