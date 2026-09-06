#!/usr/bin/env python3
"""Scraper for ittefaq.com.bd news articles by incrementing news_id."""

import argparse
import json
import os
import random
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

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


def fetch_page(news_id, timeout=10):
    url = BASE_URL.format(news_id=news_id)
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def get_last_archive_news_id(website_name):
    response = requests.get(
        LAST_NEWS_ID_URL,
        params={"website_name": website_name},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return int(response.json()["last_archive_news_id"])


def bulk_insert(records):
    response = requests.post(BULK_INSERT_URL, json=records, headers=HEADERS, timeout=30)
    return response


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def clear_file(path):
    open(path, "w", encoding="utf-8").close()


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


def run(start_id, end_id, output_path, batch_size, max_consecutive_failures, delay_range):
    if start_id is not None:
        news_id = start_id
    else:
        last_id = get_last_archive_news_id(WEBSITE_NAME)
        news_id = last_id + 1
        print(f"last_archive_news_id={last_id} -> starting at news_id={news_id}")

    consecutive_failures = 0
    batch_count = 0

    def flush_batch():
        nonlocal batch_count
        records = load_jsonl(output_path)
        if not records:
            return True
        response = bulk_insert(records)
        if 200 <= response.status_code < 300:
            clear_file(output_path)
            print(f"Bulk inserted {len(records)} record(s), cleared {output_path}")
            batch_count = 0
            return True
        print(f"Bulk insert FAILED: status={response.status_code}, body={response.text[:500]}")
        print(f"{len(records)} unsent record(s) remain in {output_path} for retry.")
        return False

    while True:
        if end_id is not None and news_id > end_id:
            print(f"Reached end_id={end_id}. Stopping.")
            flush_batch()
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
                print(f"Hit {max_consecutive_failures} consecutive invalid pages. "
                      f"Flushing {batch_count} pending record(s) and stopping.")
                flush_batch()
                break
        else:
            consecutive_failures = 0
            with open(output_path, "a", encoding="utf-8") as out_file:
                out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            batch_count += 1
            print(f"[{news_id}] saved ({batch_count}/{batch_size}): {record['title']}")

            if batch_count >= batch_size:
                if flush_batch():
                    last_id = get_last_archive_news_id(WEBSITE_NAME)
                    print(f"Resynced from API: last_archive_news_id={last_id}")
                    news_id = last_id
                else:
                    print("Stopping due to bulk insert failure.")
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
                         help="Path to output .jsonl file")
    parser.add_argument("--batch-size", type=int, default=50,
                         help="Number of scraped news to accumulate before bulk-inserting")
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
        batch_size=args.batch_size,
        max_consecutive_failures=args.max_consecutive_failures,
        delay_range=(args.delay_min, args.delay_max),
    )


if __name__ == "__main__":
    main()
