#!/usr/bin/env bash
set -e
pip install --user --upgrade pip
pip install --ignore-installed PyYAML==6.0.3
pip install -r requirements.txt
