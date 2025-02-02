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
from PyPDF2 import PdfReader
import io
from playwright.async_api import async_playwright
from typing import Dict, List, Optional, Any

# Load environment variables
load_dotenv()

class Scraper:
    """Handles all scraping operations including article extraction and processing"""
    
    UNKNOWN = ""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://google.com/',
            'Sec-CH-UA': '"Chromium";v="116", "Not)A;Brand";v="24"',
            'Sec-CH-UA-Platform': '"Windows"',
            'Sec-CH-UA-Mobile': '?0',
        }
        self.timeouts = {
            'get': 20,
            'render': 30,
            'render_sleep': 3,
            'render_retries': 3
        }

    # Public interface methods
    async def extract_from_index(
        self,
        root_url: str,
        css_selector: Optional[str] = None,
        class_name: Optional[str] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """Extract articles from index pages"""
        try:
            html = await self._get_page_html(root_url)
            print(f"=== extract_from_index html ===\n {html} \n=== end of extract_from_index html ===\n") if os.getenv('DEBUG') == 'true' else None
            
            soup = BeautifulSoup(html, 'html.parser')
            links = soup.find_all('a', href=True)
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
                        'publish_at': Scraper.UNKNOWN,
                        'author': Scraper.UNKNOWN,
                        'title': Scraper.UNKNOWN,
                    })
            
            return post_links

        except Exception as e:
            print(f"Index extraction failed: {str(e)}")
            return []

    async def extract_from_rss(self, rss_url: str) -> List[Dict[str, Any]]:
        """Extract articles from RSS feeds"""
        session = AsyncHTMLSession()
        try:
            response = await session.get(rss_url, timeout=self.timeouts['get'], headers=self.headers)
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
                            'author': entry.get('author') or Scraper.UNKNOWN,
                            'title': entry.get('title') or Scraper.UNKNOWN
                        })
                        
                return items
                
            return []
        except Exception as e:
            print(f"RSS Error: {str(e)}")
            return []
        finally:
            await session.close()

    async def scrape_article(self, url: str) -> str:
        """Main entry point for article scraping"""
        try:
            if url.lower().endswith('.pdf'):
                return await self._process_pdf(url)
            return await self._process_html(url)
        except Exception as e:
            print(f"Scraping error: {str(e)}")
            return ""

    def _clean_content(self, html: str) -> str:
        """Sanitize HTML content"""
        return html.replace('<!--', '').replace('-->', '')\
                  .replace('<noscript>', '').replace('</noscript>', '')\
                  .replace('javascript:', '')

    # Private helper methods
    async def _get_page_html(self, url: str, wait_until: str = 'networkidle') -> str:
        """Get rendered HTML using Playwright with configurable timeouts"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            try:
                context = await browser.new_context(
                    user_agent=self.headers['User-Agent'],
                    viewport={'width': 1920, 'height': 1080},
                    java_script_enabled=True
                )
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", 
                              timeout=self.timeouts['get'] * 1000)
                
                try:
                    await page.wait_for_load_state(wait_until, 
                                                 timeout=self.timeouts['get'] * 1000)
                except Exception as e:
                    print(f"Timeout waiting for {url}: {str(e)}")
                
                return await page.content()
            finally:
                await browser.close()

    async def _process_pdf(self, url: str) -> str:
        """Handle PDF content extraction"""
        session = AsyncHTMLSession()
        try:
            response = await session.get(url, timeout=self.timeouts['get'], headers=self.headers)
            pdf_stream = io.BytesIO(response.content)
            reader = PdfReader(pdf_stream)
            return '\n'.join([page.extract_text() for page in reader.pages])
        finally:
            await session.close()

    async def _process_html(self, url: str) -> str:
        """Handle HTML content extraction"""
        html = await self._get_page_html(url)
        
        soup = BeautifulSoup(html, 'html.parser')
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
        text = main_content.get_text(separator='\n', strip=True)
        extracted_text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
        
        print(f"=== extracted text ===\n {extracted_text} \n=== end of extracted text ===\n") if os.getenv('DEBUG') == 'true' else None
        return extracted_text

async def main():
    scraper = Scraper()
    
    # Hacker News example
    hn_posts = await scraper.extract_from_index(
        root_url="https://hn.algolia.com/?dateRange=last24h&type=story",
        css_selector='a[href].Story_link'
    )
    print(f"=== hn_posts ===\n {hn_posts} \n=== end of hn_posts ===\n")
    
    # Pragmatic Engineer blog example
    pe_posts = await scraper.extract_from_index(
        root_url="https://blog.pragmaticengineer.com",
        include_patterns=['https://blog.pragmaticengineer.com']
    )
    print(f"=== pe_posts ===\n {pe_posts} \n=== end of pe_posts ===\n")

    # RSS feed example
    rss = await scraper.extract_from_rss("https://blog.pragmaticengineer.com/rss")
    print(f"=== rss ===\n {rss} \n=== end of rss ===\n")

    # Article scraping examples
    article = await scraper.scrape_article("https://openai.com/index/openai-o3-mini/")
    print(f"=== article ===\n {article} \n=== end of article ===\n")
    
    pdf = await scraper.scrape_article("https://ojjdp.ojp.gov/sites/g/files/xyckuh176/files/media/document/DataSnapshot_JRFC2018.pdf")
    print(f"=== pdf ===\n {pdf} \n=== end of pdf ===\n")
    
    reuter_captcha = await scraper.scrape_article("https://www.reuters.com/world/us/trump-admin-take-down-most-government-websites-5-pm-cbs-reports-2025-01-31/")
    print(f"=== reuter_captcha ===\n {reuter_captcha} \n=== end of reuter_captcha ===\n")

if __name__ == "__main__":
    asyncio.run(main())