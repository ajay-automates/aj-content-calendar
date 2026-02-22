#!/usr/bin/env python3
"""
AJ's Daily AI News Fetcher
---------------------------
Runs via GitHub Actions every day at 7 AM ET.
Fetches top 5 AI/tech stories from RSS feeds and updates data/news.js
so the Vercel dashboard shows fresh news every morning.

No API keys needed — uses free public RSS feeds.
"""

import feedparser
import json
import re
import os
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ── RSS Sources ──────────────────────────────────────────────────────────────
FEEDS = [
    {"name": "TechCrunch AI",  "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "The Verge AI",   "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "Wired AI",       "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "Ars Technica",   "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
]

# ── Relevance Keywords ───────────────────────────────────────────────────────
HIGH_SCORE = ["openai", "anthropic", "claude", "gpt", "gemini", "llm", "chatgpt",
              "ai model", "artificial intelligence", "machine learning", "deep learning",
              "nvidia", "sam altman", "dario amodei", "google ai", "meta ai"]

MEDIUM_SCORE = ["startup", "funding", "billion", "million", "raise", "launch",
                "developer", "engineer", "software", "automation", "agent",
                "robotics", "chip", "compute", "data center"]

SKIP_KEYWORDS = ["sports", "recipe", "fashion", "celebrity", "movie review",
                 "weather", "horoscope", "politics", "election"]

# ── Scoring ──────────────────────────────────────────────────────────────────
def score_article(title, summary):
    text = (title + " " + summary).lower()
    if any(k in text for k in SKIP_KEYWORDS):
        return -1
    score = 0
    for k in HIGH_SCORE:
        if k in text: score += 3
    for k in MEDIUM_SCORE:
        if k in text: score += 1
    return score

def parse_date(entry):
    try:
        if hasattr(entry, 'published'):
            return parsedate_to_datetime(entry.published)
        if hasattr(entry, 'updated'):
            return parsedate_to_datetime(entry.updated)
    except:
        pass
    return datetime.now(timezone.utc) - timedelta(days=2)

def get_summary(entry):
    if hasattr(entry, 'summary'):
        text = re.sub(r'<[^>]+>', '', entry.summary)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:250] + ('...' if len(text) > 250 else '')
    return ""

# ── Key Angle Generator ──────────────────────────────────────────────────────
def generate_angle(title, summary, source):
    """
    Generate AJ-style hook angle for the article.
    These are templates — Claude upgrades them when writing actual captions.
    """
    title_lower = title.lower()
    angles = []

    if any(k in title_lower for k in ["replace", "job", "engineer", "developer", "worker"]):
        angles.append("Here's what most people are missing: this isn't about AI being smarter — it's about who adapts first.")
    if any(k in title_lower for k in ["billion", "million", "fund", "raise", "invest"]):
        angles.append("Follow the money. When this much capital moves in one direction, the market has already decided.")
    if any(k in title_lower for k in ["vs", "rival", "compete", "beat", "win", "lose"]):
        angles.append("This isn't just a product war. It's a values war. And that's what makes it interesting.")
    if any(k in title_lower for k in ["china", "chinese", "beijing"]):
        angles.append("While everyone watches OpenAI vs Anthropic, the real disruption might be coming from a completely different direction.")
    if any(k in title_lower for k in ["launch", "release", "announce", "new", "introduce"]):
        angles.append("What this actually means for the 99% of people who don't read the technical spec.")
    if any(k in title_lower for k in ["ban", "regulate", "law", "congress", "eu", "government"]):
        angles.append("Regulation without understanding is just noise. Here's what this actually does (and doesn't do).")

    if not angles:
        angles.append(f"Via {source} — the angle most people will miss when they share this story.")

    return angles[0]

def assign_pillar(title, summary):
    text = (title + " " + summary).lower()
    if any(k in text for k in ["startup", "funding", "founder", "vc", "entrepreneur", "business", "revenue"]):
        return "Entrepreneurship"
    if any(k in text for k in ["productivity", "workflow", "tool", "habit", "system", "efficiency"]):
        return "Productivity"
    if any(k in text for k in ["career", "job", "mindset", "learn", "growth", "skill"]):
        return "Personal Growth"
    return "AI & Tech"

# ── Main ─────────────────────────────────────────────────────────────────────
def fetch_top_stories(n=5, max_age_hours=48):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    candidates = []

    for feed_info in FEEDS:
        try:
            print(f"  Fetching {feed_info['name']}...")
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:20]:
                pub = parse_date(entry)
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                if pub < cutoff:
                    continue
                title   = entry.get("title", "").strip()
                summary = get_summary(entry)
                link    = entry.get("link", "")
                score   = score_article(title, summary)
                if score < 0 or not title:
                    continue
                candidates.append({
                    "title":     title,
                    "source":    feed_info["name"],
                    "url":       link,
                    "summary":   summary,
                    "score":     score,
                    "published": pub,
                    "pillar":    assign_pillar(title, summary),
                    "key_angle": generate_angle(title, summary, feed_info["name"])
                })
        except Exception as e:
            print(f"  ⚠️  Error fetching {feed_info['name']}: {e}")

    # Sort by score then recency
    candidates.sort(key=lambda x: (x["score"], x["published"]), reverse=True)

    # Deduplicate by similar titles
    seen, top = set(), []
    for c in candidates:
        key = c["title"][:40].lower()
        if key not in seen:
            seen.add(key)
            top.append(c)
        if len(top) >= n:
            break

    return top

def write_news_js(stories, output_path):
    today = datetime.now().strftime("%b %d, %Y")
    now   = datetime.now().strftime("%b %d, %Y at %I:%M %p ET")

    items_js = []
    for i, s in enumerate(stories, 1):
        date_str = s["published"].strftime("%b %d, %Y") if isinstance(s["published"], datetime) else today
        safe_title  = s["title"].replace("'", "\\'").replace("`", "\\`")
        safe_sum    = s["summary"].replace("'", "\\'").replace("`", "\\`")
        safe_angle  = s["key_angle"].replace("'", "\\'").replace("`", "\\`")
        uid = f"news-{datetime.now().strftime('%Y%m%d')}-{i:02d}"

        items_js.append(f"""  {{
    id: "{uid}",
    type: "news", status: "inbox", date: "{date_str}", rank: {i},
    title: "{safe_title}",
    source: "{s['source']}",
    url: "{s['url']}",
    summary: "{safe_sum}",
    key_angle: "{safe_angle}",
    pillar: "{s['pillar']}"
  }}""")

    js = f"""// AJ's Daily AI & Tech News
// Auto-updated every day at 7:00 AM ET by GitHub Actions
// Last updated: {now}

window.NEWS_ITEMS = [
{',\\n'.join(items_js)}
];
"""

    # Keep POSTED_ITEMS intact by reading existing file
    existing = ""
    if os.path.exists(output_path):
        with open(output_path) as f:
            existing = f.read()
    posted_match = re.search(r'window\.POSTED_ITEMS\s*=\s*\[.*?\];', existing, re.DOTALL)
    if posted_match:
        js += "\n" + posted_match.group(0) + "\n"

    with open(output_path, "w") as f:
        f.write(js)

    print(f"\n✅ Updated {output_path} with {len(stories)} stories")

def main():
    print("🔍 Fetching today's top AI & tech stories...\n")
    stories = fetch_top_stories(n=5)

    if not stories:
        print("⚠️  No stories found. Keeping existing data.")
        return

    print(f"\n📰 Top {len(stories)} stories selected:")
    for i, s in enumerate(stories, 1):
        print(f"  #{i} [{s['score']}pts] {s['title'][:70]} — {s['source']}")

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "..", "data", "news.js")
    write_news_js(stories, output_path)
    print("\n🚀 Dashboard data updated. Vercel will auto-deploy in ~30 seconds.")

if __name__ == "__main__":
    main()
