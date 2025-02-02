# Web Content Summarizer

A Python tool that aggregates and summarizes web content using AI. Features include:

## Features

| Feature                | Description                                                                 | Status |
|------------------------|-----------------------------------------------------------------------------|--------|
| Web Scraping           | Extract articles from websites and blogs                                    | ✅     |
| AI Summarization       | Generate concise summaries using Gemini models                             | ✅     |
| RSS Feed Support       | Process content from RSS/Atom feeds                                         | ✅     |
| PDF Processing         | Extract text content from PDF documents                                     | ✅     |
| CI/CD Integration     | Automated daily summaries via GitHub Actions                               | ✅     |
| Date Filtering         | Filter content by publication date                                         | ✅     |
| Dynamic Content        | Handle JavaScript-rendered pages using Playwright                          | ✅     |

## Setup

### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/content-aggregator.git
cd content-aggregator

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install with dependencies
pip install -e .
playwright install chromium
playwright install-deps
```

### Configuration
1. Create `.env` file:
    ```bash
    cp .env.example .env
    ```
2. Edit `.env` with your Gemini API details:
    ```env
    GEMINI_API_KEY=your_api_key_here
    GEMINI_MODEL_SUMMARIZE=gemini-2.0-flash-exp
    GEMINI_MODEL_DATE_EXTRACT=gemini-2.0-flash-exp
    ```

## Usage

### Basic Usage
```bash
# Run aggregator and generate issue
scripts/run.sh
```

### CLI Commands
| Command                | Description                                 | Example                          |
|------------------------|---------------------------------------------|----------------------------------|
| `run`                 | Default aggregation process                | `content-aggregator run`         |

### Testing
```bash
# Install with development dependencies
pip install -e '.[dev]'

# Run all tests
pytest tests/ -v -s

# Generate coverage report
pytest --cov=content_aggregator --cov-report=html -s
```

### Automated Daily Summaries
[![CI](https://github.com/jhengy/content-aggregator/actions/workflows/run.yml/badge.svg)](https://github.com/jhengy/content-aggregator/issues)

The GitHub Actions workflow:
- Runs daily (off-peak time)
- Processes configured content sources
- Creates GitHub issues with summaries
- Stores JSON results and summaries as artifacts

Output files will be created in:
- `outputs/results_*.json`: Full results in JSON format
- `outputs/results_*_summary.txt`: Executive summary text file

## CI/CD Requirements
For GitHub Actions execution, ensure these repository settings:
1. Under Settings > Actions > General:
   - Workflow permissions: "Read and write permissions"
   - Check "Allow GitHub Actions to create and approve pull requests"
2. Add these secrets:
   - GEMINI_API_KEY
   - GEMINI_MODEL_SUMMARIZE
   - GEMINI_MODEL_DATE_EXTRACT

## Challenges
- different sources have different ways of getting the post links
  - tricky to eliminate links which are not posts: save model cost by excluding links which are irrelevant
- non-deterministic output within and across models
  - same model can output different results with the same prompt
  - different models different output formats depending on the prompt -> hard to parse response in a consistent way
- reliability
  - speed issue: slowness, causing timeouts
  - rate limiting causing errors
   - retry logic
- quality of output
  - not always accurate, hallucinations can happen
  - not always relevant
  - not always useful
  - not always interesting
  - not always surprising
- cost
  - expensive to host and run on your own
  - expensive to run on a cloud provider for better models
- extract date from the post
  - llm can hallucinate date

- extracting blog content from url
  - support for dynamic content

- too many models to choose from

## Identify the best model for the task
- criteria
  - reliability
  - quality of output
  - cost

- possible options
  - Gemini Flash 1.5 8B Experimental
  - Gemma 2 9B (free)
  - Qwen 2 7B Instruct (free)
  - Llama 3.2 11B Vision Instruct (free)

- free providers (true as of the time of writing)
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


## TODO
- model dependent features
  - input
    - accept image
    - accept wide range of file types
      - accept video
  - output
    - generation
      - visualizations
    - linkages to something outside the article
  - summarization and extraction from web url, skip web scraping content before passing to llm
    - to what extent can ai model successfully extract content and summarize it based on the url? Signal to noise ratio

