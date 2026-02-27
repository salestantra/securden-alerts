#!/usr/bin/env python3
"""
Cybersecurity News Monitor
Scrapes TheHackerNews and BleepingComputer for cyberattack news
Stores in MongoDB and sends monthly digest emails
"""

import os
import sys
from datetime import datetime, timezone, timedelta
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
import resend
import re

# Configuration from environment variables
MONGODB_URL = os.environ.get('MONGODB_URL')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL')
SENDER_EMAIL = 'onboarding@resend.dev'  # Resend's default sender

# Cyberattack keywords for filtering
ATTACK_KEYWORDS = [
        'attack', 'breach', 'hacked', 'ransomware', 'malware', 'exploit',
        'vulnerability', 'data leak', 'compromise', 'zero-day', 'backdoor',
        'trojan', 'phishing', 'ddos', 'intrusion', 'penetration', 'incident',
        'threat actor', 'cyber attack', 'security breach', 'exposed', 'stolen data'
]

class CyberNewsMonitor:
        def __init__(self):
                    # Initialize MongoDB
                    try:
                                    self.mongo_client = MongoClient(MONGODB_URL)
                                    self.db = self.mongo_client.cybersecurity_news
                                    self.articles_collection = self.db.articles
                                    self.config_collection = self.db.config
                                    print("Connected to MongoDB")
except Exception as e:
            print(f"MongoDB connection failed: {e}")
            sys.exit(1)

        # Initialize Resend
        if RESEND_API_KEY:
                        resend.api_key = RESEND_API_KEY
                        print("Resend API configured")
else:
                print("Resend API key not configured")

    def scrape_thehackernews(self):
                """Scrape The Hacker News for cybersecurity articles"""
                try:
                                print("\nScraping TheHackerNews...")
                                response = requests.get('https://thehackernews.com/', timeout=30, headers={
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                                })
                                response.raise_for_status()
                                soup = BeautifulSoup(response.content, 'html.parser')
                                articles = []

                    # Find all links that point to thehackernews.com/20XX articles
                                article_links = soup.find_all('a', href=lambda x: x and 'thehackernews.com/20' in x)
                                seen_urls = set()

                    for link in article_links[:20]:
                                        try:
                                                                url = link.get('href', '')
                                                                if not url or url in seen_urls:
                                                                                            continue
                                                                                        seen_urls.add(url)

                                            # Get title - clean up the date and category info
                                                                title = link.get_text(strip=True)
                                                                title = re.sub(r'[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}', '', title)
                                                                title = re.sub(r'(Cyber Security|Cloud Security|Security Operations|Hacking|Malware|Data Breach).*$', '', title)
                                                                title = title.strip()
                                                                if not title or len(title) < 20:
                                                                                            continue

                                                                # Check if article matches cyberattack keywords
                                                                content_to_check = title.lower()
                                                                is_attack = any(keyword in content_to_check for keyword in ATTACK_KEYWORDS)

                                            articles.append({
                                                                        'title': title,
                                                                        'url': url,
                                                                        'source': 'thehackernews',
                                                                        'is_cyberattack': is_attack,
                                                                        'scraped_at': datetime.now(timezone.utc)
                                            })
except Exception as e:
                    continue

            print(f"Found {len(articles)} articles from TheHackerNews")
            return articles
except Exception as e:
            print(f"Error scraping TheHackerNews: {e}")
            return []

    def scrape_bleepingcomputer(self):
                """Scrape BleepingComputer for cybersecurity articles"""
        try:
                        print("\nScraping BleepingComputer...")
            response = requests.get('https://www.bleepingcomputer.com/', timeout=30, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []

            # Find all links that point to /news/ articles
            article_links = soup.find_all('a', href=lambda x: x and '/news/' in x)
            seen_urls = set()

            for link in article_links[:20]:
                                try:
                                                        url = link.get('href', '')
                                                        # Ensure full URL
                                                        if url and not url.startswith('http'):
                                                                                    url = 'https://www.bleepingcomputer.com' + url
                                                                                if not url or url in seen_urls:
                                                                                                            continue
                                                                                                        seen_urls.add(url)

                    # Get title
                    title = link.get_text(strip=True)
                    if not title or len(title) < 20:
                                                continue

                    # Check if article matches cyberattack keywords
                    content_to_check = title.lower()
                    is_attack = any(keyword in content_to_check for keyword in ATTACK_KEYWORDS)

                    articles.append({
                                                'title': title,
                                                'url': url,
                                                'source': 'bleepingcomputer',
                                                'is_cyberattack': is_attack,
                                                'scraped_at': datetime.now(timezone.utc)
                    })
except Exception as e:
                    continue

            print(f"Found {len(articles)} articles from BleepingComputer")
            return articles
except Exception as e:
            print(f"Error scraping BleepingComputer: {e}")
            return []

    def store_articles(self, articles):
                """Store articles in MongoDB, avoiding duplicates"""
        stored_count = 0
        for article in articles:
                        try:
                                            # Check if article already exists (by URL)
                                            existing = self.articles_collection.find_one({'url': article['url']})
                if not existing:
                                        self.articles_collection.insert_one(article)
                    stored_count += 1
except Exception as e:
                print(f"Error storing article: {e}")
                continue

        print(f"\nStored {stored_count} new articles (duplicates skipped)")
        return stored_count

    def should_send_digest(self):
                """Check if monthly digest should be sent"""
        config = self.config_collection.find_one({'type': 'digest_config'})
        if not config:
                        # First time - create config
                        self.config_collection.insert_one({
                                            'type': 'digest_config',
                                            'last_digest_sent': None,
                                            'created_at': datetime.now(timezone.utc)
                        })
            return True  # Send first digest

        last_sent = config.get('last_digest_sent')
        if not last_sent:
                        return True

        # Check if 30 days have passed
        days_since_last = (datetime.now(timezone.utc) - last_sent).days
        return days_since_last >= 30

    def send_digest_email(self):
                """Send monthly digest email with cyberattack articles"""
        if not RESEND_API_KEY:
                        print("Skipping email - Resend API key not configured")
            return

        try:
                        print("\nPreparing monthly digest email...")

            # Get config
            config = self.config_collection.find_one({'type': 'digest_config'})

            # Determine date range
            if config and config.get('last_digest_sent'):
                                since_date = config['last_digest_sent']
else:
                since_date = datetime.now(timezone.utc) - timedelta(days=30)

            # Get cyberattack articles since last digest
            articles = list(self.articles_collection.find({
                                'is_cyberattack': True,
                                'scraped_at': {'$gte': since_date}
            }).sort('scraped_at', -1))

            if not articles:
                                print("No new cyberattack articles to send")
                return

            print(f"Found {len(articles)} cyberattack articles")

            # Generate HTML email
            html_content = self.generate_digest_html(articles, since_date)

            # Send email
            params = {
                                "from": SENDER_EMAIL,
                                "to": [RECIPIENT_EMAIL],
                                "subject": f"Monthly Cybersecurity Digest - {len(articles)} New Attacks/Breaches",
                                "html": html_content
            }

            email = resend.Emails.send(params)
            print(f"Digest email sent successfully to {RECIPIENT_EMAIL}")
            print(f"  Email ID: {email.get('id')}")

            # Update last_digest_sent
            self.config_collection.update_one(
                                {'type': 'digest_config'},
                                {'$set': {'last_digest_sent': datetime.now(timezone.utc)}},
                                upsert=True
            )

except Exception as e:
            print(f"Error sending digest email: {e}")

    def generate_digest_html(self, articles, since_date):
                """Generate HTML content for digest email"""
        # Group by source
        by_source = {}
        for article in articles:
                        source = article['source']
            if source not in by_source:
                                by_source[source] = []
            by_source[source].append(article)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
                            .header {{ background: linear-gradient(135deg, #dc2626 0%, #ea580c 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 30px; }}
                                    .header h1 {{ margin: 0; font-size: 28px; }}
                                            .header p {{ margin: 10px 0 0 0; opacity: 0.9; }}
                                                    .stats {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 30px; text-align: center; }}
                                                            .stat-number {{ font-size: 48px; font-weight: bold; color: #dc2626; }}
                                                                    .stat-label {{ color: #666; font-size: 14px; margin-top: 10px; }}
                                                                            .source-section {{ margin-bottom: 40px; }}
                                                                                    .source-title {{ font-size: 22px; font-weight: bold; color: #dc2626; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #dc2626; }}
                                                                                            .article {{ background: white; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin-bottom: 15px; }}
                                                                                                    .article-title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
                                                                                                            .article-title a {{ color: #333; text-decoration: none; }}
                                                                                                                    .article-title a:hover {{ color: #dc2626; }}
                                                                                                                            .article-meta {{ color: #666; font-size: 14px; margin-bottom: 10px; }}
                                                                                                                                    .article-link {{ color: #dc2626; font-size: 14px; text-decoration: none; font-weight: 600; }}
                                                                                                                                            .footer {{ text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e0e0e0; color: #666; font-size: 14px; }}
                                                                                                                                                </style>
                                                                                                                                                </head>
                                                                                                                                                <body>
                                                                                                                                                    <div class="header">
                                                                                                                                                            <h1>Monthly Cybersecurity Digest</h1>
                                                                                                                                                                    <p>Period: {since_date.strftime('%B %d, %Y')} - {datetime.now(timezone.utc).strftime('%B %d, %Y')}</p>
                                                                                                                                                                        </div>
                                                                                                                                                                            <div class="stats">
                                                                                                                                                                                    <div class="stat-number">{len(articles)}</div>
                                                                                                                                                                                            <div class="stat-label">Cyberattack &amp; Breach Incidents This Month</div>
                                                                                                                                                                                                </div>
                                                                                                                                                                                                """

        # Add articles by source
        for source, source_articles in by_source.items():
                        source_name = "The Hacker News" if source == "thehackernews" else "BleepingComputer"
            html += f"""
                <div class="source-section">
                        <div class="source-title">{source_name} ({len(source_articles)} incidents)</div>
                        """
            for article in source_articles:
                                scraped_date = article['scraped_at'].strftime('%B %d, %Y')
                html += f"""
                        <div class="article">
                                    <div class="article-title">
                                                    <a href="{article['url']}" target="_blank">{article['title']}</a>
            </div>
            <div class="article-meta">Reported: {scraped_date}</div>
            <a href="{article['url']}" class="article-link" target="_blank">Read full article</a>
        </div>
"""
            html += "    </div>"

        html += """
    <div class="footer">
        <p>This is an automated monthly digest from your Cybersecurity News Monitor</p>
        <p>Stay vigilant and stay secure!</p>
    </div>
</body>
</html>
"""
        return html

            def run(self):
                    """Main execution function"""
                            print("\n" + "="*60)
                                    print("CYBERSECURITY NEWS MONITOR")
                                            print("="*60)
                                                    print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")

                                                            # Scrape both sites
                                                                    thehackernews_articles = self.scrape_thehackernews()
                                                                            bleepingcomputer_articles = self.scrape_bleepingcomputer()
                                                                                    all_articles = thehackernews_articles + bleepingcomputer_articles

                                                                                            print(f"\nTotal articles found: {len(all_articles)}")

                                                                                                    # Store articles
                                                                                                            stored = self.store_articles(all_articles)
                                                                                                            
                                                                                                                    # Check if digest should be sent
                                                                                                                            if self.should_send_digest():
                                                                                                                                        print("\nMonthly digest due - sending email...")
                                                                                                                                                    self.send_digest_email()
                                                                                                                                                            else:
                                                                                                                                                                        print("\nMonthly digest not due yet")
                                                                                                                                                                        
                                                                                                                                                                                # Print summary
                                                                                                                                                                                        total_articles = self.articles_collection.count_documents({})
                                                                                                                                                                                                cyberattack_articles = self.articles_collection.count_documents({'is_cyberattack': True})
                                                                                                                                                                                                
                                                                                                                                                                                                        print("\n" + "="*60)
                                                                                                                                                                                                                print("SUMMARY")
                                                                                                                                                                                                                        print("="*60)
                                                                                                                                                                                                                                print(f"Total articles in database: {total_articles}")
                                                                                                                                                                                                                                        print(f"Cyberattack articles: {cyberattack_articles}")
                                                                                                                                                                                                                                                print(f"New articles added: {stored}")
                                                                                                                                                                                                                                                        print("\nMonitor run completed successfully!")
                                                                                                                                                                                                                                                                print("="*60 + "\n")
                                                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                        # Close MongoDB connection
                                                                                                                                                                                                                                                                                self.mongo_client.close()
                                                                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                                
                                                                                                                                                                                                                                                                                if __name__ == "__main__":
                                                                                                                                                                                                                                                                                    # Validate environment variables
                                                                                                                                                                                                                                                                                        if not MONGODB_URL:
                                                                                                                                                                                                                                                                                                print("Error: MONGODB_URL environment variable not set")
                                                                                                                                                                                                                                                                                                        sys.exit(1)
                                                                                                                                                                                                                                                                                                        
                                                                                                                                                                                                                                                                                                            if not RECIPIENT_EMAIL:
                                                                                                                                                                                                                                                                                                                    print("Error: RECIPIENT_EMAIL environment variable not set")
                                                                                                                                                                                                                                                                                                                            sys.exit(1)
                                                                                                                                                                                                                                                                                                                            
                                                                                                                                                                                                                                                                                                                                # Run monitor
                                                                                                                                                                                                                                                                                                                                    monitor = CyberNewsMonitor()
                                                                                                                                                                                                                                                                                                                                        monitor.run()
