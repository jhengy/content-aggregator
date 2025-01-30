from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def extract_date_with_llama(html_content):
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
                "model": "meta-llama/llama-3-70b-instruct:free",
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

def extract_posts(blog_homepage):
    response = requests.get(blog_homepage)
    base_domain = urlparse(blog_homepage).netloc

    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        post_links = set()
        for link in soup.find_all('a', href=True):
            url = urljoin(blog_homepage, link['href'])
            if urlparse(url).netloc == base_domain and url != blog_homepage:
                post_links.add(url)

        return post_links       
    else:
        print(f"Failed to retrieve the webpage: {response.status_code}")
        return None
    
    
def filter_by_date(post_links, target_date_str):
    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    blog_urls = set()

    # Second pass: Verify dates using AI
    for url in post_links:
        try:
            post_response = requests.get(url, timeout=10)
            if post_response.status_code == 200:
                ai_date = extract_date_with_llama(post_response.text)
                if ai_date and ai_date != 'null':
                    print(f"url: {url}\n ai_date: {ai_date}\n")
                    post_date = datetime.strptime(ai_date, "%Y-%m-%d").date()
                    if post_date == target_date:
                        blog_urls.add(url)
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")

    return blog_urls

def main():
    posts = extract_posts("https://blog.pragmaticengineer.com")
    print(posts)
    filtered_posts = filter_by_date(posts, "2025-01-21")
    print(filtered_posts)

if __name__ == "__main__":
    main()