#!/usr/bin/env python3
"""
Markdown Website Scraper Module
Converts website content to markdown format for analysis
"""

import requests
import logging
from typing import Optional, Dict
from urllib.parse import urlparse
import html2text
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class MarkdownScraper:
    """Scrape website and convert to markdown"""
    
    def __init__(self, url: str, timeout: int = 30):
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def scrape_to_markdown(self) -> Dict:
        """
        Scrape website and convert to markdown
        Returns dict with markdown content and metadata
        """
        try:
            # Validate URL
            parsed = urlparse(self.url)
            if not parsed.scheme:
                self.url = 'https://' + self.url
            
            # Fetch the webpage
            response = self.session.get(self.url, timeout=self.timeout)
            response.raise_for_status()
            
            # Get HTML content
            html_content = response.text
            
            # Convert HTML to markdown using html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.body_width = 0  # Don't wrap lines
            h.unicode_snob = True
            h.ignore_emphasis = False
            
            markdown_content = h.handle(html_content)
            
            # Extract additional metadata
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Get title
            title = soup.find('title')
            title_text = title.get_text() if title else ''
            
            # Get meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            description = meta_desc.get('content', '') if meta_desc else ''
            
            # Get meta keywords
            meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
            keywords = meta_keywords.get('content', '') if meta_keywords else ''
            
            # Extract headings
            headings = []
            for tag in ['h1', 'h2', 'h3']:
                for heading in soup.find_all(tag):
                    headings.append(heading.get_text().strip())
            
            return {
                'success': True,
                'url': self.url,
                'markdown': markdown_content,
                'title': title_text,
                'description': description,
                'keywords': keywords,
                'headings': headings,
                'content_length': len(markdown_content)
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching {self.url}: {e}")
            return {
                'success': False,
                'error': f'Failed to fetch website: {str(e)}',
                'url': self.url
            }
        except Exception as e:
            logger.error(f"Error converting to markdown: {e}")
            return {
                'success': False,
                'error': f'Failed to convert to markdown: {str(e)}',
                'url': self.url
            }
    
    def scrape_with_api(self, api_key: Optional[str] = None) -> Dict:
        """
        Alternative: Use external API for markdown conversion
        Falls back to local conversion if API fails
        """
        # Try API first if key provided
        if api_key:
            try:
                # Try UseScraper API
                api_url = "https://api.usescraper.com/v1/scrape"
                response = requests.post(
                    api_url,
                    json={'url': self.url},
                    headers={'Authorization': f'Bearer {api_key}'},
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        'success': True,
                        'url': self.url,
                        'markdown': data.get('markdown', ''),
                        'title': data.get('title', ''),
                        'description': data.get('description', ''),
                        'source': 'api'
                    }
            except Exception as e:
                logger.warning(f"API scraping failed, using local method: {e}")
        
        # Fallback to local scraping
        return self.scrape_to_markdown()

