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

## Usage

Run the script:
```bash
python main.py
```

This will scrape the main content from the specified URL and generate a summary.


## Challenges
- different sources have different ways of getting the post links
  - tricky to eliminate links which are not posts: save model cost by excluding links which are irrelevant
- non-deterministic output within and across models
  - same model can output different results with the same prompt
  - different models different output formats depending on the prompt -> hard to parse response in a consistent way
- reliability
  - slowness, causing timeouts
  - rate limiting causing errors
   - retry logic
- extract date from the post
  - llm can hallucinate date

- extracting blog content from url
  - support for dynamic content

- identify the best model for the task
  - criteria
    - reliability
    - quality of output
    - cost
    - speed

  - possible options
    - Gemini Flash 1.5 8B Experimental
    - Gemma 2 9B (free)
    - Qwen 2 7B Instruct (free)
    - Llama 3.2 11B Vision Instruct (free)

- free providers
  - google ai studio
    - https://ai.google.dev/gemini-api/docs/models/gemini
    - https://ai.google.dev/pricing#1_5flash
      - 15 RPM (requests per minute)
      - 1 million TPM (tokens per minute)
      - 1,500 RPD (requests per day)
  - OpenRouter: https://openrouter.ai/docs/limits
    - Free limit: If you are using a free model variant (with an ID ending in :free), then you will be limited to 20 requests per minute and 200 requests per day.
  - huggings face serverless inference api
    - https://huggingface.co/docs/api-inference/en/rate-limits
     - Signed-up Users	1,000 requests per day
