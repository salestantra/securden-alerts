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
        try:
            self.mongo_client = MongoClient(MONGODB_URL)
            self.db = self.mongo_client.cybersecurity_news
            self.articles_collection = self.db.articles
            self.config_collection = self.db.config
            print("Connected to MongoDB")
        except Exception as e:
            print(f"MongoDB connection failed: {e}")
            sys.exit(1)

        if RESEND_API_KEY:
            resend.api_key = RESEND_API_KEY
            print("Resend API configured")
        else:
            print("Resend API key not configured")

    def scrape_thehackernews(self):
        try:
            response = requests.get('https://thehackernews.com/', timeout=30,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            article_links = soup.find_all('a', href=lambda x: x and 'thehackernews.com/20' in x)
            seen_urls = set()
            for link in article_links[:20]:
                try:
                    url = link.get('href', '')
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = link.get_text(strip=True)
                    title = re.sub(r'[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}', '', title).strip()
                    if not title or len(title) < 20:
                        continue
                    is_attack = any(kw in title.lower() for kw in ATTACK_KEYWORDS)
                    articles.append({
                        'title': title, 'url': url, 'source': 'thehackernews',
                        'is_cyberattack': is_attack, 'scraped_at': datetime.now(timezone.utc)
                    })
                except Exception:
                    continue
            print(f"Found {len(articles)} articles from TheHackerNews")
            return articles
        except Exception as e:
            print(f"Error scraping TheHackerNews: {e}")
            return []

    def scrape_bleepingcomputer(self):
        try:
            response = requests.get('https://www.bleepingcomputer.com/', timeout=30,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            articles = []
            article_links = soup.find_all('a', href=lambda x: x and '/news/' in x)
            seen_urls = set()
            for link in article_links[:20]:
                try:
                    url = link.get('href', '')
                    if url and not url.startswith('http'):
                        url = 'https://www.bleepingcomputer.com' + url
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = link.get_text(strip=True)
                    if not title or len(title) < 20:
                        continue
                    is_attack = any(kw in title.lower() for kw in ATTACK_KEYWORDS)
                    articles.append({
                        'title': title, 'url': url, 'source': 'bleepingcomputer',
                        'is_cyberattack': is_attack, 'scraped_at': datetime.now(timezone.utc)
                    })
                except Exception:
                    continue
            print(f"Found {len(articles)} articles from BleepingComputer")
            return articles
        except Exception as e:
            print(f"Error scraping BleepingComputer: {e}")
            return []

    def store_articles(self, articles):
        stored_count = 0
        for article in articles:
            try:
                if not self.articles_collection.find_one({'url': article['url']}):
                    self.articles_collection.insert_one(article)
                    stored_count += 1
            except Exception as e:
                print(f"Error storing article: {e}")
        print(f"Stored {stored_count} new articles")
        return stored_count

    def should_send_digest(self):
        config = self.config_collection.find_one({'type': 'digest_config'})
        if not config:
            self.config_collection.insert_one({
                'type': 'digest_config',
                'last_digest_sent': None,
                'created_at': datetime.now(timezone.utc)
            })
            return True
        last_sent = config.get('last_digest_sent')
        if not last_sent:
            return True
        return (datetime.now(timezone.utc) - last_sent.replace(tzinfo=timezone.utc)).days >= 30

    def send_digest_email(self):
        if not RESEND_API_KEY:
            print("Skipping email - no API key")
            return
        try:
            config = self.config_collection.find_one({'type': 'digest_config'})
            since_date = (config.get('last_digest_sent').replace(tzinfo=timezone.utc) if config and config.get('last_digest_sent')
                         else datetime.now(timezone.utc) - timedelta(days=30))
            articles = list(self.articles_collection.find(
                {'is_cyberattack': True, 'scraped_at': {'$gte': since_date}}
            ).sort('scraped_at', -1))
            if not articles:
                print("No new cyberattack articles to send")
                return
            html_content = self.generate_digest_html(articles, since_date)
            params = {
                "from": SENDER_EMAIL,
                "to": [RECIPIENT_EMAIL],
                "subject": f"Monthly Cybersecurity Digest - {len(articles)} Incidents",
                "html": html_content
            }
            email = resend.Emails.send(params)
            print(f"Email sent to {RECIPIENT_EMAIL}, ID: {email.get('id')}")
            self.config_collection.update_one(
                {'type': 'digest_config'},
                {'$set': {'last_digest_sent': datetime.now(timezone.utc)}},
                upsert=True
            )
        except Exception as e:
            print(f"Error sending email: {e}")

    def generate_digest_html(self, articles, since_date):
        by_source = {}
        for article in articles:
            by_source.setdefault(article['source'], []).append(article)
        html = (
            "<!DOCTYPE html><html><head><style>"
            "body{font-family:Arial,sans-serif;color:#333;max-width:800px;margin:0 auto;padding:20px}"
            ".header{background:#dc2626;color:white;padding:30px;border-radius:10px;margin-bottom:30px}"
            ".article{border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:15px}"
            "</style></head><body>"
            "<div class='header'><h1>Monthly Cybersecurity Digest</h1>"
            f"<p>{since_date.strftime('%B %d, %Y')} - {datetime.now(timezone.utc).strftime('%B %d, %Y')}</p></div>"
            f"<p><strong>{len(articles)}</strong> incidents found</p>"
        )
        for source, arts in by_source.items():
            name = "The Hacker News" if source == "thehackernews" else "BleepingComputer"
            html += f"<h2>{name} ({len(arts)} incidents)</h2>"
            for a in arts:
                html += (
                    f'<div class="article"><h3><a href="{a["url"]}">{a["title"]}</a></h3>'
                    f'<p>{a["scraped_at"].strftime("%B %d, %Y")}</p></div>'
                )
        html += "<p>Stay secure!</p></body></html>"
        return html

    def run(self):
        print("\n" + "="*60 + "\nCYBERSECURITY NEWS MONITOR\n" + "="*60)
        print(f"Run time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        thn = self.scrape_thehackernews()
        bc = self.scrape_bleepingcomputer()
        all_articles = thn + bc
        print(f"Total articles found: {len(all_articles)}")
        stored = self.store_articles(all_articles)
        if self.should_send_digest():
            self.send_digest_email()
        total = self.articles_collection.count_documents({})
        attacks = self.articles_collection.count_documents({'is_cyberattack': True})
        print(f"\nSUMMARY: {total} total, {attacks} attack articles, {stored} new")
        self.mongo_client.close()


if __name__ == "__main__":
    if not MONGODB_URL:
        print("Error: MONGODB_URL not set")
        sys.exit(1)
    if not RECIPIENT_EMAIL:
        print("Error: RECIPIENT_EMAIL not set")
        sys.exit(1)
    monitor = CyberNewsMonitor()
    monitor.run()
