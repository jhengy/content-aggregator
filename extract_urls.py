from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
from dotenv import load_dotenv
from requests_html import HTMLSession
from utils import deduplicate

load_dotenv()

def extract_date_llm(html_content):
    prompt = """Analyze this HTML and find the publication date in YYYY-MM-DD format.
    Look for dates in article headers, meta tags, or visible date elements, exclude dates in the article body
    Return ONLY the date in ISO format within curly braces or 'null' if not found."""
    
    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "HTTP-Referer": "https://github.com/your-repo",  # Required by OpenRouter
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": os.getenv('MODEL_EXTRACT_DATE'),
                "messages": [{
                    "role": "user",
                    "content": f"{prompt}\n\n{html_content[:8000]}"
                }]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content'].strip().replace("{", "").replace("}", "")
        return None
    except Exception as e:
        print(f"AI date extraction failed: {str(e)}")
        return None

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
    
    
def filter_by_date(post_links, target_date_str):
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    blog_urls = []

    for url in post_links:
        try:
            post_response = requests.get(url, timeout=10)
            if post_response.status_code == 200:
                ai_date = extract_date_llm(post_response.text)
                if ai_date and ai_date != 'null':
                    print(f"url: {url}\n ai_date: {ai_date}\n") if os.getenv('DEBUG') == 'true' else None
                    post_date = datetime.strptime(ai_date, "%Y-%m-%d").date()
                    if post_date == target_date:
                        blog_urls.append(url)
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")

    return deduplicate(blog_urls)

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