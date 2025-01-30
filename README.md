# Web Content Summarizer

A Python tool that scrapes web articles and generates summaries using the OpenRouter API.

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your credentials:
   - OPENROUTER_API_KEY: Your OpenRouter API key
   - SITE_URL: Your site URL
   - SITE_NAME: Your site name

## Usage

Run the script:
```bash
python openrouter_api_script.py
```

This will scrape the main content from the specified URL and generate a summary.
