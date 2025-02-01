#!/bin/bash
set -ex

app_root=$(dirname "$(dirname "$(realpath "$0")")")

rm -rf $app_root/outputs/*
python $app_root/main.py
bash $app_root/scripts/create_issue_body.sh $app_root/outputs/issue.md