#!/bin/bash

# Accept filename as argument or default to issue_body.md
FILE_NAME=${1:-issue_body.md}

echo -e "# 📰 Daily Content Summary - $(date +'%Y-%m-%d')" > $FILE_NAME
echo -e "### Articles Processed" >> $FILE_NAME
jq -r '.[] | "- [📄](\(.url)) \(.summary)  🏷️\(.tags) \n"' outputs/*.json >> $FILE_NAME 2>/dev/null || echo "No articles processed today" >> $FILE_NAME
echo -e "---\n### Executive Summary" >> $FILE_NAME
echo -e "\n$(cat outputs/*_summary.txt 2>/dev/null || echo 'No summary generated')\n" >> $FILE_NAME
echo -e "---\n*🤖 Automated Summary*" >> $FILE_NAME 