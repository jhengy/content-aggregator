import pytest
from content_aggregator.llm import LLMProcessor

# NOTE: these test reqire GEMINI_API_KEY environment variable and will fire api calls

@pytest.fixture
def live_processor():
    # Requires GEMINI_API_KEY environment variable
    return LLMProcessor()

@pytest.mark.external
@pytest.mark.asyncio
async def test_live_summarize_post(live_processor):
    """Integration test with real Gemini API (requires API key)"""
    article_text = """Seagate has responded to queries about used hard drives being sold as new..."""
    
    result = await live_processor.summarize_post(
        article_text,
        "https://example.com/article"
    )
    
    assert result.get('url') == "https://example.com/article"
    assert result.get('title') != live_processor.UNKNOWN
    assert result.get('summary') != "No summary generated"
    assert len(result.get('tags')) > 0

@pytest.mark.external
@pytest.mark.asyncio
async def test_live_summarize_all(live_processor):
    """Integration test for summary aggregation"""
    input_summaries = [
        "Recent findings show unexpected failure rates in storage hardware",
        "New industry report reveals growing concerns about refurbished components"
    ]
    
    result = await live_processor.summarize_all(input_summaries)
    
    assert len(result) > 100  # Should generate substantial summary
    assert any(word in result.lower() for word in ["insights", "trends", "implications"]) 