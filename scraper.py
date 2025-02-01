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

# TODO: manage session creation and closing at the top level, maybe creating a class to encapsulate the session
# TODO: see if changing to production grade browser automation tools such as playwright or puppeteer would be better in (1) performance (2) reliability (counter measure for anti-scraping measures) e.g. Enable JavaScript and cookies to continue 

async def get_page_html(url, wait_until='networkidle', timeout=SESSION_GET_TIMEOUT):
    """Shared Playwright helper to get rendered HTML"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        try:
            context = await browser.new_context(
                user_agent=HEADERS['User-Agent'],
                viewport={'width': 1920, 'height': 1080},
                java_script_enabled=True
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
            
            try:
                await page.wait_for_load_state(wait_until, timeout=timeout * 1000)
            except Exception as e:
                print(f"Error waiting for networkidle under {url}, may be due to constant background network activity such as analytics, will continue: {str(e)}")
        
            return await page.content()
        finally:
            await browser.close()

async def scrape_article(url):
    """Scrape articles using Playwright with improved PDF handling"""
    try:
        if url.lower().endswith('.pdf'):
            session = AsyncHTMLSession()
            response = await session.get(
                url,
                timeout=SESSION_GET_TIMEOUT,
                headers=HEADERS
            )
            pdf_stream = io.BytesIO(response.content)
            reader = PdfReader(pdf_stream)
            text = '\n'.join([page.extract_text() for page in reader.pages])
            return text
        
        html = await get_page_html(url)
        
        # Sanitize HTML for content extraction
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

    except Exception as e:
        print(f"Scraping error: {str(e)}")
        return ""

def clean_content(html):
    """Fast HTML sanitization"""
    return html.replace('<!--', '').replace('-->', '')\
              .replace('<noscript>', '').replace('</noscript>', '')\
              .replace('javascript:', '')

async def extract_from_index(root_url, css_selector=None, class_name=None, 
                 include_patterns=None, exclude_patterns=None):
    try:
        html = await get_page_html(root_url)
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
                    'publish_at': UNKNOWN,
                    'author': UNKNOWN,
                    'title': UNKNOWN,
                })
        
        return post_links

    except Exception as e:
        print(f"Index extraction failed: {str(e)}")
        return []

async def extract_from_rss(rss_url):
    """Extract RSS feed items with links and dates"""
    session = AsyncHTMLSession()
    try:
        response = await session.get(rss_url, timeout=SESSION_GET_TIMEOUT, headers=HEADERS)
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
    finally:
        await session.close()

async def main():
    # TODO: add support for filtering by date and remove noisy links
    hn_posts = await extract_from_index(
        "https://hn.algolia.com/?dateRange=last24h&type=story",
        **
        {
            'css_selector': 'a[href].Story_link',
        }
    )
    print(f"=== hn_posts ===\n {hn_posts} \n=== end of hn_posts ===\n")
    
    pe_posts = await extract_from_index(
        "https://blog.pragmaticengineer.com",
        **
        {
            'include_patterns': ['https://blog.pragmaticengineer.com'],
        }
    )
    print(f"=== pe_posts ===\n {pe_posts} \n=== end of pe_posts ===\n")

    rss = await extract_from_rss("https://blog.pragmaticengineer.com/rss")
    print(f"=== rss ===\n {rss} \n=== end of rss ===\n")

    article = await scrape_article("https://openai.com/index/openai-o3-mini/")
    print(f"=== article ===\n {article} \n=== end of article ===\n")
    
    pdf = await scrape_article("https://ojjdp.ojp.gov/sites/g/files/xyckuh176/files/media/document/DataSnapshot_JRFC2018.pdf")
    print(f"=== pdf ===\n {pdf} \n=== end of pdf ===\n")

if __name__ == "__main__":
    asyncio.run(main())