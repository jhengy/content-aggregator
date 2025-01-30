from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv
from requests_html import HTMLSession

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

        payload = {
            "model": "meta-llama/llama-3.1-70b-instruct:free",
            "messages": [{
                "role": "user",
                "content": f"Summarize this text in under five bullet points covering all aspects, first line gives a list of tags based on the content, second line the published date in the format dd-mm-yyyy if any:\n{text}"
            }]
        }

        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        return f"API error: {response.status_code} - {response.text}"

    except Exception as e:
        return f"Summarization error: {str(e)}"

def main():
    article = scrape_article("https://blog.pragmaticengineer.com/are-llms-making-stackoverflow-irrelevant")
    summary = summarize(article)
    print(summary)

if __name__ == "__main__":
    main()
