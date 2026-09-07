#!/usr/bin/env python3
"""Scraper for ittefaq.com.bd news articles by incrementing news_id."""

import argparse
import json
import os
import random
import time
from datetime import datetime

import requests
import urllib3
from bs4 import BeautifulSoup

# Proxies fetched from proxy-guide.txt are often MITM/self-signed, which
# fails TLS verification. We disable verification only for the proxied
# scrape requests (never for our own API calls), so silence the resulting
# per-request InsecureRequestWarning noise.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

WEBSITE_NAME = "ittefaq"
BASE_URL = "https://www.ittefaq.com.bd/{news_id}/test-news-title"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

API_BASE_URL = "https://www.takebackbangladesh.com/api"
LAST_NEWS_ID_URL = f"{API_BASE_URL}/news-archives/last-news-id"
BULK_INSERT_URL = f"{API_BASE_URL}/news-archives-bulk-store"

# ---------------------------------------------------------------------------
# Route scrape requests through proxies loaded from a local proxies.jsonl
# file (one JSON object per line: {"proxy": "http://user:pass@host:port"}),
# so they don't all come from this machine's IP.
# ---------------------------------------------------------------------------
PROXIES_JSONL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "proxies.jsonl"
)

_proxy_pool = []
_dead_proxies = set()


def load_proxy_pool():
    if not os.path.exists(PROXIES_JSONL_PATH):
        return []
    proxies = []
    with open(PROXIES_JSONL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            try:
                proxy = json.loads(line).get("proxy")
            except json.JSONDecodeError:
                continue
            if proxy:
                proxies.append(proxy)
    return proxies


def refresh_proxy_pool():
    global _proxy_pool, _dead_proxies
    _proxy_pool = load_proxy_pool()
    _dead_proxies = set()
    print(f"Loaded {len(_proxy_pool)} proxies from {PROXIES_JSONL_PATH}")


refresh_proxy_pool()


def get_random_proxy():
    """Return (proxy_url, requests-proxies-dict) for a random live proxy, or (None, None)."""
    live = [p for p in _proxy_pool if p not in _dead_proxies]
    if not live:
        refresh_proxy_pool()
        live = [p for p in _proxy_pool if p not in _dead_proxies]
    if not live:
        return None, None
    proxy = random.choice(live)
    return proxy, {"http": proxy, "https": proxy}


def mark_proxy_dead(proxy):
    _dead_proxies.add(proxy)


def fetch_page(news_id, timeout=15, max_proxy_attempts=6):
    url = BASE_URL.format(news_id=news_id)
    last_exc = None
    for _ in range(max_proxy_attempts):
        proxy, proxies = get_random_proxy()
        try:
            response = requests.get(
                url, headers=HEADERS, proxies=proxies, timeout=timeout, verify=False
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            if proxy:
                print(f"[{news_id}] proxy {proxy} failed ({exc}); trying another proxy...")
                mark_proxy_dead(proxy)
            else:
                print(f"[{news_id}] direct request failed ({exc})")
    raise last_exc


def get_last_archive_news_id(website_name):
    response = requests.get(
        LAST_NEWS_ID_URL,
        params={"website_name": website_name},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return int(response.json()["last_archive_news_id"])


def insert_record(record):
    response = requests.post(BULK_INSERT_URL, json=[record], headers=HEADERS, timeout=30)
    return response


def extract_title(soup):
    tag = soup.find("h1", class_="title", attrs={"itemprop": "headline"})
    if tag:
        return tag.get_text(strip=True)
    return None


IMAGE_CDN_BASE = "https://cdn.ittefaqbd.com/contents/uploads/"


def extract_image_thumbnail(soup):
    container = soup.find(class_="featured_image")
    if not container:
        return None

    # Case 1: a real <img> tag is present inside featured_image.
    img = container.find("img")
    if img:
        src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-original")
            or img.get("data-lazy-src")
        )
        if src:
            if src.startswith("//"):
                src = "https:" + src
            return src

    # Case 2 (the common case on this site): no <img> tag exists in the raw
    # HTML at all. The image is only rendered client-side by JS from a
    # `data-ari` JSON attribute, e.g.:
    #   data-ari='{"path":"media/2026/09/02/xxx.jpg?jadewits_media_id=123",...}'
    ari_tag = container.find(attrs={"data-ari": True})
    if ari_tag:
        try:
            path = json.loads(ari_tag["data-ari"]).get("path")
        except (json.JSONDecodeError, TypeError, AttributeError):
            path = None
        if path:
            return IMAGE_CDN_BASE + path

    return None


def extract_description(soup):
    content_detail = soup.find(class_="content_detail_content_inner")
    if not content_detail:
        return None
    article_body = content_detail.find(class_="jw_article_body")
    if not article_body:
        return None
    paragraphs = article_body.find_all("p")
    if not paragraphs:
        return None
    text = " ".join(p.get_text(strip=True) for p in paragraphs)
    return text if text else None


def extract_published_at(soup):
    tag = soup.find(attrs={"itemprop": "datePublished"})
    if not tag or not tag.get("content"):
        return None
    raw = tag["content"]
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def scrape_news(news_id):
    html = fetch_page(news_id)
    soup = BeautifulSoup(html, "html.parser")

    title = extract_title(soup)
    description = extract_description(soup)

    if title is None and description is None:
        return None

    return {
        "website_name": WEBSITE_NAME,
        "news_id": str(news_id),
        "title": title,
        "description": description,
        "image_thumbnail": extract_image_thumbnail(soup),
        "published_at": extract_published_at(soup),
    }


def run(start_id, end_id, output_path, max_consecutive_failures, delay_range):
    if start_id is not None:
        news_id = start_id
    else:
        last_id = get_last_archive_news_id(WEBSITE_NAME)
        news_id = last_id + 1
        print(f"last_archive_news_id={last_id} -> starting at news_id={news_id}")

    consecutive_failures = 0

    while True:
        if end_id is not None and news_id > end_id:
            print(f"Reached end_id={end_id}. Stopping.")
            break

        try:
            record = scrape_news(news_id)
        except requests.RequestException as exc:
            print(f"[{news_id}] request failed: {exc}")
            record = None
        except Exception as exc:
            print(f"[{news_id}] unexpected error: {exc}")
            record = None

        if record is None:
            consecutive_failures += 1
            print(f"[{news_id}] invalid/empty page, skipping "
                  f"({consecutive_failures}/{max_consecutive_failures})")
            if end_id is None and consecutive_failures >= max_consecutive_failures:
                print(f"Hit {max_consecutive_failures} consecutive invalid pages. Stopping.")
                break
        else:
            consecutive_failures = 0
            response = insert_record(record)
            if 200 <= response.status_code < 300:
                print(f"[{news_id}] stored: {record['title']}")
            else:
                print(f"[{news_id}] insert FAILED: status={response.status_code}, "
                      f"body={response.text[:500]}")
                with open(output_path, "a", encoding="utf-8") as out_file:
                    out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"Saved failed record to {output_path} for retry. Stopping.")
                break

        news_id += 1
        time.sleep(random.uniform(*delay_range))


def parse_args():
    parser = argparse.ArgumentParser(description="Scrape news from ittefaq.com.bd")
    parser.add_argument("--start-id", type=int, default=None,
                         help="Starting news_id. If omitted, fetched from the "
                              "last-news-id API (last_archive_news_id + 1).")
    parser.add_argument("--end-id", type=int, default=None,
                         help="Ending news_id (inclusive). If omitted, runs until "
                              "consecutive invalid pages are hit.")
    parser.add_argument("--output", default="ittefaq_news.jsonl",
                         help="Path to .jsonl file where records are saved if a "
                              "server insert fails, for later retry")
    parser.add_argument("--max-consecutive-failures", type=int, default=15,
                         help="Stop after this many consecutive invalid pages "
                              "(only used when --end-id is not set)")
    parser.add_argument("--delay-min", type=float, default=1.0, help="Min delay (seconds)")
    parser.add_argument("--delay-max", type=float, default=2.0, help="Max delay (seconds)")
    return parser.parse_args()


def main():
    args = parse_args()
    run(
        start_id=args.start_id,
        end_id=args.end_id,
        output_path=args.output,
        max_consecutive_failures=args.max_consecutive_failures,
        delay_range=(args.delay_min, args.delay_max),
    )


if __name__ == "__main__":
    main()
