#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
pip install --user --upgrade pip
pip install --ignore-installed PyYAML==6.0.3 cryptography cffi
pip install -r requirements.txt
