#!/usr/bin/env python3
"""
Auto Marketer Module
Main orchestrator for automated marketing campaigns
"""

import logging
from typing import Dict, List, Optional
import json
from datetime import datetime

from markdown_scraper import MarkdownScraper
from content_analyzer import ContentAnalyzer
from social_media_poster import (
    TikTokPoster, InstagramPoster, XPoster, PinterestPoster, RedditPoster
)

logger = logging.getLogger(__name__)


class AutoMarketer:
    """Automated marketing campaign manager"""
    
    def __init__(self, company_url: str, db=None):
        self.company_url = company_url
        self.db = db
        self.markdown_scraper = MarkdownScraper(company_url)
        self.analysis = None
        self.campaign_id = None
        
        # Initialize social media posters
        self.posters = {
            'tiktok': TikTokPoster(),
            'instagram': InstagramPoster(),
            'x': XPoster(),
            'pinterest': PinterestPoster(),
            'reddit': RedditPoster()
        }
    
    def setup_campaign(self, user_id: int, social_credentials: Dict = None) -> Dict:
        """
        Setup and analyze the company for marketing campaign
        
        Args:
            user_id: User ID for database tracking
            social_credentials: Dict with credentials for social platforms
                {
                    'instagram': {'username': '', 'password': ''},
                    'tiktok': {'username': '', 'password': ''},
                    'pinterest': {'email': '', 'password': ''},
                    'reddit': {'client_id': '', 'client_secret': '', 'username': '', 'password': ''},
                    'x': {'api_key': ''}
                }
        """
        try:
            # Step 1: Scrape website to markdown
            logger.info(f"Scraping {self.company_url} to markdown...")
            markdown_result = self.markdown_scraper.scrape_to_markdown()
            
            if not markdown_result.get('success'):
                return {
                    'success': False,
                    'error': markdown_result.get('error', 'Failed to scrape website'),
                    'step': 'scraping'
                }
            
            markdown_content = markdown_result.get('markdown', '')
            
            # Step 2: Analyze content
            logger.info("Analyzing content...")
            analyzer = ContentAnalyzer(markdown_content)
            analysis = analyzer.analyze()
            
            self.analysis = analysis
            
            # Step 3: Create campaign in database
            if self.db:
                self.campaign_id = self.db.create_campaign(
                    user_id=user_id,
                    company_url=self.company_url,
                    company_field=analysis.get('field'),
                    company_offerings=json.dumps(analysis.get('offerings', [])),
                    markdown_content=markdown_content[:10000],  # Limit size
                    analysis_summary=analysis.get('summary')
                )
            
            # Step 4: Setup social media credentials
            if social_credentials:
                self._setup_social_credentials(social_credentials)
            
            return {
                'success': True,
                'campaign_id': self.campaign_id,
                'company_url': self.company_url,
                'analysis': analysis,
                'markdown_length': len(markdown_content)
            }
            
        except Exception as e:
            logger.error(f"Error setting up campaign: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'step': 'setup'
            }
    
    def _setup_social_credentials(self, credentials: Dict):
        """Setup credentials for social media platforms"""
        # Instagram
        if 'instagram' in credentials:
            insta_creds = credentials['instagram']
            self.posters['instagram'] = InstagramPoster(
                username=insta_creds.get('username'),
                password=insta_creds.get('password')
            )
        
        # TikTok
        if 'tiktok' in credentials:
            tiktok_creds = credentials['tiktok']
            self.posters['tiktok'] = TikTokPoster(
                username=tiktok_creds.get('username'),
                password=tiktok_creds.get('password')
            )
        
        # Pinterest
        if 'pinterest' in credentials:
            pinterest_creds = credentials['pinterest']
            self.posters['pinterest'] = PinterestPoster(
                email=pinterest_creds.get('email'),
                password=pinterest_creds.get('password')
            )
        
        # Reddit
        if 'reddit' in credentials:
            reddit_creds = credentials['reddit']
            self.posters['reddit'] = RedditPoster(
                client_id=reddit_creds.get('client_id'),
                client_secret=reddit_creds.get('client_secret'),
                username=reddit_creds.get('username'),
                password=reddit_creds.get('password')
            )
        
        # X/Twitter
        if 'x' in credentials:
            x_creds = credentials['x']
            self.posters['x'] = XPoster(
                api_key=x_creds.get('api_key')
            )
    
    def post_comment_on_post(self, platform: str, post_url: str, context: str = "", user_id: int = None) -> Dict:
        """
        Post a comment on a specific social media post
        
        Args:
            platform: 'tiktok', 'instagram', 'x', 'pinterest', 'reddit'
            post_url: URL of the post to comment on
            context: Optional context about the post for generating relevant comment
        """
        if platform not in self.posters:
            return {
                'success': False,
                'error': f'Platform {platform} not supported',
                'platform': platform
            }
        
        if not self.analysis:
            return {
                'success': False,
                'error': 'Campaign not analyzed yet. Call setup_campaign first.',
                'platform': platform
            }
        
        try:
            poster = self.posters[platform]
            
            # Generate comment
            comment = poster.generate_comment(
                company_url=self.company_url,
                field=self.analysis.get('field', 'business'),
                offerings=self.analysis.get('offerings', []),
                context=context
            )
            
            # Post comment
            result = poster.post_comment(post_url, comment)
            
            # Save to database if available
            if self.db and self.campaign_id and user_id:
                if result.get('success'):
                    self.db.save_comment(
                        campaign_id=self.campaign_id,
                        user_id=user_id,
                        platform=platform,
                        post_url=post_url,
                        comment=comment,
                        comment_id=result.get('comment_id'),
                        comment_url=result.get('comment_url'),
                        status='posted'
                    )
                else:
                    # Save failed attempt
                    self.db.save_comment(
                        campaign_id=self.campaign_id,
                        user_id=user_id,
                        platform=platform,
                        post_url=post_url,
                        comment=comment,
                        status='failed',
                        error_message=result.get('error')
                    )
            
            return result
            
        except Exception as e:
            logger.error(f"Error posting comment on {platform}: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'platform': platform
            }
    
    def post_comments_batch(self, posts: List[Dict], user_id: int) -> Dict:
        """
        Post comments on multiple posts
        
        Args:
            posts: List of dicts with 'platform' and 'post_url'
            user_id: User ID for database tracking
        """
        results = []
        
        for post in posts:
            platform = post.get('platform')
            post_url = post.get('post_url')
            context = post.get('context', '')
            
            if not platform or not post_url:
                results.append({
                    'success': False,
                    'error': 'Missing platform or post_url',
                    'post': post
                })
                continue
            
            result = self.post_comment_on_post(platform, post_url, context)
            result['user_id'] = user_id
            results.append(result)
        
        # Calculate statistics
        successful = sum(1 for r in results if r.get('success'))
        failed = len(results) - successful
        
        return {
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'results': results
        }
    
    def get_campaign_summary(self) -> Dict:
        """Get summary of the campaign"""
        if not self.analysis:
            return {
                'error': 'Campaign not analyzed yet'
            }
        
        return {
            'company_url': self.company_url,
            'campaign_id': self.campaign_id,
            'field': self.analysis.get('field'),
            'offerings': self.analysis.get('offerings'),
            'keywords': self.analysis.get('keywords'),
            'summary': self.analysis.get('summary')
        }

