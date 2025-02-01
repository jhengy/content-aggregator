from scraper import scrape_article, extract_from_index, extract_from_rss
from llm import summarize_post, summarize_all
from dotenv import load_dotenv
import json
from datetime import datetime
import os
import time
import sys
import asyncio
from utils import deduplicate

load_dotenv()

async def extract_articles(source_url, extract_type, extract_params={'css_selector': 'a[href]'}, limit=100):
    """Main workflow: Extract URLs -> Filter by date -> Process articles"""
    print(f"🚀 Starting extracting articles from {source_url}")
    
    if extract_type == 'rss':
        current_time = time.time()
        one_day_ago = current_time - 86400
        articles = await extract_from_rss(source_url)
        articles = [x for x in articles if x['publish_at'] > one_day_ago]
    elif extract_type == 'index':
        articles = await extract_from_index(source_url, **extract_params)
    else:
        raise ValueError(f"Invalid extract type: {extract_type}")
    
    if not articles:
        print(f"❌ No posts found from {source_url}")
        return []
        
    print(f"📚 Found {len(articles[:limit])} potential articles from {source_url} with limit {limit}")
    return articles[:limit]

async def process_articles(articles):
    results = []
    n = len(articles)
    while len(results) < n and len(articles) > 0:
        article = articles.pop(0)
        url = article['url']
        print(f"\n📄 Processing article {url}")
        
        try:
            # TODO: support for pdf
            # Scrape article content
            print("Scrape content...")
            content = await scrape_article(url)
            if not content:
                print(f"⚠️ Empty content for {url}, skipping")
                continue
                
            # Generate summary
            print("Generating summary...")
            summary = await summarize_post(content)
            if summary['summary'] is None:
                print(f"❌ Error processing {url}: {summary}")
                articles.append(article)
                continue
            results.append({
                "url": url,
                "tags": summary['tags'],
                "date": summary['date'],
                "summary": summary['summary'],
                "author": article['author'] or summary['author'],
                "title": article['title'] or summary['title'],
                "timestamp": datetime.now().isoformat()
            })
            
            print(f"✅ Successfully processed: {url}")
            
        except Exception as e:
            print(f"❌ Error processing {url}: {str(e)}")
            # if rate limited, wait and try again
            time.sleep(15)
            articles.append(article)
            
    # Create the output directory if it doesn't exist
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)
    file_prefix = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    json_filename = f"{output_dir}/{file_prefix}.json"
    with open(json_filename, 'w') as f:
        json.dump(results, f, indent=2)
        
    # Generate executive summary
    print("Generating executive summary...")
    executive_summary = await summarize_all([x['summary'] for x in results])
    summary_filename = f"{output_dir}/{file_prefix}_summary.txt"
    with open(summary_filename, 'w') as f:
        f.write(executive_summary)
        
    print(f"\n🎉 Done! Results saved to {json_filename} and {summary_filename}")

async def gather_articles(total_limit=500):
    """Run multiple extraction tasks concurrently and combine results"""
    
    article_tasks = [
        {
            'source_url': "https://hn.algolia.com/?dateRange=last24h&type=story",
            'extract_type': 'index',
            'extract_params': {'css_selector': 'a[href].Story_link'},
        },
        {
            'source_url': "https://simonwillison.net/atom/everything/",
            'extract_type': 'rss',
        }
    ]
    
    # Create all coroutines
    coroutines = [extract_articles(**task) for task in article_tasks]
    
    # Run all tasks concurrently
    results = await asyncio.gather(*coroutines)
    flattened_results = [item for sublist in results for item in sublist]
  
    # distribute the limit across all sources by the proportion of the number of articles found
    weighted_results = [result[:(int(len(result) / len(flattened_results) * total_limit) or 1)] for result in results]

    # Combine and deduplicate
    combined = deduplicate(
        [item for articles in weighted_results for item in articles],
        key_func=lambda x: x['url']
    )
    
    print(f"🎉 Done! Found {len(combined)} articles in total: {combined} out of limit {total_limit}")
    return combined[:total_limit]

if __name__ == "__main__":
    try:
        articles = asyncio.run(gather_articles(int(os.getenv('ARTICLES_LIMIT'))))
        asyncio.run(process_articles(articles))
    except KeyboardInterrupt:
        print("\n🛑 Script interrupted by user")
        sys.exit(1)