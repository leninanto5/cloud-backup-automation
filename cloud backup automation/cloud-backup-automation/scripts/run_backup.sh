#!/bin/sh
# Runs one backup (Linux / Mac)
cd "$(dirname "$0")/.." || exit 1
python3 backup.py
