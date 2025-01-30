from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup

"""
1. identify urls (1) blog article (2) of the latest date
"""
def extract_blog_urls(blog_homepage):
    # Send a GET request to fetch the HTML content
    response = requests.get(blog_homepage)
    base_domain = urlparse(blog_homepage).netloc
    
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Set to store unique blog URLs
        blog_urls = set()
        
        # Find all anchor tags
        for link in soup.find_all('a'):
            resolved_urls = urljoin(blog_homepage, link.get('href'))
            # Check if the href is valid and contains 'blog' (adjust this condition as needed)
            if resolved_urls and urlparse(resolved_urls).netloc == base_domain:
                blog_urls.add(resolved_urls)

        return blog_urls
    else:
        print(f"Failed to retrieve the webpage: {response.status_code}")
        return None
    
urls = extract_blog_urls("https://www.v2ex.com/go/share")
print(urls)