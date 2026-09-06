#!/usr/bin/env python3
"""Facebook news post automation: fetch unpublished news, generate/post the
Facebook template image for each, then immediately update that news item's
published status as soon as the post is created."""

import random
import time
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Config - fill these in before running
# ---------------------------------------------------------------------------
PAGE_ID = "1"
AUTHORIZATION_TOKEN = "Bearer 1|DNNj50TkfUYNjBJcSK7A76n6YSK2Zk2gasUdw5Wn5aaccfc4"

NEWS_ARCHIVES_URL = "https://www.takebackbangladesh.com/api/news-archives"
GENERATE_IMAGE_URL = "https://fb.programmingwithrakib.com/api/templates/1/generate-image"
UPDATE_PUBLISHED_URL = "https://www.takebackbangladesh.com/api/news-archives/published"
DELETE_NEWS_ARCHIVE_URL = "https://www.takebackbangladesh.com/api/news-archives/delete/{news_id}"

# ---------------------------------------------------------------------------
# Rate-limit avoidance: randomized delay between consecutive Facebook posts.
# Posting on a fixed interval looks automated to Facebook and triggers
# restrictions quickly. These tiers pick a random gap each time (mostly short,
# occasionally longer), plus an occasional extra-long "human style" break, so
# the posting cadence never repeats a predictable pattern. See fb_post_rule.txt.
# ---------------------------------------------------------------------------
DELAY_TIERS = [
    (60, 150, 0.55),   # 1-2.5 min: most posts
    (150, 300, 0.30),  # 2.5-5 min: occasional
    (300, 480, 0.15),  # 5-8 min: rarer cool-down
]
LONG_BREAK_RANGE = (600, 900)      # 10-15 min "human pause"
LONG_BREAK_EVERY_POSTS = (6, 10)   # trigger a long break after this many posts

BANGLA_DIGITS = "০১২৩৪৫৬৭৮৯"
BANGLA_MONTHS = [
    "জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন",
    "জুলাই", "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর",
]


def to_bangla_digits(value):
    return "".join(BANGLA_DIGITS[int(ch)] if ch.isdigit() else ch for ch in str(value))


def to_bangla_date(iso_date_string):
    dt = datetime.fromisoformat(iso_date_string.replace("Z", "+00:00"))
    day = to_bangla_digits(dt.day)
    month = BANGLA_MONTHS[dt.month - 1]
    year = to_bangla_digits(dt.year)
    return f"{day} {month}, {year}"


def extract_date_only(iso_date_string):
    if not iso_date_string:
        return None
    return iso_date_string.split("T")[0]


_posts_since_break = 0
_next_break_at = random.randint(*LONG_BREAK_EVERY_POSTS)


def wait_before_next_post():
    """Sleep a randomized amount of time between Facebook posts.

    Mostly short gaps (1-2.5 min), sometimes medium (2.5-5 min), rarely long
    (5-8 min), plus an occasional 10-15 min pause every few posts. Randomizing
    both the gap length and which tier is picked keeps the posting cadence
    from looking like an automated, fixed-interval script to Facebook.
    """
    global _posts_since_break, _next_break_at

    _posts_since_break += 1
    if _posts_since_break >= _next_break_at:
        delay = random.uniform(*LONG_BREAK_RANGE)
        _posts_since_break = 0
        _next_break_at = random.randint(*LONG_BREAK_EVERY_POSTS)
        print(f"Taking a longer pause: {delay / 60:.1f} min before the next post...")
    else:
        delay = pick_post_delay_seconds()
        print(f"Waiting {delay / 60:.1f} min before the next post...")

    time.sleep(delay)


def pick_post_delay_seconds():
    r = random.random()
    cumulative = 0.0
    for low, high, weight in DELAY_TIERS:
        cumulative += weight
        if r <= cumulative:
            return random.uniform(low, high)
    low, high, _ = DELAY_TIERS[-1]
    return random.uniform(low, high)


def fetch_news_archives():
    response = requests.get(NEWS_ARCHIVES_URL, timeout=30)
    response.raise_for_status()
    return response.json()


def generate_facebook_post(news):
    payload = {
        "thumbnail_image": news["image_thumbnail"],
        "headline": news["title"],
        "date": to_bangla_date(news["published_at"]),
        "page_id": PAGE_ID,
        "caption": news["title"],
        "comment_message": news['news_url'] or None,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": AUTHORIZATION_TOKEN,
    }
    response = requests.post(GENERATE_IMAGE_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()


def update_news_published(news_id, is_published):
    payload = {"id": news_id, "is_published": is_published}
    return requests.post(UPDATE_PUBLISHED_URL, json=payload, timeout=30)


def delete_news_archive(news_id, title, published_at, image_url):
    payload = {
        "title": title,
        "date": extract_date_only(published_at),
        "card_type": "portrait",
        "image_url": image_url,
    }
    return requests.post(
        DELETE_NEWS_ARCHIVE_URL.format(news_id=news_id), json=payload, timeout=30
    )


def process_news_batch(news_list):
    for news in news_list:
        title = news.get("title")
        image_thumbnail = news.get("image_thumbnail")
        published_at = news.get("published_at")

        if not title or not image_thumbnail or not published_at:
            try:
                response = delete_news_archive(news["id"], title, published_at, image_thumbnail)
                if response.status_code == 200:
                    print(f"[{news['id']}] deleted: missing title/image/date")
                else:
                    print(
                        f"[{news['id']}] delete failed: status={response.status_code}, "
                        f"body={response.text[:300]}"
                    )
            except requests.RequestException as exc:
                print(f"[{news['id']}] delete request failed: {exc}")
            continue

        try:
            result = generate_facebook_post(news)
            print(f"[{news['id']}] {result.get('message')}")

            if result.get("data", {}).get("page_posted") is True:
                try:
                    response = update_news_published(news["id"], True)
                    if response.status_code == 200:
                        print(f"[{news['id']}] marked as published")
                    else:
                        print(
                            f"[{news['id']}] failed to update published status: "
                            f"status={response.status_code}, body={response.text[:300]}"
                        )
                except requests.RequestException as exc:
                    print(f"[{news['id']}] update published request failed: {exc}")
        except requests.RequestException as exc:
            print(f"[{news['id']}] failed to post: {exc}")
        finally:
            wait_before_next_post()


def run():
    while True:
        news_list = fetch_news_archives()

        if not news_list:
            print("No more news to publish. Stopping.")
            break

        print(f"Fetched {len(news_list)} news item(s).")
        process_news_batch(news_list)


if __name__ == "__main__":
    run()
