import argparse
import json
import random
import re
import shutil
import tempfile
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

LINKS = [
    "https://www.ittefaq.com.bd/",
    "https://www.ittefaq.com.bd/808586/%E0%A6%AC%E0%A7%9C-%E0%A6%B6%E0%A6%B9%E0%A6%B0-%E0%A6%A8%E0%A7%9F-%E0%A6%AE%E0%A6%BE%E0%A6%A8%E0%A6%AC%E0%A6%BF%E0%A6%95-%E0%A6%93-%E0%A6%AA%E0%A6%B0%E0%A6%BF%E0%A6%AC%E0%A7%87%E0%A6%B6%E0%A6%AC%E0%A6%BE%E0%A6%A8%E0%A7%8D%E0%A6%A7%E0%A6%AC-%E0%A6%A8%E0%A6%97%E0%A6%B0%E0%A6%AC%E0%A7%8D%E0%A6%AF%E0%A6%AC%E0%A6%B8%E0%A7%8D%E0%A6%A5%E0%A6%BE-%E0%A6%97%E0%A7%9C%E0%A7%87",
]

PROXIES_FILE = "proxies.jsonl"

ALLOWED_DOMAIN = "ittefaq.com.bd"

MIN_STAY = 15
MAX_STAY = 35

MIN_SCROLL = 200
MAX_SCROLL = 700

MIN_CLICKS = 2
MAX_CLICKS = 4

PROXY_RE = re.compile(
    r"^(?P<username>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)


def load_proxies(path=PROXIES_FILE):

    proxies = []

    with open(path, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            entry = json.loads(line)

            match = PROXY_RE.match(entry["proxy"])

            if not match:
                raise ValueError(f"Bad proxy format: {entry['proxy']}")

            proxies.append(match.groupdict())

    return proxies


def random_wait(a=1, b=3):
    time.sleep(random.uniform(a, b))


def human_scroll(driver, duration):
    end = time.time() + duration

    while time.time() < end:

        direction = random.choice([1, 1, 1, -1])

        pixels = random.randint(MIN_SCROLL, MAX_SCROLL)

        driver.execute_script(
            f"""
            window.scrollBy({{
                top:{pixels * direction},
                left:0,
                behavior:'smooth'
            }});
            """
        )

        time.sleep(random.uniform(0.8, 2.5))


def is_allowed_domain(url):

    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False

    if not netloc:
        return False

    return (
        netloc == ALLOWED_DOMAIN
        or netloc == f"www.{ALLOWED_DOMAIN}"
        or netloc.endswith(f".{ALLOWED_DOMAIN}")
    )


def get_internal_links(driver):

    links = []

    for a in driver.find_elements(By.TAG_NAME, "a"):

        try:
            href = a.get_attribute("href")
        except StaleElementReferenceException:
            continue

        if not href:
            continue

        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue

        if is_allowed_domain(href):
            links.append((a, href))

    return links


def click_internal_link(driver):

    current_url = driver.current_url.rstrip("/")

    links = get_internal_links(driver)

    candidates = [
        (el, href) for el, href in links if href.rstrip("/") != current_url
    ]

    if not candidates:
        return False

    el, href = random.choice(candidates)

    try:

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center', behavior:'smooth'});",
            el,
        )

        random_wait(1, 2)

        try:
            el.click()
        except (ElementClickInterceptedException, StaleElementReferenceException):
            driver.execute_script("arguments[0].click();", el)

        print(f"Clicked link : {href}")

        random_wait(3, 6)

        return True

    except Exception as e:

        print(f"Click failed: {e}")

        return False


def browse_page(driver):

    total_time = random.randint(MIN_STAY, MAX_STAY)

    start = time.time()

    while time.time() - start < total_time:

        human_scroll(driver, random.uniform(3, 7))

        random_wait(2, 5)


def build_proxy_extension(proxy):

    plugin_dir = tempfile.mkdtemp(prefix="proxy_ext_")

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        }
    }
    """

    background_js = f"""
    var config = {{
        mode: "fixed_servers",
        rules: {{
            singleProxy: {{
                scheme: "http",
                host: "{proxy['host']}",
                port: parseInt({proxy['port']})
            }},
            bypassList: ["localhost"]
        }}
    }};

    chrome.proxy.settings.set({{value: config, scope: "regular"}}, function() {{}});

    function callbackFn(details) {{
        return {{
            authCredentials: {{
                username: "{proxy['username']}",
                password: "{proxy['password']}"
            }}
        }};
    }}

    chrome.webRequest.onAuthRequired.addListener(
        callbackFn,
        {{urls: ["<all_urls>"]}},
        ['blocking']
    );
    """

    with open(f"{plugin_dir}/manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest_json)

    with open(f"{plugin_dir}/background.js", "w", encoding="utf-8") as f:
        f.write(background_js)

    return plugin_dir


def create_driver(proxy, headless):

    options = Options()

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_experimental_option(
        "excludeSwitches",
        ["enable-automation"]
    )

    options.add_experimental_option(
        "useAutomationExtension",
        False
    )

    plugin_dir = build_proxy_extension(proxy)

    options.add_argument(f"--load-extension={plugin_dir}")

    driver = webdriver.Chrome(options=options)

    driver.execute_script("""
    Object.defineProperty(navigator,'webdriver',{
        get:()=>undefined
    });
    """)

    return driver, plugin_dir


def visit(url, proxy, headless):

    driver, plugin_dir = create_driver(proxy, headless)

    try:

        print(f"\nOpening : {url}")
        print(f"Using proxy : {proxy['host']}:{proxy['port']}")

        driver.get(url)

        random_wait(3, 6)

        browse_page(driver)

        clicks = random.randint(MIN_CLICKS, MAX_CLICKS)

        for _ in range(clicks):

            clicked = click_internal_link(driver)

            if not clicked:
                print("No internal link found to click.")
                break

            browse_page(driver)

        print("Finished.")

    except Exception as e:

        print(e)

    finally:

        random_wait(2, 4)

        driver.quit()

        shutil.rmtree(plugin_dir, ignore_errors=True)


def parse_args():

    parser = argparse.ArgumentParser(
        description="Visit site with human-like scrolling/clicking via proxies."
    )

    parser.add_argument(
        "show_browser",
        nargs="?",
        choices=["yes", "no"],
        default=None,
        help="yes = show the browser window, no = run in background (headless)",
    )

    return parser.parse_args()


def ask_show_browser():

    while True:

        answer = input("Browser open korte chan? (yes/no): ").strip().lower()

        if answer in ("yes", "no"):
            return answer

        print("Please type yes or no.")


def main():

    args = parse_args()

    show_browser = args.show_browser or ask_show_browser()

    headless = show_browser == "no"

    proxies = load_proxies()

    for url in LINKS:

        proxy = random.choice(proxies)

        visit(url, proxy, headless)

        print("Browser Closed.")

        time.sleep(random.randint(5, 10))


if __name__ == "__main__":
    main()
