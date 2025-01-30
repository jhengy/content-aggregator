from scraper import scrape_article, extract_posts
from llm import summarize_post, filter_by_date, summarize_all
from dotenv import load_dotenv
import json
from datetime import datetime
import os
import time
import sys
load_dotenv()

def process_articles(root_url, target_date, extract_params={'css_selector': 'a[href]'}, limit=10):
    """Main workflow: Extract URLs -> Filter by date -> Process articles"""
    print(f"🚀 Starting processing for {root_url} on {target_date}")
    
    # Step 1: Extract potential post URLs
    print("\n🔍 Extracting post links...")
    posts = extract_posts(root_url, **extract_params)
    if not posts:
        print("❌ No posts found")
        return
        
    print(f"📚 Found {len(posts)} potential articles")
    
    # Step 2: Filter by publication date
    # print("\n📅 Filtering by date...")
    # filtered_posts = filter_by_date(posts, target_date)
    # if not filtered_posts:
    #     print("❌ No posts match the target date")
    #     return
    filtered_posts = posts[:limit]
    
    print(f"🎯 Found {len(filtered_posts)} articles published on {target_date}")
    
    # Step 3: Process each article
    results = []
    n = len(filtered_posts)
    while len(results) < n:
        url = filtered_posts.pop(0)
        print(f"\n📄 Processing article {url}")
        
        try:
            # Scrape article content
            print("Scrape content...")
            content = scrape_article(url)
                
            # Generate summary
            print("Generating summary...")
            summary = summarize_post(content)
            if summary['summary'] is None:
                print(f"❌ Error processing {url}: {summary}")
                filtered_posts.append(url)
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
            filtered_posts.append(url)
            
    # Create the output directory if it doesn't exist
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate executive summary
    print("Generating executive summary...")
    executive_summary = summarize_all([x['summary'] for x in results])
    print(executive_summary)
    
    # Save results
    filename = f"{output_dir}/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
        
    print(f"\n🎉 Done! Results saved to {filename}")

if __name__ == "__main__":
    try:
        process_articles(
            root_url="https://hn.algolia.com/?dateRange=last24h&type=story",
            target_date="2025-01-29",
            extract_params={  # Full configuration object
                'css_selector': 'a[href].Story_link',
                # Can add other extract_posts parameters here
            }
        )
    except KeyboardInterrupt:
        print("\n🛑 Script interrupted by user")
        sys.exit(1)