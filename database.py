#!/usr/bin/env python3
"""
Database module for API keys, credits, usage tracking, and logs
"""

import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)

class Database:
    """Database manager for API keys, credits, and usage"""
    
    def __init__(self, db_path: str = "passivleads.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # API Keys table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                api_key_hash TEXT NOT NULL,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Credits table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL DEFAULT 0.0,
                currency TEXT DEFAULT 'USD',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Credit transactions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS credit_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                transaction_type TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Usage tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                api_key_id INTEGER,
                user_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                cost REAL NOT NULL,
                status_code INTEGER,
                request_data TEXT,
                response_data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (api_key_id) REFERENCES api_keys(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Service costs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_costs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT UNIQUE NOT NULL,
                endpoint TEXT NOT NULL,
                cost_per_request REAL NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Auto marketer campaigns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_marketer_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                company_url TEXT NOT NULL,
                company_field TEXT,
                company_offerings TEXT,
                markdown_content TEXT,
                analysis_summary TEXT,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Posted comments tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                post_url TEXT NOT NULL,
                comment TEXT NOT NULL,
                comment_id TEXT,
                comment_url TEXT,
                status TEXT DEFAULT 'posted',
                error_message TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (campaign_id) REFERENCES auto_marketer_campaigns(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Initialize default service costs
        default_costs = [
            ('email_finder', '/api/v1/email-finder', 0.01, 'Find emails from a single URL'),
            ('email_finder_csv', '/api/v1/email-finder/csv', 0.05, 'Process CSV file with multiple URLs'),
            ('osm_scraper', '/api/v1/osm-scraper', 0.02, 'Scrape OpenStreetMap data for a city'),
            ('auto_marketer', '/api/v1/auto-marketer/start', 0.10, 'Start auto marketing campaign'),
        ]
        
        for service, endpoint, cost, desc in default_costs:
            cursor.execute('''
                INSERT OR IGNORE INTO service_costs (service, endpoint, cost_per_request, description)
                VALUES (?, ?, ?, ?)
            ''', (service, endpoint, cost, desc))
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def create_user(self, username: str, email: Optional[str] = None) -> int:
        """Create a new user and give them 1 USD free credit"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('INSERT INTO users (username, email) VALUES (?, ?)', (username, email))
            user_id = cursor.lastrowid
            
            # Give 1 USD free credit
            cursor.execute('INSERT INTO credits (user_id, amount) VALUES (?, ?)', (user_id, 1.0))
            cursor.execute('''
                INSERT INTO credit_transactions (user_id, amount, transaction_type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 1.0, 'credit', 'Free welcome credit'))
            
            conn.commit()
            logger.info(f"Created user {username} with ID {user_id} and 1 USD free credit")
            return user_id
        except sqlite3.IntegrityError as e:
            conn.rollback()
            logger.error(f"Error creating user: {e}")
            raise
        finally:
            conn.close()
    
    def create_api_key(self, user_id: int, name: Optional[str] = None) -> Tuple[str, str]:
        """Create a new API key for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Generate API key
        api_key = f"pl_{secrets.token_urlsafe(32)}"
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        cursor.execute('''
            INSERT INTO api_keys (user_id, api_key_hash, name)
            VALUES (?, ?, ?)
        ''', (user_id, api_key_hash, name))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created API key for user {user_id}")
        return api_key, api_key_hash
    
    def validate_api_key(self, api_key: str) -> Optional[Dict]:
        """Validate API key and return user info"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        cursor.execute('''
            SELECT ak.id, ak.user_id, ak.name, ak.last_used_at, u.username, u.email
            FROM api_keys ak
            JOIN users u ON ak.user_id = u.id
            WHERE ak.api_key_hash = ? AND ak.is_active = 1 AND u.is_active = 1
        ''', (api_key_hash,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            # Update last used
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('UPDATE api_keys SET last_used_at = ? WHERE id = ?', 
                         (datetime.utcnow().isoformat(), result['id']))
            conn.commit()
            conn.close()
            
            return {
                'api_key_id': result['id'],
                'user_id': result['user_id'],
                'username': result['username'],
                'email': result['email'],
                'key_name': result['name']
            }
        return None
    
    def get_user_credits(self, user_id: int) -> float:
        """Get current credit balance for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT amount FROM credits WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result['amount'] if result else 0.0
    
    def deduct_credits(self, user_id: int, amount: float, description: str = "API usage") -> bool:
        """Deduct credits from user account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check current balance
        current_balance = self.get_user_credits(user_id)
        
        if current_balance < amount:
            conn.close()
            return False
        
        # Deduct credits
        new_balance = current_balance - amount
        cursor.execute('UPDATE credits SET amount = ?, updated_at = ? WHERE user_id = ?',
                      (new_balance, datetime.utcnow().isoformat(), user_id))
        
        # Log transaction
        cursor.execute('''
            INSERT INTO credit_transactions (user_id, amount, transaction_type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, -amount, 'debit', description))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deducted {amount} credits from user {user_id}. New balance: {new_balance}")
        return True
    
    def add_credits(self, user_id: int, amount: float, description: str = "Credit purchase"):
        """Add credits to user account"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        current_balance = self.get_user_credits(user_id)
        new_balance = current_balance + amount
        
        cursor.execute('UPDATE credits SET amount = ?, updated_at = ? WHERE user_id = ?',
                      (new_balance, datetime.utcnow().isoformat(), user_id))
        
        cursor.execute('''
            INSERT INTO credit_transactions (user_id, amount, transaction_type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, 'credit', description))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Added {amount} credits to user {user_id}. New balance: {new_balance}")
    
    def log_usage(self, api_key_id: Optional[int], user_id: int, service: str, 
                  endpoint: str, cost: float, status_code: int = 200,
                  request_data: Optional[str] = None, response_data: Optional[str] = None):
        """Log API usage"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO usage_logs (api_key_id, user_id, service, endpoint, cost, 
                                   status_code, request_data, response_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (api_key_id, user_id, service, endpoint, cost, status_code, 
              request_data, response_data))
        
        conn.commit()
        conn.close()
    
    def get_service_cost(self, service: str, endpoint: str) -> float:
        """Get cost for a service endpoint"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT cost_per_request FROM service_costs 
            WHERE service = ? AND endpoint = ?
        ''', (service, endpoint))
        
        result = cursor.fetchone()
        conn.close()
        
        return result['cost_per_request'] if result else 0.01  # Default cost
    
    def get_user_usage_stats(self, user_id: int, days: int = 30) -> Dict:
        """Get usage statistics for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Total requests
        cursor.execute('''
            SELECT COUNT(*) as total, SUM(cost) as total_cost
            FROM usage_logs
            WHERE user_id = ? AND created_at >= ?
        ''', (user_id, since))
        
        total_stats = cursor.fetchone()
        
        # By service
        cursor.execute('''
            SELECT service, COUNT(*) as count, SUM(cost) as cost
            FROM usage_logs
            WHERE user_id = ? AND created_at >= ?
            GROUP BY service
        ''', (user_id, since))
        
        by_service = [dict(row) for row in cursor.fetchall()]
        
        # By endpoint
        cursor.execute('''
            SELECT endpoint, COUNT(*) as count, SUM(cost) as cost
            FROM usage_logs
            WHERE user_id = ? AND created_at >= ?
            GROUP BY endpoint
        ''', (user_id, since))
        
        by_endpoint = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            'total_requests': total_stats['total'] or 0,
            'total_cost': total_stats['total_cost'] or 0.0,
            'by_service': by_service,
            'by_endpoint': by_endpoint
        }
    
    def get_user_logs(self, user_id: int, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get usage logs for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ul.*, ak.name as api_key_name
            FROM usage_logs ul
            LEFT JOIN api_keys ak ON ul.api_key_id = ak.id
            WHERE ul.user_id = ?
            ORDER BY ul.created_at DESC
            LIMIT ? OFFSET ?
        ''', (user_id, limit, offset))
        
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return logs
    
    def get_user_api_keys(self, user_id: int) -> List[Dict]:
        """Get all API keys for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, created_at, last_used_at, is_active
            FROM api_keys
            WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        
        keys = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return keys
    
    def get_credit_transactions(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get credit transactions for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM credit_transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        transactions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return transactions
    
    def create_campaign(self, user_id: int, company_url: str, company_field: str = None,
                       company_offerings: str = None, markdown_content: str = None,
                       analysis_summary: str = None) -> int:
        """Create a new auto marketer campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO auto_marketer_campaigns 
            (user_id, company_url, company_field, company_offerings, markdown_content, analysis_summary)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, company_url, company_field, company_offerings, markdown_content, analysis_summary))
        
        campaign_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Created campaign {campaign_id} for user {user_id}")
        return campaign_id
    
    def get_campaign(self, campaign_id: int) -> Optional[Dict]:
        """Get campaign by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM auto_marketer_campaigns WHERE id = ?', (campaign_id,))
        result = cursor.fetchone()
        conn.close()
        
        return dict(result) if result else None
    
    def get_user_campaigns(self, user_id: int, limit: int = 50) -> List[Dict]:
        """Get all campaigns for a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM auto_marketer_campaigns
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        campaigns = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return campaigns
    
    def save_comment(self, campaign_id: int, user_id: int, platform: str, post_url: str,
                    comment: str, comment_id: str = None, comment_url: str = None,
                    status: str = 'posted', error_message: str = None) -> int:
        """Save a posted comment to the database"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO posted_comments
            (campaign_id, user_id, platform, post_url, comment, comment_id, comment_url, status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (campaign_id, user_id, platform, post_url, comment, comment_id, comment_url, status, error_message))
        
        comment_db_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Saved comment {comment_db_id} for campaign {campaign_id}")
        return comment_db_id
    
    def get_campaign_comments(self, campaign_id: int, limit: int = 100) -> List[Dict]:
        """Get all comments for a campaign"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM posted_comments
            WHERE campaign_id = ?
            ORDER BY posted_at DESC
            LIMIT ?
        ''', (campaign_id, limit))
        
        comments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return comments
    
    def get_user_comments(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Get all comments posted by a user"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT pc.*, amc.company_url as campaign_url
            FROM posted_comments pc
            JOIN auto_marketer_campaigns amc ON pc.campaign_id = amc.id
            WHERE pc.user_id = ?
            ORDER BY pc.posted_at DESC
            LIMIT ?
        ''', (user_id, limit))
        
        comments = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return comments
    
    def get_comment_stats(self, campaign_id: int = None, user_id: int = None) -> Dict:
        """Get statistics about posted comments"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if campaign_id:
            cursor.execute('''
                SELECT 
                    platform,
                    status,
                    COUNT(*) as count
                FROM posted_comments
                WHERE campaign_id = ?
                GROUP BY platform, status
            ''', (campaign_id,))
        elif user_id:
            cursor.execute('''
                SELECT 
                    platform,
                    status,
                    COUNT(*) as count
                FROM posted_comments
                WHERE user_id = ?
                GROUP BY platform, status
            ''', (user_id,))
        else:
            cursor.execute('''
                SELECT 
                    platform,
                    status,
                    COUNT(*) as count
                FROM posted_comments
                GROUP BY platform, status
            ''')
        
        stats = {}
        for row in cursor.fetchall():
            platform = row['platform']
            status = row['status']
            count = row['count']
            
            if platform not in stats:
                stats[platform] = {}
            stats[platform][status] = count
        
        conn.close()
        return stats

