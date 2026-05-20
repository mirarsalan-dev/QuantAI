import streamlit as st
import html
from typing import List, Dict


def sanitize_ticker(raw: str) -> str:
    if not raw:
        return "AAPL"
    # allow alnum, space, dash; trim and uppercase for ticker search
    cleaned = ''.join(ch for ch in raw if ch.isalnum() or ch in [' ', '-', '_']).strip()
    return cleaned.upper()


def safe_markdown(text: str):
    # Use plain write to avoid HTML injection; escape HTML entities
    if not text:
        st.write("No content available.")
        return
    try:
        safe = html.escape(text)
        st.write(safe)
    except Exception:
        st.write("Content unavailable.")


def display_news(items: List[Dict[str, str]]):
    for article in items:
        title = html.escape(article.get('title', 'Headline Unavailable'))
        link = article.get('link', '#')
        publisher = html.escape(article.get('publisher', 'Financial Press'))
        st.markdown(f"- [{title}]({link}) — *{publisher}*")
