from dotenv import load_dotenv
from datetime import datetime
import asyncio
from gemini_api import GeminiAPI
import re
# Load environment variables
load_dotenv()
gemini = GeminiAPI()

async def summarize_post(text: str) -> dict:
    """Handle empty content gracefully"""
    if not text.strip():
        return {
            "tags": ["error"],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": "Content unavailable"
        }
        
    # Add null check before slicing
    truncated = text[:15000] if text else ""
    prompt = f"""Analyze this article...{truncated}"""
    
    prompt = """You are an AI assistant specialized in summarizing and extracting metadata from articles. 
Your task is to summarize the article and extract the publication date.
Instructions:
1. Carefully read the entire blog text provided.
2. Extract the publication date as [Publication Date], if not found, return unknown
3. Summarize article in 3-5 sentences as [Summary] and tags as [Tags] in lowercase, no special characters, comma separated
4. Present your findings strictly following the specified format:
<tags>[Tags]</tags>
<date>[Publication Date]</date>
<summary>[Summary]</summary>

Article text:
{text}""".format(text=truncated)

    try:
        response = await gemini.generate_content(
            model_key='summarize',
            prompt=prompt,
            temperature=0.1
        )
        
        return parse_response(response)
    except Exception as e:
        print(f"Summarization error: {str(e)}")
        return {
            "tags": None,
            "date": None,
            "summary": truncated[:500]  # Fallback
        }

def parse_response(response: str) -> dict:
    """Parse the XML-like response format"""
    return {
        "tags": extract_tag(response, "tags"),
        "date": extract_tag(response, "date"),
        "summary": extract_tag(response, "summary")
    }

def extract_tag(text: str, tag: str) -> str:
    match = re.search(f'<{tag}>(.*?)</{tag}>', text, re.DOTALL)
    return match.group(1).strip() if match else None

async def summarize_all(summaries: list) -> str:
    """Generate executive summary from multiple summaries"""
    combined = "\n".join(summaries)
    prompt = """Generate an executive summary under 500 words from these key points:
    Text to analyze:
    {text}
    
    Rules:
    1. Use plain text only in a single paragraph
    2. Maintain crucial details
    3. Avoid markdown
    """.format(text=combined)

    try:
        return await gemini.generate_content(
            model_key='summarize',
            prompt=prompt,
            temperature=0.1
        )
    except Exception as e:
        print(f"Summary aggregation failed: {str(e)}")
        return "\n".join(summaries)

async def extract_date_llm(html_content: str) -> str:
    """Extract publication date using original prompt structure"""
    prompt = """Analyze this HTML and find the publication date in YYYY-MM-DD format.
    Look for dates in article headers, meta tags, or visible date elements, exclude dates in the article body
    Return ONLY the date in ISO format within curly braces or 'null' if not found.
    
    HTML Content:
    {content}""".format(content=html_content[:8000])

    try:
        response = await gemini.generate_content(
            model_key='date_extract',
            prompt=prompt,
            temperature=0.0,
            max_tokens=100
        )
        return response.strip('{}').strip() if response else 'null'
    except Exception as e:
        print(f"Date extraction failed: {str(e)}")
        return 'null'

async def main():
   
    article = """
     (Image credit: Seagate)
Update 1/30/2025:
Seagate
has responded to our queries, pinning the issue on resellers not buying from official distributors. You can
read about that here
.
Advertisement
Original Article:
German outlet Heise.de says it may have uncovered fraud after hearing from many of its readers who bought supposedly new Seagate hard drives, which turned out to be very much used.
Sponsored Links
Sponsored Links
Promoted Links
Promoted Links
Start investing today!
interactive brokers
Learn More
Undo
Last week, the publication
relayed
the experience of one of Heise.de’s readers, who said he had bought a couple of 14TB Seagate Exos HDDs that seemed a little strange. The drives had some minor signs of wear on the outside, but after a quick look at the SMART stats, everything appeared normal. Later, though, the reader did a more thorough Field Accessible Reliability Metrics (FARM) test and discovered that one drive had already been used for 10,000 hours, and the other 15,000 hours.
LATEST VIDEOS FROM tomshardware
Naturally, he returned the drives to the store he bought them from, an official Seagate retailer, and decided to replace them with two 16TB Exos HDDs purchased from a different store. These drives also turned out to be heavily used: 22,000 hours logged on each one.
Advertisement
Although both HDD sellers, neither of which Heise.de identified, claimed the Exos drives were simply brand-new retail models, Seagate told the publication that all four drives were actually OEM models. This meant that the normal five-year warranty did not apply like it would to typical drives bought at retail.
The initial retailer eventually stopped selling the 14TB and 16TB HDDs at some point and even canceled an order that Heise.de had anonymously placed. According to the report, Seagate is looking into how this happened, especially as one of the retailers has the storage corporation’s endorsement as an official retailer.
Stay On the Cutting Edge: Get the Tom's Hardware Newsletter
Get Tom's Hardware's best news and in-depth reviews, straight to your inbox.
After this report was published, the floodgates opened, and over fifty other Heise.de readers
said
they experienced the exact same thing after buying apparently new Seagate HDDs. While 50 is a small sample size, the issue might be widespread since they bought their drives at a dozen different retailers, some of which are on Seagate’s official “where-to-buy” list. Some of the impacted retailers are quite large, such as
Amazon
and Mindfactory.
Most readers report having 16TB Exos drives, but others have the 12TB model, and a few have non-Exos HDDs ranging from 4 to 18TB. The time used ranges from 15,000 to 36,000 hours except for two 4TB HDDs, which were both used for about 50,000 hours. Heise.de checked a few drives at random to see when their warranties expired, and most of them were for 2026. Assuming a five-year warranty, that means they were first made and sold in 2021. All of the readers who reported receiving a used Seagate drive had bought it in the past few weeks, meaning the issue is relatively recent.
It’s hard to imagine this is just a simple mixup, not just because so many retailers are apparently involved but also because they’ve all had their SMART stats reset, which would be very useful to someone trying to pretend a used drive is new. Although it’s not entirely clear if actual fraud is happening here, something has definitely gone very wrong.
We reached out to Seagate for comment but haven’t received a reply yet.
Seagate does have a direct relationship with used hard drives. Nearly a year ago, the company
launched an official eBay store that sells refurbished drives. It
also has a Hard Drive Circularity Program to find as many refurbish-worthy drives as possible, including Exos models. However, this store only sells in the US, so it doesn’t seem likely that it has anything to do with the current situation.
stuffs
stuffs
stuffs
Drop in a standard article here maybe?
See more HDDs News
See all comments (21)
Matthew Connatser
Matthew Connatser is a freelancing writer for Tom's Hardware US. He writes articles about CPUs, GPUs, SSDs, and computers in general.
More about hdds
Seagate responds to fraudulent hard drives scandal, says resellers should only buy from certified partners
Seagate unveils 36TB HAMR hard drive: Mozaic 3+ extended
Latest
Intel cancels Falcon Shores GPU for AI workloads — Jaguar Shores to be successor
See more latest  ►
21 Comments
Comment from the forums
:sweatsmile:
Reply
Seagate has been selling refurbished HDDs here in Germany for years. The two Seagate 1 TB drives I'm currently using are refurbished and I bought them around 8 years ago.
From my expereince Seagate has always put a refurbished sticker on drives that were used. This has me thinking that Seagate released those drives to vendors (without the stickers) hoping no one would notice that the HDDs are used.
Reply
Dr3ams
said:
Seagate has been selling refurbished HDDs here in Germany for years. The two Seagate 1 TB drives I'm currently using are refurbished and I bought them around 8 years ago.
From my expereince Seagate has always put a refurbished sticker on drives that were used. This has me thinking that Seagate released those drives to vendors (without the stickers) hoping no one would notice that the HDDs are used.
They do more than the green label stickers in the US - they also laser etch REFURBISHED into the disk case. Not sure if it is the same worldwide, but I would expect it is.
Generally with these disks there are no signs of use.
Reply
A few years ago I bought 2 1.5TB HDs. A few months later, despite little use, one broke, and was replaced under warranty with a refurbished one (!). Shortly after that the refurbished one also broke. Even the last disk eventually broke and I decided not to change it under warranty given the unreliability of that company's hardware. Since then I have decided to never give my money to Seagate again...
Reply
A few years ago I bought 2 1.5TB HDs. A few months later, despite little use, one broke, and was replaced under warranty with a refurbished one (!). Shortly after that the refurbished one also broke. Even the last disk eventually broke and I decided not to change it under warranty given the unreliability of that company's hardware. Since then I have decided to never give my money to Seagate again...
Reply
pigeonskiller
said:
A few years ago I bought 2 1.5TB HDs. A few months later, despite little use, one broke, and was replaced under warranty with a refurbished one (!). Shortly after that the refurbished one also broke and since then I have decided to never give my money to Seagate again...
How long ago was that? I know there was a point in time when it was difficult to get disks due to flooding at their primary manufacturing plant, and some models were absolutely terrible. I remember the 1tb were quite bad, and heard the 750gb and 1.5tb of the series were bad as well.
Reply
zcomputerwiz
said:
How long ago was that? I know there was a point in time when it was difficult to get disks due to flooding at their primary manufacturing plant, and some models were absolutely terrible. I remember the 1tb were quite bad, and heard the 750gb and 1.5tb of the series were bad as well.
If I remember correctly, some time after that event. However, this does not justify the company's attitude in marketing defective products and recovering financial losses with the money of good-faith customers...
Reply
Something about this story does not make sense. Like where would the hard drives come from?
Reply
vanadiel007
said:
Something about this story does not make sense. Like where would the hard drives come from?
It's definitely going to take more diligence from tech news outlets to uproot who the big distributors are. Saying these drives were "bought from Seagate" is quite disingenuous as it leaves out a few steps of the supply chain and suggests that they were bought from Seagate's own store. No, rather, they are manufactured by Seagate. After that, some entity is pulling this scam where recycled drives are having SMART cleared and going back into the distribution stream or directly to retailers.
Amazon has all sorts of scams and counterfeit products, so that doesn't say anything. As for Mindfactory, surprising to me but if they source those models from a distributor and not directly from Seagate's factories, that allows that middleman tampering problem.
That said, it's still feasible that there's a small splinter cell at one of the Seagate factories that has been pulling this off under the radar. Either way, I'm extremely curious to see how this all unfolds!
Reply
I have never bought Seagate, only WD/Toshiba/Fujitsu/IBM (and earlier server versions of Samsung). Once I got one (SMR) as part of a laptop with NAND cache, it has been working for 7 years, although its performance during large copy operations is terrible, despite the 8GB NAND buffer.
Most of my drives are from WD. The only problem was with 1.5TB drives. They crumbled even in the complete absence of any vibration and even with an ideal (after a full scan) surface immediately after purchase - about 1.5-2 years. And they were in 2 different heavy cases with good cooling with good power supplies.
But the latest WD purchases have shown that their reliability has seriously dropped even with the same capacity as very old ones - 2TB. With a much weaker load than before, because now the system drives are only SSDs. And the prices in $ have not fallen at all in 15 years. At the same time, back in 2010, WD Green came with a 5-year warranty. I have such disks for 2 TB. I switched to Toshiba server disks without helium for 8 TB with a 5-year warranty and a read/write resource of 550 TB per year. Although they are quite noisy. But for backup, this is not important. Most of the time, all my HDDs are turned off to avoid the risk of random vibrations near the cases and impacts (especially dangerous with modern high platter density and low head suspension, if there are children or large animals in the house), including those that are in system units thanks to 5.25" drive power selectors. When needed, I turn them on and then immediately turn them off.
I also began to suspect, judging by the mass failures in some series according to reviews in a number of large retail chains, that some SSD batches of disks are clearly either repackaged like new (already used and worn out with reset SMART parameters) or for different countries there are batches with different grades of NAND chips. For third world countries, either repackaged restored / worn out or lower grade. For the USA and Western Europe - the highest grade, only new chips.
------
Unlike SSD, where real wear is extremely difficult to check (long time frames of the test for the rate of charge loss in cells), in HDD wear is most often easily checked by a full surface scan - if there were already head hits on the protective layer and there were chips, all this will quickly be visible in slow sectors, whole blocks. A disk that has worked for tens of thousands of hours cannot look new a priori, unless this is a factory repackaging of the can - there will be noticeable traces and irreparable dust almost everywhere and it will be visible by the quality of the plate surface after the scan. And "restoration" at the Seagate plant without replacing the plates and possibly heads - does not cancel the fact of wear of the servo drive / heads and plates, which have a finite resource, including the protective layer. So such a disk is quite easy to distinguish in an individual case, but not when you buy a large batch - but these are the problems of the company's purchasers and their risks.
Reply
View All 21 Comments
Show more comments
Most Popular 
    """
    summary = await summarize_post(article)
    print(f"=== summary ===\n {summary} \n=== end of summary ===\n")
    
    results = ['Internet sleuths discovered that including expletives in Google search queries disables the AI-generated summaries, providing only standard search results. This workaround highlights user dissatisfaction with AI summaries, which are often inaccurate and potentially spread misinformation.  The method is a simple alternative to more complex techniques for disabling AI results.  This issue reflects broader concerns about the unchecked proliferation of AI tools across various platforms.', '', 'This is a list of recent posts related to game development, including news about Godot 4.4 beta 2,  open-source projects like a pixel art upscaler and a 2D cloth simulation, and articles on game design and industry trends.  Several posts highlight new releases and tools for game developers. The list also includes discussions on game development processes and performance optimization.']
    executive_summary = await summarize_all(results)
    print(f"=== executive_summary ===\n {executive_summary} \n=== end of executive_summary ===\n")

if __name__ == "__main__":
    asyncio.run(main())