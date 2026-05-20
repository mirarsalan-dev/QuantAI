import streamlit as st
import html
from typing import List, TypedDict
from urllib.parse import urlparse
from config import logger

class Article(TypedDict, total=False):
    """Type hint for news article structure."""
    title: str
    link: str
    publisher: str

def sanitize_ticker(raw: str) -> str:
    """
    Sanitize user input for ticker symbol.
    Allows alphanumeric, spaces, dashes, underscores.
    Returns an uppercase string suitable for API queries.
    """
    if not raw or not raw.strip():
        logger.warning("Empty ticker provided, using AAPL fallback")
        return "AAPL"
    
    cleaned = ''.join(ch for ch in raw if ch.isalnum() or ch in [' ', '-', '_']).strip()
    if not cleaned:
        logger.warning("Sanitize_ticker resulted in empty string, using AAPL fallback")
        return "AAPL"
    
    return cleaned.upper()

def safe_markdown(text: str) -> None:
    """
    Safely render markdown content while preventing raw HTML injection.
    """
    if not text or not text.strip():
        st.warning("⚠️ No content available to display.")
        return
    try:
        st.markdown(text, unsafe_allow_html=False)
    except Exception as e:
        st.error("Failed to render content.")
        logger.warning("safe_markdown failed: %s", e)

def _is_safe_url(url: str) -> bool:
    """
    Validate URL protocol to prevent 'javascript:' or other malicious redirects.
    """
    if not url or not isinstance(url, str):
        return False
    
    try:
        parsed = urlparse(url)
        # Whitelist safe schemes; reject empty/missing schemes and require a network location
        return parsed.scheme in ['http', 'https'] and bool(parsed.netloc)
    except Exception as e:
        logger.debug("URL parsing failed for %s: %s", url, e)
        return False

def display_news(items: List[Article]) -> None:
    """
    Render a list of news articles with premium CSS styling.
    Validates data structure, URL safety, escapes attributes, and removes duplicates.
    """
    if not items or not isinstance(items, list):
        st.info("📰 No recent news available.")
        return
    
    seen_links = set()  # Deduplicate articles
    
    for article in items:
        if not isinstance(article, dict):
            continue
        
        title = article.get('title', 'Headline Unavailable')
        link = article.get('link', '#')
        publisher = article.get('publisher', 'Financial Press')
        
        # Deduplicate and validate URL before processing
        if link == '#' or not _is_safe_url(link) or link in seen_links:
            continue
        
        seen_links.add(link)
        
        # Escape all user-controlled content
        title = html.escape(str(title))
        publisher = html.escape(str(publisher))
        
        # Critical Security Fix: quote=True ensures malicious links can't break out of the href attribute
        safe_link = html.escape(link, quote=True)
        
        # Use markdown with safe HTML (no unescaped user input in HTML attributes)
        st.markdown(f"""
            <div class="news-card">
                <a href="{safe_link}" target="_blank" rel="noopener noreferrer">{title}</a>
                <div class="news-publisher">📰 {publisher}</div>
            </div>
        """, unsafe_allow_html=True)