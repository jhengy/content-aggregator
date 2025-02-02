import pytest
from content_aggregator.scraper import Scraper

@pytest.fixture(scope="module")
def scraper():
    return Scraper()

@pytest.mark.external
@pytest.mark.asyncio
async def test_hn_scraping(scraper):
    """Test Hacker News index scraping"""
    hn_posts = await scraper.extract_from_index(
        root_url="https://hn.algolia.com/?dateRange=last24h&type=story",
        css_selector='a[href].Story_link'
    )
    
    assert len(hn_posts) > 0, "Should find Hacker News posts"
    assert all(post['url'].startswith('https://') for post in hn_posts), "URLs should be valid"

@pytest.mark.external
@pytest.mark.asyncio
async def test_pe_blog_scraping(scraper):
    """Test Pragmatic Engineer blog scraping"""
    pe_posts = await scraper.extract_from_index(
        root_url="https://blog.pragmaticengineer.com",
        include_patterns=['https://blog.pragmaticengineer.com']
    )
    
    assert len(pe_posts) > 0, "Should find blog posts"
    assert all('pragmaticengineer.com' in post['url'] for post in pe_posts), "All URLs should match include pattern"

@pytest.mark.external
@pytest.mark.asyncio
async def test_rss_feed_parsing(scraper):
    """Test RSS feed parsing"""
    rss = await scraper.extract_from_rss("https://blog.pragmaticengineer.com/rss")
    
    assert len(rss) > 0, "Should parse RSS feed entries"
    assert all(post['publish_at'] is not None for post in rss), "RSS entries should have publish dates"

@pytest.mark.external
@pytest.mark.asyncio
async def test_article_scraping(scraper):
    """Test article content scraping"""
    # Test HTML article
    html_content = await scraper.scrape_article("https://openai.com/index/openai-o3-mini/")
    assert len(html_content) > 500, "HTML content should be substantial"
    print(f"=== html_content ===\n {html_content} \n=== end of html_content ===\n")
    
    # Test PDF
    pdf_content = await scraper.scrape_article("https://ojjdp.ojp.gov/sites/g/files/xyckuh176/files/media/document/DataSnapshot_JRFC2018.pdf")
    assert "Juvenile" in pdf_content, "PDF content should be extracted"
    
    # Test problematic URL (captcha)
    captcha_content = await scraper.scrape_article("https://www.reuters.com/world/us/trump-admin-take-down-most-government-websites-5-pm-cbs-reports-2025-01-31/")
    assert len(captcha_content) < 100 or "captcha" in captcha_content.lower(), "Should handle CAPTCHA pages"