import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from requests_html import HTMLSession
import re
from utils import deduplicate
from urllib.parse import urljoin

# Load environment variables
load_dotenv()

def scrape_article(url):
    """Scrape main content from a webpage"""
    session = HTMLSession()
    try:
        response = session.get(url)
        response.html.render(timeout=20, sleep=3)
        
        soup = BeautifulSoup(response.html.html, 'html.parser')
        
        # Extract text from common content containers
        main_content = soup.find(['article', 'main']) or soup.body
        if not main_content:
            raise ValueError("Could not find main content")
        return main_content.get_text(separator=' ', strip=True)
    except Exception as e:
        print(f"Rendering failed: {str(e)}")
        return None
    finally:
        session.close()
        
        
def extract_posts(root_url, css_selector=None, class_name=None, 
                 include_patterns=None, exclude_patterns=None):
    session = HTMLSession()
    try:
        response = session.get(root_url)
        response.html.render(timeout=20, sleep=3)
        
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
        session.close()
    

def main():
    # print("--------------------------------")
    # pe_posts = extract_posts(
    #     "https://blog.pragmaticengineer.com",
    #     **
    #     {
    #         'include_patterns': ['https://blog.pragmaticengineer.com'],
    #     }
    # )
    # print(f"pe_posts: {pe_posts}")
    # filtered_pe_posts = filter_by_date(pe_posts, "2025-01-29")
    # print(f"filtered_pe_posts: {filtered_pe_posts}")
    
    # print("--------------------------------")
    # pe_newsletter_posts = extract_posts(
    #     "https://newsletter.pragmaticengineer.com/archive",
    #     **
    #     {
    #         'include_patterns': ['https://newsletter.pragmaticengineer.com/p/'],
    #     }
    # )
    # print(f"pe_newsletter_posts: {pe_newsletter_posts}")
    

    print("--------------------------------")
    hn_posts = extract_posts(
        "https://hn.algolia.com/?dateRange=last24h&type=story",
        **
        {
            'css_selector': 'a[href].Story_link'
        }
    )
    print(f"hn_posts: {hn_posts}")
    # filtered_hn_posts = filter_by_date(hn_posts, "2025-01-29")
    # print(f"filtered_hn_posts: {filtered_hn_posts}")


if __name__ == "__main__":
    main()