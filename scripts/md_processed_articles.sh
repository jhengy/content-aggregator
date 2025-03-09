#!/bin/bash

# Accept filename as argument or default to issue_body.md
FILE_NAME=${1:-processed_articles.md}

echo -e "---\n### Articles Processed" >> $FILE_NAME
echo -e "| 📑 Article | 👤 Author | 📄 Summary | 🏷️ Tags |" >> $FILE_NAME
echo -e "|---------|-----------|-----------|--------|" >> $FILE_NAME
jq -r '.[] | "| [🔗](\(.url)) \(.title) | \(.author) | \(.summary) | \(.tags) |"' outputs/*.json >> $FILE_NAME 2>/dev/null || echo "No articles processed today" >> $FILE_NAME
echo -e "---\n*🤖 Automated Report [$(date +'%Y-%m-%d %H:%M:%S %Z')]*" >> $FILE_NAME 
