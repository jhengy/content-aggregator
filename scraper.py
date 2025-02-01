import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from requests_html import AsyncHTMLSession
from utils import deduplicate
from urllib.parse import urljoin
import asyncio
import feedparser
import time

# Load environment variables
load_dotenv()

UNKNOWN = ""
SESSION_GET_TIMEOUT = 20
SESSION_RENDER_TIMEOUT = 30
SESSION_RENDER_SLEEP = 3
SESSION_RENDER_RETRIES = 3

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://google.com/',
    'Sec-CH-UA': '"Chromium";v="116", "Not)A;Brand";v="24"',
    'Sec-CH-UA-Platform': '"Windows"',
    'Sec-CH-UA-Mobile': '?0',
}

# TODO: manage session creation and closing at the top level (now implemented via Scraper class)
class Scraper:
    def __init__(self):
        self.session = None

    async def __aenter__(self):
        """Initialize shared session on context entry"""
        self.session = AsyncHTMLSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup session on context exit"""
        await self.session.close()
        self.session = None

    async def scrape_article(self, url):
        """Async scraping with proper JS rendering"""
        # TODO: consider changing to playwright/puppeteer for production use
        try:
            response = await self.session.get(
                url,
                timeout=SESSION_GET_TIMEOUT,
                headers=HEADERS
            )
            
            COOKIES = response.cookies
            
            await response.html.arender(
                timeout=SESSION_RENDER_TIMEOUT,
                sleep=SESSION_RENDER_SLEEP,
                retries=SESSION_RENDER_RETRIES,
                cookies=COOKIES
            )

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

    async def extract_from_index(self, root_url, css_selector=None, class_name=None,
                                include_patterns=None, exclude_patterns=None):
        """Index extraction using shared session"""
        try:
            response = await self.session.get(root_url, timeout=SESSION_GET_TIMEOUT, headers=HEADERS)
            await response.html.arender(
                timeout=SESSION_RENDER_TIMEOUT,
                sleep=SESSION_RENDER_SLEEP,
                retries=SESSION_RENDER_RETRIES
            )
            
            soup = BeautifulSoup(response.html.html, 'html.parser')
            
            # Base query for all links
            links = soup.find_all('a', href=True)
            
            # Apply filters
            if css_selector:
                links = soup.select(css_selector)
            elif class_name:
                links = [link for link in links if class_name in link.get('class', [])]
            
            post_links = []
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
                    post_links.append({
                        'url': url,
                        'publish_at': UNKNOWN,
                        'author': UNKNOWN,
                        'title': UNKNOWN,
                    })
            
            return post_links
        except Exception as e:
            print(f"Rendering failed: {str(e)}")
            return None

    async def extract_from_rss(self, rss_url):
        """RSS extraction using shared session"""
        try:
            response = await self.session.get(rss_url, timeout=SESSION_GET_TIMEOUT, headers=HEADERS)
            if response.status_code == 200:
                feed = feedparser.parse(response.text)
                items = []
                
                for entry in feed.entries:
                    # Get absolute URL
                    url = urljoin(rss_url, entry.link) if entry.link else None
                    
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
                    
                    if url:  # Only include entries with valid links
                        items.append({
                            'url': url,
                            'publish_at': pub_date,  # Now stores epoch timestamp
                            'author': entry.get('author') or UNKNOWN,
                            'title': entry.get('title') or UNKNOWN
                        })
                        
                return items
                
            return []
        except Exception as e:
            print(f"RSS Error: {str(e)}")
            return []

# Update main function to use shared session
async def main():
    # TODO: add support for filtering by date and remove noisy links
    async with Scraper() as scraper:
        pe_posts = await scraper.extract_from_index(
            "https://blog.pragmaticengineer.com",
            include_patterns=['https://blog.pragmaticengineer.com']
        )
        print(f"=== pe_posts ===\n {pe_posts} \n=== end of pe_posts ===\n")

        hn_posts = await scraper.extract_from_index(
            "https://hn.algolia.com/?dateRange=last24h&type=story",
            css_selector='a[href].Story_link'
        )
        print(f"=== hn_posts ===\n {hn_posts} \n=== end of hn_posts ===\n")
        
        rss = await scraper.extract_from_rss("https://blog.pragmaticengineer.com/rss")
        print(f"=== rss ===\n {rss} \n=== end of rss ===\n")

        article = await scraper.scrape_article("https://openai.com/index/openai-o3-mini/")
        print(f"=== article ===\n {article} \n=== end of article ===\n")

def clean_content(html):
    """Fast HTML sanitization"""
    return html.replace('<!--', '').replace('-->', '')\
              .replace('<noscript>', '').replace('</noscript>', '')\
              .replace('javascript:', '')

if __name__ == "__main__":
    asyncio.run(main())