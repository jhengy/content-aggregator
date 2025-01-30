from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from requests_html import HTMLSession
import re

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

def summarize(text):
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

def validate_response(content):
    # Check required tags
    if not re.search(r'<tags>.+</tags>', content):
        raise ValueError("Missing tags section")
    if not re.search(r'<date>.+</date>', content):
        raise ValueError("Missing date section")
    if not re.search(r'<summary>.+</summary>', content):
        raise ValueError("Missing summary section")
    return content

def main():
    article = scrape_article("https://www.404media.co/openai-furious-deepseek-might-have-stolen-all-the-data-openai-stole-from-us/")
    summary = summarize(article)
    print(summary)

if __name__ == "__main__":
    main()
