from dotenv import load_dotenv
import json
from datetime import datetime
import os
import time
import sys
from .utils import deduplicate
from typing import List, Dict, Any
from .scraper import Scraper
from .llm import LLMProcessor
from .models import Article
from .exceptions import RateLimitExceededError
import asyncio
import click

__version__ = "0.1.0"
__all__ = ['ContentAggregator', 'Scraper', 'LLMProcessor', 'Article']

class ContentAggregator:
    """Main class orchestrating the content aggregation workflow"""
    
    def __init__(self):
        self.scraper = Scraper()
        self.llm = LLMProcessor()
        self.config = {
            'article_sources': [
                {
                    'source_url': "https://hn.algolia.com/?dateRange=last24h&type=story",
                    'extract_type': 'index',
                    'extract_params': {'css_selector': 'a[href].Story_link'},
                },
                {
                    'source_url': "https://www.hillelwayne.com/",
                    'extract_type': 'index',
                    'extract_params': {'css_selector': '#recent-posts li:nth-child(1) a'},
                },
                {
                    'source_url': "https://newsletter.pragmaticengineer.com/feed",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://hellointerview.substack.com/feed",
                    'extract_type': 'rss',
                },        
                {
                    'source_url': "https://architecturenotes.co/feed",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://simonwillison.net/atom/everything/",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://airbnb.tech/feed/",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://engineering.fb.com/feed/",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://www.allthingsdistributed.com/atom.xml",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://hackernoon.com/feed",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://cacm.acm.org/section/blogcacm/feed/",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://www.jeremykun.com/index.xml",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://austinhenley.com/blog/feed.rss",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://www.techmeme.com/feed.xml",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://brooker.co.za/blog/rss.xml",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://feeds.feedburner.com/blogspot/RLXA",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://world.hey.com/dhh/feed.atom",
                    'extract_type': 'rss',
                },
                {
                    'source_url': "https://www.writesoftwarewell.com/rss",
                    'extract_type': 'rss',
                },
            ],
            'max_articles': int(os.getenv('ARTICLES_LIMIT', 500)),
            'retry_delay_seconds': 15
        }

    async def run_pipeline(self) -> None:
        """Main execution pipeline"""
        articles = await self.gather_articles()
        await self.process_articles(articles)

    # TODO: consider recursively extracting articles with a max depth as some source_url may be an index for another index
    async def extract_articles(self, source_url, extract_type, extract_params={'css_selector': 'a[href]'}, limit=100):
        """Main workflow: Extract URLs -> Filter by date -> Process articles"""
        print(f"🚀 Starting extracting articles from {source_url}")
        
        if extract_type == 'rss':
            current_time = time.time()
            one_day_ago = current_time - 86400
            articles = await self.scraper.extract_from_rss(source_url)
            articles = [x for x in articles if x.get('publish_at', 0) > one_day_ago]
        elif extract_type == 'index':
            articles = await self.scraper.extract_from_index(source_url, **extract_params)
        else:
            raise ValueError(f"Invalid extract type: {extract_type}")
        
        if not articles:
            print(f"⚠️ No posts found from {source_url}")
            return []
        
        print(f"📚 Found {len(articles[:limit])} potential articles from {source_url} with limit {limit}")
        return articles[:limit]

    async def process_articles(self, articles: List[Article]) -> List[Article]:
        results = []
        already_retried = set()
        while len(articles) > 0:
            article = articles.pop(0)
            url = article.get('url')
            
            if not url:
                print(f"⚠️ Empty URL for {article} - skipping")
                continue
            
            print(f"\n📄 Processing article {url}")
            
            try:
                print("Scrape content...")
                article_content = await self.scraper.scrape_article(url)
                if not article_content:
                    print(f"⚠️ Empty content for {url} - skipping")
                    continue
                    
                # Generate summary
                print("Generating summary...")
                summary = await self.llm.summarize_post(article_content, url)
                if summary.get('summary') is None:
                    print(f"❌ Error processing {url} - returned empty summary")
                    if url not in already_retried:
                        already_retried.add(url)
                        articles.append(article)
                        continue
                else:
                    results.append(Article(
                        url=url,
                        tags=summary.get('tags'),
                        date=summary.get('date'),
                        summary=summary.get('summary'),
                        author=article.get('author') or summary.get('author'),
                        title=article.get('title') or summary.get('title'),
                        publish_at=article.get('publish_at'),
                        timestamp=datetime.now().isoformat()
                    ))
                
                print(f"✅ Successfully processed: {url}")
                
            # TODO: exponential backoff in retry?
            except RateLimitExceededError as e:
                if url not in already_retried:
                    retry_after = e.retry_after or self.config['retry_delay_seconds']
                    print(f"🔄 Retrying {url} in {retry_after} seconds")
                    time.sleep(retry_after)
                    
                    already_retried.add(url)
                    articles.append(article)
                else:
                    print(f"⚠️ Already retried {url} - skipping")
                    continue
                
            except Exception as e:
                print(f"❌ Error processing {url} - {str(e)}")
                pass
            
        # Create the output directory if it doesn't exist
        output_dir = "outputs"
        os.makedirs(output_dir, exist_ok=True)
        file_prefix = f"results_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        json_filename = f"{output_dir}/{file_prefix}.json"
        with open(json_filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Generate executive summary
        print("Generating executive summary...")
        executive_summary = await self.llm.summarize_all([x.get('summary') for x in results])
        summary_filename = f"{output_dir}/{file_prefix}_summary.txt"
        with open(summary_filename, 'w') as f:
            f.write(executive_summary)
        
        print(f"\n🎉 Done! Results saved to {json_filename} and {summary_filename}")
        return results

    async def gather_articles(self):
        """Run multiple extraction tasks concurrently and combine results"""
        
        # TODO: source_url for index extract type should implicitly include the date range as there is no reliable way to get the date range from the index page, think of a better way to do this
        article_tasks = self.config['article_sources']
        
        # Create all coroutines
        coroutines = [self.extract_articles(**task) for task in article_tasks]
        
        # Run all tasks concurrently
        results = await asyncio.gather(*coroutines)
        flattened_results = [item for sublist in results for item in sublist]
        
        if len(flattened_results) == 0:
            print("⚠️ No articles found from any sources")
            return []
      
        # distribute the limit across all sources by the proportion of the number of articles found
        # TODO: there's a chance that the total number exceeds the limit, need to handle this
        weighted_results = [result[:(int(len(result) / len(flattened_results) * self.config['max_articles']) or 1)] for result in results]

        # Combine and deduplicate
        combined = deduplicate(
            [item for articles in weighted_results for item in articles],
            key_func=lambda x: x.get('url')
        )
        
        print(f"🎉 Done! Out of limit={self.config['max_articles']}, found {len(combined)} articles in total: {combined} ")
        return combined[:self.config['max_articles']]

# Add Click integration at the bottom
@click.group()
def main():
    """Content Aggregator CLI"""
    pass

@main.command()
def run():
    """Run the aggregation pipeline"""
    try:
        aggregator = ContentAggregator()
        asyncio.run(aggregator.run_pipeline())
    except KeyboardInterrupt:
        print("\n🛑 Script interrupted by user")
        sys.exit(1)

if __name__ == "__main__":
    main()
