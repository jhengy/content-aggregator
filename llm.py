from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from requests_html import HTMLSession
import re
from scraper import scrape_article
from utils import deduplicate
from datetime import datetime

# Load environment variables
load_dotenv()

def summarize_post(text):
    """Summarize text using OpenRouter API via direct HTTP"""
    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv('SITE_URL'),
            "X-Title": os.getenv('SITE_NAME')
        }

        prompt = """Strictly follow this format:
<tags>comma,separated,tags</tags>
<date>dd-mm-yyyy</date>
<summary>3-5 sentence paragraph</summary>

Text to analyze:
{text}

Rules:
1. Use exact XML-like tags shown
2. Extract only the publish date of the post and ignore other dates.If date not found, use <date>unknown</date>
3. Summary must be plain text without markdown and enclosed within <summary></summary>
4. Tags must be lowercase, no special characters and enclosed within <tags></tags>
"""
        print("prompt:\n", prompt.format(text=text)) if os.getenv('DEBUG') == 'true' else None

        payload = {
            "model": os.getenv('MODEL_SUMMARIZE'),
            # "temperature": 0.1,
            # "top_p": 0.3,
            # "max_tokens": 300,
            # "frequency_penalty": 1.0,
            "messages": [{
                "role": "user",
                "content": prompt.format(text=text)
            }]
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        print("response:\n", response.json(), response.status_code) if os.getenv('DEBUG') == 'true' else None
        
        if response.status_code == 200:
          try:
              content = response.json()['choices'][0]['message']['content']
          except (KeyError, IndexError, TypeError):
              raise Exception("Error parsing response", response.json())
          
          # Parse structured response
          tags_match = re.search(r'<tags>(.*?)</tags>', content, re.DOTALL)
          tags = tags_match.group(1).strip() if tags_match else 'unknown'
          
          # Extract date
          date_match = re.search(r'<date>(.*?)</date>', content, re.DOTALL)
          date = date_match.group(1).strip() if date_match else 'unknown'
          
          # Extract summary
          summary_match = re.search(r'<summary>(.*?)</summary>', content, re.DOTALL)
          summary = summary_match.group(1).strip() if summary_match else 'unknown'
          
          return {
              "tags": tags,
              "date": date,
              "summary": summary
          }
        else:
          raise Exception(f"API error: {response.status_code} - {response.text}")

    except Exception as e:
        raise Exception(f"Summarization error: {str(e)}")

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
    article = scrape_article("https://www.404media.co/openai-furious-deepseek-might-have-stolen-all-the-data-openai-stole-from-us/")
    summary = summarize_post(article)
    print(summary)

if __name__ == "__main__":
    main()
