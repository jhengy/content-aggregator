import pytest
from content_aggregator.utils import deduplicate

@pytest.fixture
def sample_articles():
    return [
        {'url': 'https://blog.example.com/post1', 'title': 'Post One'},
        {'url': 'https://blog.example.com/post2', 'title': 'Post Two'},
        {'url': 'https://blog.example.com/post1', 'title': 'Duplicate Post'},
        {'url': 'https://blog.example.com/post3', 'title': 'Post Three'},
        {'url': 'https://blog.example.com/post2', 'title': 'Duplicate Post'},
    ]

def test_deduplicate_default_key(sample_articles):
    result = deduplicate(sample_articles)
    assert len(result) == 3
    assert [a['url'] for a in result] == [
        'https://blog.example.com/post1',
        'https://blog.example.com/post2',
        'https://blog.example.com/post3'
    ]

def test_deduplicate_custom_key(sample_articles):
    custom_key = lambda x: x['title']
    result = deduplicate(sample_articles, custom_key)
    assert len(result) == 4
    assert [a['title'] for a in result] == [
        'Post One',
        'Post Two',
        'Duplicate Post',
        'Post Three'
    ]

def test_deduplicate_empty_input():
    assert deduplicate([]) == []

def test_deduplicate_no_duplicates():
    articles = [
        {'url': 'https://blog.example.com/a'},
        {'url': 'https://blog.example.com/b'}
    ]
    assert len(deduplicate(articles)) == 2

def test_deduplicate_mixed_case_keys():
    articles = [
        {'url': 'A'}, 
        {'url': 'a'},
        {'url': 'A'}
    ]
    result = deduplicate(articles, lambda x: x['url'])
    assert len(result) == 2
    assert [a['url'] for a in result] == ['A', 'a'] 