"""Load a news article from a URL, an HTML file or a plain-text file."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import requests
from bs4 import BeautifulSoup

USER_AGENT = 'Mozilla/5.0 (greek-utils reader)'
MIN_PARAGRAPH_CHARS = 40


@dataclass
class Article:
    title: str
    text: str
    url: str | None = None
    outlet: str | None = None
    author: str | None = None
    published: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find('meta', attrs={'property': name}) or soup.find('meta', attrs={'name': name})
        if tag and tag.get('content'):
            return tag['content'].strip()
    return None


def _json_ld_author(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            author = item.get('author') if isinstance(item, dict) else None
            if isinstance(author, list):
                author = author[0] if author else None
            if isinstance(author, dict):
                author = author.get('name')
            if isinstance(author, str) and author.strip():
                return author.strip()
    return None


def _clean(text: str) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub(r'\s+([,.;:!·»;)])', r'\1', text)


def parse_html(html: str, url: str | None = None) -> Article:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'figure', 'aside', 'nav', 'footer', 'header']):
        if tag.name == 'script' and tag.get('type') == 'application/ld+json':
            continue
        if tag.name == 'header' and tag.find_parent('article'):
            continue  # an article's own header holds its headline
        tag.decompose()

    container = soup.find('article') or soup.find('main') or soup.body or soup
    h1 = container.find('h1') or soup.find('h1')
    title = h1.get_text(' ', strip=True) if h1 else ''
    if not title:
        title = _meta(soup, 'og:title') or (soup.title.get_text(strip=True) if soup.title else '')

    paragraphs = [_clean(p.get_text()) for p in container.find_all('p')]
    paragraphs = [p for p in paragraphs if len(p) >= MIN_PARAGRAPH_CHARS]

    return Article(
        title=title,
        text='\n\n'.join(paragraphs),
        url=url or _meta(soup, 'og:url'),
        outlet=_meta(soup, 'og:site_name'),
        author=_meta(soup, 'author', 'article:author') or _json_ld_author(soup),
        published=_meta(soup, 'article:published_time', 'og:published_time', 'date'),
    )


def parse_text(text: str) -> Article:
    """Plain text: a short first line followed by a blank line is the title."""
    lines = text.strip().splitlines()
    if len(lines) > 2 and len(lines[0]) <= 150 and not lines[1].strip():
        return Article(title=lines[0].strip(), text='\n'.join(lines[2:]).strip())
    return Article(title='', text=text.strip())


def fetch(url: str, timeout: float = 20) -> Article:
    resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding if resp.encoding in (None, 'ISO-8859-1') else resp.encoding
    return parse_html(resp.text, url)


def load(source: str) -> Article:
    if re.match(r'https?://', source):
        return fetch(source)
    path = Path(source)
    content = path.read_text(encoding='utf-8')
    if path.suffix.lower() in ('.html', '.htm'):
        return parse_html(content)
    return parse_text(content)
