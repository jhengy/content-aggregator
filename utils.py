import requests
from datetime import datetime
import os

def deduplicate(array):
    return list(dict.fromkeys(array))


async def filter_by_date(post_links, target_date_str, date_extractor):
    """Filter posts by date using provided date extraction function"""
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    blog_urls = []

    for url in post_links:
        try:
            post_response = requests.get(url, timeout=10)
            if post_response.status_code == 200:
                ai_date = await date_extractor(post_response.text)
                if ai_date and ai_date != 'null':
                    print(f"url: {url}\n ai_date: {ai_date}\n") if os.getenv('DEBUG') == 'true' else None
                    post_date = datetime.strptime(ai_date, "%Y-%m-%d").date()
                    if post_date == target_date:
                        blog_urls.append(url)
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")

    return deduplicate(blog_urls)