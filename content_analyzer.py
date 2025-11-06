#!/usr/bin/env python3
"""
Content Analyzer Module
Analyzes markdown content to identify company field of work and offerings
"""

import re
import logging
from typing import Dict, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """Analyze website content to identify business field and offerings"""
    
    # Industry keywords mapping
    INDUSTRY_KEYWORDS = {
        'software': ['software', 'app', 'application', 'platform', 'saas', 'api', 'development', 'programming', 'code', 'tech'],
        'ecommerce': ['shop', 'store', 'buy', 'sell', 'product', 'cart', 'checkout', 'payment', 'shipping', 'delivery'],
        'consulting': ['consulting', 'consultant', 'advisory', 'expert', 'strategy', 'solution', 'service'],
        'marketing': ['marketing', 'advertising', 'seo', 'social media', 'campaign', 'brand', 'promotion', 'lead'],
        'healthcare': ['health', 'medical', 'doctor', 'hospital', 'clinic', 'treatment', 'therapy', 'patient'],
        'education': ['education', 'learning', 'course', 'training', 'school', 'university', 'student', 'tutor'],
        'finance': ['finance', 'financial', 'bank', 'investment', 'loan', 'credit', 'money', 'accounting', 'tax'],
        'real_estate': ['real estate', 'property', 'house', 'apartment', 'rent', 'buy', 'sell', 'realty'],
        'food': ['restaurant', 'food', 'cafe', 'dining', 'menu', 'cuisine', 'chef', 'catering'],
        'travel': ['travel', 'tourism', 'hotel', 'booking', 'vacation', 'trip', 'flight'],
        'fitness': ['fitness', 'gym', 'workout', 'exercise', 'training', 'health', 'wellness'],
        'legal': ['law', 'legal', 'attorney', 'lawyer', 'litigation', 'legal services'],
        'design': ['design', 'creative', 'graphic', 'branding', 'logo', 'ui', 'ux', 'art'],
    }
    
    # Offering patterns
    OFFERING_PATTERNS = [
        r'we (?:offer|provide|sell|deliver|create|build)',
        r'our (?:service|product|solution|offering)',
        r'(?:service|product|solution|tool) (?:for|to|that)',
        r'help(?:ing|s)? (?:you|businesses|companies)',
        r'specializ(?:e|ing|ed) in',
        r'expert (?:in|at)',
        r'offer(?:ing|s)?',
        r'provid(?:e|ing|es)',
    ]
    
    def __init__(self, markdown_content: str):
        self.content = markdown_content.lower()
        self.analyzed = False
        self.field = None
        self.offerings = []
        self.keywords = []
    
    def analyze(self) -> Dict:
        """Analyze content and return findings"""
        if self.analyzed:
            return self._get_results()
        
        # Identify industry/field
        self.field = self._identify_field()
        
        # Extract offerings
        self.offerings = self._extract_offerings()
        
        # Extract keywords
        self.keywords = self._extract_keywords()
        
        self.analyzed = True
        
        return self._get_results()
    
    def _identify_field(self) -> str:
        """Identify the main field of work"""
        field_scores = {}
        
        for field, keywords in self.INDUSTRY_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in self.content)
            if score > 0:
                field_scores[field] = score
        
        if field_scores:
            # Return field with highest score
            return max(field_scores.items(), key=lambda x: x[1])[0]
        
        return 'general'
    
    def _extract_offerings(self) -> List[str]:
        """Extract what the company offers"""
        offerings = []
        
        # Look for offering patterns
        for pattern in self.OFFERING_PATTERNS:
            matches = re.finditer(pattern, self.content, re.IGNORECASE)
            for match in matches:
                # Extract context around the match
                start = max(0, match.start() - 50)
                end = min(len(self.content), match.end() + 100)
                context = self.content[start:end]
                
                # Try to extract a sentence or phrase
                sentences = re.split(r'[.!?]\s+', context)
                for sentence in sentences:
                    if any(keyword in sentence for keyword in ['offer', 'provide', 'service', 'product', 'solution']):
                        # Clean up the sentence
                        sentence = sentence.strip()
                        if len(sentence) > 20 and len(sentence) < 200:
                            offerings.append(sentence)
        
        # Remove duplicates and sort by relevance
        unique_offerings = []
        seen = set()
        for offering in offerings:
            offering_lower = offering.lower()
            if offering_lower not in seen:
                seen.add(offering_lower)
                unique_offerings.append(offering)
        
        return unique_offerings[:5]  # Return top 5
    
    def _extract_keywords(self) -> List[str]:
        """Extract important keywords from content"""
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should', 'could', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who', 'whom', 'whose', 'where', 'when', 'why', 'how'}
        
        # Extract words
        words = re.findall(r'\b[a-z]{4,}\b', self.content)
        
        # Filter stop words and get frequency
        filtered_words = [w for w in words if w not in stop_words]
        word_freq = Counter(filtered_words)
        
        # Return top keywords
        top_keywords = [word for word, count in word_freq.most_common(20)]
        
        return top_keywords
    
    def _get_results(self) -> Dict:
        """Get analysis results"""
        return {
            'field': self.field,
            'offerings': self.offerings,
            'keywords': self.keywords,
            'summary': self._generate_summary()
        }
    
    def _generate_summary(self) -> str:
        """Generate a summary of the company"""
        summary_parts = []
        
        if self.field and self.field != 'general':
            summary_parts.append(f"Company operates in the {self.field} industry")
        
        if self.offerings:
            summary_parts.append(f"Main offerings: {', '.join(self.offerings[:2])}")
        
        if not summary_parts:
            summary_parts.append("General business")
        
        return ". ".join(summary_parts)

