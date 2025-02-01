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

def summarize_all(summaries):
    """Generate an executive summary from multiple summaries using LLM"""
    if len(summaries) == 0:
        return "No summaries to summarize"

    try:
        combined = "\n".join(summaries)
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv('SITE_URL'),
            "X-Title": os.getenv('SITE_NAME')
        }
        
        prompt = """Generate an executive summary under 200 words from these key points:
        Text to analyze:
        {text}
        
        Rules:
        1. Use plain text only in a single paragraph
        2. Maintain crucial details
        3. Avoid markdown
        4. Keep paragraphs short
        """
        
        payload = {
            "model": os.getenv('MODEL_SUMMARIZE'),
            "messages": [{
                "role": "user",
                "content": prompt.format(text=combined)
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
            return content
        else:
            raise Exception(f"API error: {response.status_code} - {response.text}")

    except Exception as e:
        print(f"Summary aggregation failed: {str(e)}")
        return "\n".join(summaries)  # Fallback to original behavior

def summarize_post(text):
    """Summarize text using OpenRouter API via direct HTTP"""
    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv('SITE_URL'),
            "X-Title": os.getenv('SITE_NAME')
        }
        
        prompt = """
You are an AI assistant specialized in summarizing and extracting metadata from articles. Your task is to summarize the article and extract the publication date.
Instructions:
1. Carefully read the entire blog text provided.
2. Extract the publication date as [Publication Date], if not found, return unknown
3. Summarize article in 3-5 sentences as [Summary] and tags as [Tags] in lowercase, no special characters, comma separated
4. Present your findings strictly following the specified format:
<tags>[Tags]</tags>
<date>[Publication Date]</date>
<summary>[Summary]</summary>

Article text:
{text}
        
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
          tags = tags_match.group(1).strip() if tags_match else None
          
          # Extract date
          date_match = re.search(r'<date>(.*?)</date>', content, re.DOTALL)
          date = date_match.group(1).strip() if date_match else None
          
          # Extract summary
          summary_match = re.search(r'<summary>(.*?)</summary>', content, re.DOTALL)
          summary = summary_match.group(1).strip() if summary_match else None
          
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

def main():
    article = scrape_article("https://www.tomshardware.com/pc-components/hdds/german-seagate-customers-say-their-new-hard-drives-were-actually-used-resold-hdds-reportedly-used-for-tens-of-thousands-of-hours")
    summary = summarize_post(article)
    print(summary)

if __name__ == "__main__":
    main()
