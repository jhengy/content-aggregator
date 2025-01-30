from openai import OpenAI
import requests
from bs4 import BeautifulSoup
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def scrape_article(url):
    """Scrape main content from a webpage"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract text from common content containers
        main_content = soup.find(['article', 'main']) or soup.body
        if not main_content:
            raise ValueError("Could not find main content")
        return main_content.get_text(separator=' ', strip=True)
    
    except Exception as e:
        return f"Scraping error: {str(e)}"

def summarize(text):
    """Summarize text using OpenRouter API"""
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv('OPENROUTER_API_KEY'),
        )

        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": os.getenv('SITE_URL'),
                "X-Title": os.getenv('SITE_NAME'),
            },
            model="meta-llama/llama-3.1-70b-instruct:free",
            messages=[
                {
                    "role": "user",
                    "content": f"Summarize this text in under five bullet points covering all aspects, first line gives a list of tags based on the content, second line the published date in the format dd-mm-yyyy if any:\n{text}",
                }
            ]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"Summarization error: {str(e)}"

def main():
    article = scrape_article("https://blog.pragmaticengineer.com/are-llms-making-stackoverflow-irrelevant")
    summary = summarize(article)
    print(summary)

if __name__ == "__main__":
    main()
