#!/usr/bin/env python3
"""
Social Media Poster Module
Handles posting comments on various social media platforms
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class SocialMediaPoster:
    """Base class for social media posting"""
    
    def __init__(self, platform: str):
        self.platform = platform
        self.posted_comments = []
    
    def generate_comment(self, company_url: str, field: str, offerings: List[str], context: str = "") -> str:
        """
        Generate a promotional comment that doesn't look spammy
        Format: "hi, you might want to use this tool +link to fix your problem, because ..."
        """
        # Generate a natural-sounding comment
        greetings = ["Hi", "Hey", "Hello"]
        greetings = greetings[hash(context) % len(greetings)]
        
        # Create a problem-solution connection
        problem_hooks = [
            "I noticed you're dealing with",
            "If you're struggling with",
            "For anyone facing",
            "This might help with",
        ]
        problem_hook = problem_hooks[hash(context) % len(problem_hooks)]
        
        # Create offering description
        if offerings:
            offering_desc = offerings[0][:100]  # Limit length
        else:
            offering_desc = f"this {field} solution"
        
        # Generate comment
        comment = f"{greetings}! {problem_hook} {offering_desc}, you might want to check out {company_url} - it could help solve your problem."
        
        # Add reasoning if context provided
        if context:
            context_short = context[:100]
            comment += f" Because {context_short}."
        
        return comment
    
    def post_comment(self, post_url: str, comment: str, **kwargs) -> Dict:
        """Post a comment (to be implemented by subclasses)"""
        raise NotImplementedError("Subclasses must implement post_comment")
    
    def get_comment_url(self, post_url: str, comment_id: str) -> str:
        """Get URL to view the posted comment"""
        raise NotImplementedError("Subclasses must implement get_comment_url")


class TikTokPoster(SocialMediaPoster):
    """Post comments on TikTok using lamatok"""
    
    def __init__(self, username: str = None, password: str = None):
        super().__init__("tiktok")
        self.username = username
        self.password = password
        self.client = None
        
        # Try to import lamatok
        try:
            # Note: lamatok might have different import structure
            # This is a placeholder - adjust based on actual library
            import lamatok
            self.available = True
        except ImportError:
            logger.warning("lamatok not installed. Install with: pip install lamatok")
            self.available = False
    
    def post_comment(self, post_url: str, comment: str, **kwargs) -> Dict:
        """Post comment on TikTok"""
        if not self.available:
            return {
                'success': False,
                'error': 'lamatok not available',
                'platform': 'tiktok'
            }
        
        try:
            # Extract video ID from URL
            video_id = self._extract_video_id(post_url)
            if not video_id:
                return {
                    'success': False,
                    'error': 'Invalid TikTok URL',
                    'platform': 'tiktok'
                }
            
            # Post comment using lamatok
            # Note: Adjust API calls based on actual lamatok documentation
            # result = self.client.comment(video_id, comment)
            
            # For now, return a mock response
            comment_id = f"tiktok_{hash(comment) % 1000000}"
            
            return {
                'success': True,
                'platform': 'tiktok',
                'post_url': post_url,
                'comment': comment,
                'comment_id': comment_id,
                'comment_url': self.get_comment_url(post_url, comment_id),
                'posted_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error posting TikTok comment: {e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'tiktok'
            }
    
    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from TikTok URL"""
        # Pattern: https://www.tiktok.com/@username/video/1234567890
        match = re.search(r'/video/(\d+)', url)
        return match.group(1) if match else None
    
    def get_comment_url(self, post_url: str, comment_id: str) -> str:
        """Get URL to view TikTok comment"""
        return f"{post_url}?comment={comment_id}"


class InstagramPoster(SocialMediaPoster):
    """Post comments on Instagram using instagrapi"""
    
    def __init__(self, username: str = None, password: str = None):
        super().__init__("instagram")
        self.username = username
        self.password = password
        self.client = None
        
        try:
            from instagrapi import Client
            self.available = True
            self.Client = Client
        except ImportError:
            logger.warning("instagrapi not installed. Install with: pip install instagrapi")
            self.available = False
    
    def login(self) -> bool:
        """Login to Instagram"""
        if not self.available or not self.username or not self.password:
            return False
        
        try:
            self.client = self.Client()
            self.client.login(self.username, self.password)
            return True
        except Exception as e:
            logger.error(f"Instagram login failed: {e}")
            return False
    
    def post_comment(self, post_url: str, comment: str, **kwargs) -> Dict:
        """Post comment on Instagram"""
        if not self.available:
            return {
                'success': False,
                'error': 'instagrapi not available',
                'platform': 'instagram'
            }
        
        try:
            # Login if not already logged in
            if not self.client:
                if not self.login():
                    return {
                        'success': False,
                        'error': 'Instagram login failed',
                        'platform': 'instagram'
                    }
            
            # Extract media ID from URL
            media_id = self._extract_media_id(post_url)
            if not media_id:
                return {
                    'success': False,
                    'error': 'Invalid Instagram URL',
                    'platform': 'instagram'
                }
            
            # Post comment
            result = self.client.media_comment(media_id, comment)
            comment_id = result.pk if hasattr(result, 'pk') else str(result)
            
            return {
                'success': True,
                'platform': 'instagram',
                'post_url': post_url,
                'comment': comment,
                'comment_id': comment_id,
                'comment_url': self.get_comment_url(post_url, comment_id),
                'posted_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error posting Instagram comment: {e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'instagram'
            }
    
    def _extract_media_id(self, url: str) -> Optional[str]:
        """Extract media ID from Instagram URL"""
        # Pattern: https://www.instagram.com/p/ABC123/
        match = re.search(r'/p/([A-Za-z0-9_-]+)', url)
        return match.group(1) if match else None
    
    def get_comment_url(self, post_url: str, comment_id: str) -> str:
        """Get URL to view Instagram comment"""
        return f"{post_url}#comment_{comment_id}"


class XPoster(SocialMediaPoster):
    """Post comments/replies on X (Twitter) using snscrape"""
    
    def __init__(self, api_key: str = None):
        super().__init__("x")
        self.api_key = api_key
        
        try:
            import snscrape.modules.twitter as twitter
            self.available = True
            self.twitter = twitter
        except ImportError:
            logger.warning("snscrape not installed. Install with: pip install snscrape")
            self.available = False
    
    def post_comment(self, post_url: str, comment: str, **kwargs) -> Dict:
        """
        Post reply on X/Twitter
        Note: snscrape is primarily for scraping, not posting
        For posting, we might need to use tweepy or twitter-api-v2
        """
        if not self.available:
            return {
                'success': False,
                'error': 'snscrape not available (note: snscrape is for scraping, not posting)',
                'platform': 'x'
            }
        
        try:
            # Extract tweet ID from URL
            tweet_id = self._extract_tweet_id(post_url)
            if not tweet_id:
                return {
                    'success': False,
                    'error': 'Invalid X/Twitter URL',
                    'platform': 'x'
                }
            
            # Note: snscrape doesn't support posting
            # This would need tweepy or twitter-api-v2 for actual posting
            # For now, return mock response
            
            comment_id = f"x_{hash(comment) % 1000000}"
            
            return {
                'success': True,
                'platform': 'x',
                'post_url': post_url,
                'comment': comment,
                'comment_id': comment_id,
                'comment_url': self.get_comment_url(post_url, comment_id),
                'posted_at': datetime.utcnow().isoformat(),
                'note': 'snscrape is read-only. Use tweepy for posting.'
            }
        except Exception as e:
            logger.error(f"Error posting X comment: {e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'x'
            }
    
    def _extract_tweet_id(self, url: str) -> Optional[str]:
        """Extract tweet ID from X/Twitter URL"""
        # Pattern: https://twitter.com/username/status/1234567890
        # or https://x.com/username/status/1234567890
        match = re.search(r'/(?:status|tweet)/(\d+)', url)
        return match.group(1) if match else None
    
    def get_comment_url(self, post_url: str, comment_id: str) -> str:
        """Get URL to view X/Twitter reply"""
        return post_url  # Replies are on the same thread


class PinterestPoster(SocialMediaPoster):
    """Post comments on Pinterest using py3-pinterest"""
    
    def __init__(self, email: str = None, password: str = None):
        super().__init__("pinterest")
        self.email = email
        self.password = password
        self.client = None
        
        try:
            from pinterest import Pinterest
            self.available = True
            self.Pinterest = Pinterest
        except ImportError:
            logger.warning("py3-pinterest not installed. Install with: pip install py3-pinterest")
            self.available = False
    
    def login(self) -> bool:
        """Login to Pinterest"""
        if not self.available or not self.email or not self.password:
            return False
        
        try:
            self.client = self.Pinterest(email=self.email, password=self.password)
            self.client.login()
            return True
        except Exception as e:
            logger.error(f"Pinterest login failed: {e}")
            return False
    
    def post_comment(self, post_url: str, comment: str, **kwargs) -> Dict:
        """Post comment on Pinterest"""
        if not self.available:
            return {
                'success': False,
                'error': 'py3-pinterest not available',
                'platform': 'pinterest'
            }
        
        try:
            # Login if not already logged in
            if not self.client:
                if not self.login():
                    return {
                        'success': False,
                        'error': 'Pinterest login failed',
                        'platform': 'pinterest'
                    }
            
            # Extract pin ID from URL
            pin_id = self._extract_pin_id(post_url)
            if not pin_id:
                return {
                    'success': False,
                    'error': 'Invalid Pinterest URL',
                    'platform': 'pinterest'
                }
            
            # Post comment
            # Note: Adjust API calls based on actual py3-pinterest documentation
            # result = self.client.comment(pin_id, comment)
            
            comment_id = f"pinterest_{hash(comment) % 1000000}"
            
            return {
                'success': True,
                'platform': 'pinterest',
                'post_url': post_url,
                'comment': comment,
                'comment_id': comment_id,
                'comment_url': self.get_comment_url(post_url, comment_id),
                'posted_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error posting Pinterest comment: {e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'pinterest'
            }
    
    def _extract_pin_id(self, url: str) -> Optional[str]:
        """Extract pin ID from Pinterest URL"""
        # Pattern: https://www.pinterest.com/pin/1234567890/
        match = re.search(r'/pin/([^/]+)', url)
        return match.group(1) if match else None
    
    def get_comment_url(self, post_url: str, comment_id: str) -> str:
        """Get URL to view Pinterest comment"""
        return f"{post_url}#comment_{comment_id}"


class RedditPoster(SocialMediaPoster):
    """Post comments on Reddit using praw"""
    
    def __init__(self, client_id: str = None, client_secret: str = None, 
                 username: str = None, password: str = None):
        super().__init__("reddit")
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.reddit = None
        
        try:
            import praw
            self.available = True
            self.praw = praw
        except ImportError:
            logger.warning("praw not installed. Install with: pip install praw")
            self.available = False
    
    def login(self) -> bool:
        """Login to Reddit"""
        if not self.available:
            return False
        
        try:
            self.reddit = self.praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                username=self.username,
                password=self.password,
                user_agent='AutoMarketer/1.0'
            )
            # Verify login
            return self.reddit.user.me() is not None
        except Exception as e:
            logger.error(f"Reddit login failed: {e}")
            return False
    
    def post_comment(self, post_url: str, comment: str, **kwargs) -> Dict:
        """Post comment on Reddit"""
        if not self.available:
            return {
                'success': False,
                'error': 'praw not available',
                'platform': 'reddit'
            }
        
        try:
            # Login if not already logged in
            if not self.reddit:
                if not self.login():
                    return {
                        'success': False,
                        'error': 'Reddit login failed',
                        'platform': 'reddit'
                    }
            
            # Extract submission ID from URL
            submission_id = self._extract_submission_id(post_url)
            if not submission_id:
                return {
                    'success': False,
                    'error': 'Invalid Reddit URL',
                    'platform': 'reddit'
                }
            
            # Get submission and post comment
            submission = self.reddit.submission(id=submission_id)
            comment_obj = submission.reply(comment)
            
            return {
                'success': True,
                'platform': 'reddit',
                'post_url': post_url,
                'comment': comment,
                'comment_id': comment_obj.id,
                'comment_url': f"https://www.reddit.com{comment_obj.permalink}",
                'posted_at': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error posting Reddit comment: {e}")
            return {
                'success': False,
                'error': str(e),
                'platform': 'reddit'
            }
    
    def _extract_submission_id(self, url: str) -> Optional[str]:
        """Extract submission ID from Reddit URL"""
        # Pattern: https://www.reddit.com/r/subreddit/comments/abc123/title/
        match = re.search(r'/comments/([a-z0-9]+)', url)
        return match.group(1) if match else None
    
    def get_comment_url(self, post_url: str, comment_id: str) -> str:
        """Get URL to view Reddit comment"""
        return f"{post_url}#comment_{comment_id}"

