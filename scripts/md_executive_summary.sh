#!/bin/bash

# Accept filename as argument or default to issue_body.md
FILE_NAME=${1:-executive_summary.md}

echo -e "# 📰 Daily Content Summary - $(date +'%Y-%m-%d')" > $FILE_NAME
echo -e "### Executive Summary" >> $FILE_NAME
echo -e "\n$(cat outputs/*_summary.txt 2>/dev/null || echo 'No summary generated')\n" >> $FILE_NAME