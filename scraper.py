import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from requests_html import AsyncHTMLSession
import re
from utils import deduplicate
from urllib.parse import urljoin
import asyncio
from playwright.async_api import async_playwright
import feedparser
from datetime import datetime
import time

# Load environment variables
load_dotenv()

# TODO: manage session creation and closing at the top level, maybe creating a class to encapsulate the session
async def scrape_article(url):
    """Async scraping with proper JS rendering"""
    session = AsyncHTMLSession()
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://google.com/',
        }
        
        # Configure timeouts from environment
        timeout = int(os.getenv('REQUEST_TIMEOUT', 20))
        
        # Fetch page with browser-like headers
        response = await session.get(
            url,
            timeout=timeout,
            headers=headers
        )
        
        await response.html.arender(timeout=10, sleep=3)

        # Clean content before parsing
        cleaned_html = clean_content(response.html.html)
        
        # Parse with optimized settings
        soup = BeautifulSoup(cleaned_html, 'html.parser')
        
        # Remove non-content elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 
                        'aside', 'form', 'svg', 'link', 'meta']):
            tag.decompose()
            
        # Find main content using multiple heuristics
        main_content = (
            soup.find('article') or 
            soup.find('main') or 
            soup.find('div', role='main') or 
            soup.find(class_=['article', 'content', 'post']) or 
            soup.body
        )
        
        # Final text cleaning
        text = main_content.get_text(separator='\n', strip=True)
        print(f"=== extracted text ===\n {text} \n=== end of extracted text ===\n") if os.getenv('DEBUG') == 'true' else None
        return '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        
    except Exception as e:
        print(f"Scraping error: {str(e)}")
        return ""
    finally:
        await session.close()

def clean_content(html):
    """Fast HTML sanitization"""
    return html.replace('<!--', '').replace('-->', '')\
              .replace('<noscript>', '').replace('</noscript>', '')\
              .replace('javascript:', '')

async def extract_from_index(root_url, css_selector=None, class_name=None, 
                 include_patterns=None, exclude_patterns=None):
    session = AsyncHTMLSession()
    try:
        response = await session.get(root_url)
        await response.html.arender(timeout=10, sleep=3)
        
        soup = BeautifulSoup(response.html.html, 'html.parser')
        post_links = []
        
        # Base query for all links
        links = soup.find_all('a', href=True)
        
        # Apply filters
        if css_selector:
            links = soup.select(css_selector)
        elif class_name:
            links = [link for link in links if class_name in link.get('class', [])]
        
        for link in links:
            url = urljoin(root_url, link['href'])
            
            # Inclusion check
            include = True
            if include_patterns:
                include = any(pattern in url for pattern in include_patterns)
            
            # Exclusion check
            if exclude_patterns and any(pattern in url for pattern in exclude_patterns):
                include = False
                
            if include:
                post_links.append(url)
        
        return deduplicate(post_links)
    except Exception as e:
        print(f"Rendering failed: {str(e)}")
        return None
    finally:
        await session.close()
    
async def extract_from_rss(rss_url):
    """Extract RSS feed items with links and dates"""
    session = AsyncHTMLSession()
    try:
        response = await session.get(rss_url)
        if response.status_code == 200:
            feed = feedparser.parse(response.text)
            items = []
            
            for entry in feed.entries:
                # Get absolute URL
                link = urljoin(rss_url, entry.link) if entry.link else None
                
                # Parse date from multiple possible fields
                date_fields = [
                    entry.get('published_parsed'),
                    entry.get('updated_parsed'),
                    entry.get('created_parsed')
                ]
                pub_date = next(
                    (int(time.mktime(dt)) for dt in date_fields if dt),  # Convert to epoch timestamp
                    None
                )
                
                if link:  # Only include entries with valid links
                    items.append({
                        'link': link,
                        'publish_at': pub_date  # Now stores epoch timestamp
                    })
                    
            return items
            
        return []
    except Exception as e:
        print(f"RSS Error: {str(e)}")
        return []
    finally:
        await session.close()

async def main():
    # TODO: add support for filtering by date and remove noisy links
    pe_posts = await extract_from_index(
        "https://blog.pragmaticengineer.com",
        **
        {
            'include_patterns': ['https://blog.pragmaticengineer.com'],
        }
    )
    print(f"=== pe_posts ===\n {pe_posts} \n=== end of pe_posts ===\n")

    hn_posts = await extract_from_index(
        "https://hn.algolia.com/?dateRange=last24h&type=story",
        **
        {
            'css_selector': 'a[href].Story_link'
        }
    )
    print(f"=== hn_posts ===\n {hn_posts} \n=== end of hn_posts ===\n")
    
    rss = await extract_from_rss("https://blog.pragmaticengineer.com/rss")
    print(f"=== rss ===\n {rss} \n=== end of rss ===\n")

    article = await scrape_article("https://openai.com/index/openai-o3-mini/")
    print(f"=== article ===\n {article} \n=== end of article ===\n")

if __name__ == "__main__":
    asyncio.run(main())