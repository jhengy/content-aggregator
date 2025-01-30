from extract_urls import extract_posts, filter_by_date
from openrouter_api_script import scrape_article, summarize
from dotenv import load_dotenv
import os
import json
from datetime import datetime

load_dotenv()

def process_articles(root_url, target_date):
    """Main workflow: Extract URLs -> Filter by date -> Process articles"""
    print(f"🚀 Starting processing for {root_url} on {target_date}")
    
    # Step 1: Extract potential post URLs
    print("\n🔍 Extracting post links...")
    posts = extract_posts(
            root_url,
            **
            {
                'css_selector': 'a[href].Story_link'
            }
        )
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
    filtered_posts = posts[:2]
    
    print(f"🎯 Found {len(filtered_posts)} articles published on {target_date}")
    
    # Step 3: Process each article
    results = []
    for idx, url in enumerate(filtered_posts, 1):
        print(f"\n📄 Processing article {idx}/{len(filtered_posts)}: {url}")
        
        try:
            # Scrape article content
            content = scrape_article(url)
            if "error" in content.lower():
                raise ValueError(content)
                
            # Generate summary
            summary = summarize(content)
            
            # Parse summary components
            summary_lines = summary.split('\n')
            tags = summary_lines[0].replace("Tags:", "").strip() if len(summary_lines) > 0 else ""
            date = summary_lines[1].replace("Published Date:", "").strip() if len(summary_lines) > 1 else ""
            bullets = '\n'.join(summary_lines[2:]) if len(summary_lines) > 2 else ""
            
            results.append({
                "url": url,
                "tags": tags,
                "date": date,
                "summary": bullets,
                "timestamp": datetime.now().isoformat()
            })
            
            print(f"✅ Successfully processed: {url}")
            
        except Exception as e:
            print(f"❌ Error processing {url}: {str(e)}")
            results.append({
                "url": url,
                "error": str(e)
            })
    
    # Save results
    filename = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
        
    print(f"\n🎉 Done! Results saved to {filename}")

if __name__ == "__main__":
    # Example usage
    process_articles(
        root_url="https://hn.algolia.com/?dateRange=last24h&type=story",
        target_date="2025-01-29"
    ) 