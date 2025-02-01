from scraper import scrape_article, extract_from_index
from llm import summarize_post, summarize_all
from dotenv import load_dotenv
import json
from datetime import datetime
import os
import time
import sys
import asyncio

load_dotenv()

async def extract_articles(source_url, target_date, extract_params={'css_selector': 'a[href]'}, limit=10):
    """Main workflow: Extract URLs -> Filter by date -> Process articles"""
    print(f"🚀 Starting processing for {source_url} on {target_date}")
    
    # Step 1: Extract potential post URLs
    print("\n🔍 Extracting post links...")
    articles = await extract_from_index(source_url, **extract_params)
    if not articles:
        print("❌ No posts found")
        return
        
    print(f"📚 Found {len(articles)} potential articles")
    filtered_articles = articles[:limit]
    
    print(f"🎯 Found {len(filtered_articles)} articles published on {target_date}")
    return filtered_articles

async def process_articles(filtered_articles):
    results = []
    n = len(filtered_articles)
    while len(results) < n and len(filtered_articles) > 0:
        url = filtered_articles.pop(0)
        print(f"\n📄 Processing article {url}")
        
        try:
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
                filtered_articles.append(url)
                continue
            results.append({
                "url": url,
                "tags": summary['tags'],
                "date": summary['date'],
                "summary": summary['summary'],
                "timestamp": datetime.now().isoformat()
            })
            
            print(f"✅ Successfully processed: {url}")
            
        except Exception as e:
            print(f"❌ Error processing {url}: {str(e)}")
            # results.append({
            #     "url": url,
            #     "error": str(e)
            # })
            
            time.sleep(30)
            filtered_articles.append(url)
            
    # Create the output directory if it doesn't exist
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate executive summary
    print("Generating executive summary...")
    executive_summary = await summarize_all([x['summary'] for x in results])
    print(executive_summary)
    
    # Save results
    filename = f"{output_dir}/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
        
    print(f"\n🎉 Done! Results saved to {filename}")

if __name__ == "__main__":
    try:
        articles = asyncio.run(extract_articles(source_url="https://hn.algolia.com/?dateRange=last24h&type=story",
            target_date="2025-01-29",
            extract_params={
                'css_selector': 'a[href].Story_link',
            },
            limit=3
        ))
        
        asyncio.run(process_articles(articles))
    except KeyboardInterrupt:
        print("\n🛑 Script interrupted by user")
        sys.exit(1)