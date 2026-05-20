import streamlit as st
import html
from typing import List, Dict
from urllib.parse import urlparse
from config import logger

def sanitize_ticker(raw: str) -> str:
    """
    Sanitize user input for ticker symbol.
    Allows alphanumeric, spaces, dashes, underscores.
    Returns an uppercase string suitable for API queries.
    """
    if not raw:
        return "AAPL"
    # Allow alphanumeric, spaces, dashes; trim and uppercase for ticker search
    cleaned = ''.join(ch for ch in raw if ch.isalnum() or ch in [' ', '-', '_']).strip()
    return cleaned.upper()


def safe_markdown(text: str) -> None:
    """
    Safely render markdown content while preventing raw HTML injection.
    """
    if not text:
        st.warning("⚠️ No content available to display.")
        return
    try:
        # Allow markdown rendering but keep HTML execution disabled
        st.markdown(text, unsafe_allow_html=False)
    except Exception as e:
        st.error("Failed to render content.")
        logger.warning("safe_markdown failed: %s", e)


def _is_safe_url(url: str) -> bool:
    """
    Validate URL protocol to prevent 'javascript:' or other malicious redirects.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ['http', 'https']
    except Exception:
        return False


def display_news(items: List[Dict[str, str]]) -> None:
    """
    Render a list of news articles with premium CSS styling.
    Validates data structure and URL safety before rendering.
    """
    if not items or not isinstance(items, list):
        st.info("📰 No recent news available.")
        return
    
    for article in items:
        # Defensive check against malformed data arrays
        if not isinstance(article, dict):
            continue  
            
        title = html.escape(article.get('title', 'Headline Unavailable'))
        link = article.get('link', '#')
        publisher = html.escape(article.get('publisher', 'Financial Press'))
        
        # Only render if the URL is safe
        if link != '#' and not _is_safe_url(link):
            continue

        # Use styled markdown to match main.py's ".news-card" CSS
        # Added rel="noopener noreferrer" for security when opening new tabs
        st.markdown(f"""
            <div class="news-card">
                <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
                <div class="news-publisher">📰 {publisher}</div>
            </div>
        """, unsafe_allow_html=True)