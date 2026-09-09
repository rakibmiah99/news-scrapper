import argparse
import json
import random
import re
import shutil
import tempfile
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


LINKS = [
    "https://www.takebackbangladesh.com/news/bderwfcmmbrr",
    "https://www.takebackbangladesh.com/news/2wn0omgzkkum",
    "https://www.takebackbangladesh.com/news/rlzanvfteaj1",
    "https://www.takebackbangladesh.com/"
]

# Domain used to discover in-page links worth clicking (found dynamically on
# the visited page, instead of clicking a fixed on-screen position).
TARGET_DOMAIN = "takebackbangladesh.com"

PROXIES_FILE = "proxies.jsonl"

MIN_STAY = 15
MAX_STAY = 35

MIN_CLICKS = 1
MAX_CLICKS = 2

# Chance (per page visited) of also throwing in one random-position click,
# not tied to any real link, just to look less mechanical.
RANDOM_CLICK_CHANCE = 0.3

# Fallback on-screen position used only if no real link could be found
# (viewport pixels).
CLICK_WIDTH = 900
CLICK_HEIGHT = 220

# Saves a grid-overlay screenshot before clicking so you can read off the
# right CLICK_WIDTH / CLICK_HEIGHT values.
SAVE_CLICK_PREVIEW = True
PREVIEW_GRID_STEP = 100

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


def save_position_preview(driver, path, grid_step=PREVIEW_GRID_STEP):

    driver.execute_script(
        """
        (function(step) {
            document.querySelectorAll('.__coord_grid_overlay').forEach(function(el){el.remove();});

            var overlay = document.createElement('div');
            overlay.className = '__coord_grid_overlay';
            overlay.style.position = 'fixed';
            overlay.style.top = '0';
            overlay.style.left = '0';
            overlay.style.width = '100%';
            overlay.style.height = '100%';
            overlay.style.zIndex = '2147483647';
            overlay.style.pointerEvents = 'none';

            var w = window.innerWidth;
            var h = window.innerHeight;

            for (var x = 0; x <= w; x += step) {
                var vLine = document.createElement('div');
                vLine.style.position = 'absolute';
                vLine.style.left = x + 'px';
                vLine.style.top = '0';
                vLine.style.width = '1px';
                vLine.style.height = h + 'px';
                vLine.style.background = 'rgba(255,0,0,0.6)';
                overlay.appendChild(vLine);

                var xLabel = document.createElement('div');
                xLabel.textContent = x;
                xLabel.style.position = 'absolute';
                xLabel.style.left = (x + 2) + 'px';
                xLabel.style.top = '0';
                xLabel.style.color = 'red';
                xLabel.style.fontSize = '10px';
                xLabel.style.background = 'white';
                overlay.appendChild(xLabel);
            }

            for (var y = 0; y <= h; y += step) {
                var hLine = document.createElement('div');
                hLine.style.position = 'absolute';
                hLine.style.top = y + 'px';
                hLine.style.left = '0';
                hLine.style.width = w + 'px';
                hLine.style.height = '1px';
                hLine.style.background = 'rgba(0,0,255,0.6)';
                overlay.appendChild(hLine);

                var yLabel = document.createElement('div');
                yLabel.textContent = y;
                yLabel.style.position = 'absolute';
                yLabel.style.top = y + 'px';
                yLabel.style.left = '0';
                yLabel.style.color = 'blue';
                yLabel.style.fontSize = '10px';
                yLabel.style.background = 'white';
                overlay.appendChild(yLabel);
            }

            document.body.appendChild(overlay);
        })(arguments[0]);
        """,
        grid_step,
    )

    driver.save_screenshot(path)

    driver.execute_script(
        "document.querySelectorAll('.__coord_grid_overlay').forEach(function(el){el.remove();});"
    )

    print(f"Position preview saved: {path} (grid every {grid_step}px)")


def find_visible_target_links(driver, target_domain=TARGET_DOMAIN):
    """Return real <a> links to target_domain that are visible in the current
    viewport (i.e. after the page has been scrolled to top), with their
    on-screen center coordinates. Used so clicks land on real links instead
    of a fixed guessed position."""

    script = """
    var targetDomain = arguments[0];
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var anchors = Array.prototype.slice.call(document.querySelectorAll('a[href]'));
    var results = [];

    anchors.forEach(function(a) {
        var href = a.href;
        if (!href || href.indexOf(targetDomain) === -1) return;
        if (href === window.location.href) return;

        var rect = a.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return;

        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;

        if (cx < 0 || cy < 0 || cx > vw || cy > vh) return;

        results.push({href: href, x: cx, y: cy});
    });

    return results;
    """

    try:
        links = driver.execute_script(script, target_domain)
    except Exception as e:
        print(f"Link discovery failed: {e}")
        links = []

    return links


def move_cursor_and_click(driver, x=CLICK_WIDTH, y=CLICK_HEIGHT, steps=20):

    try:

        window_size = driver.get_window_size()

        start_x = random.randint(0, window_size["width"])
        start_y = random.randint(0, window_size["height"])

        for step in range(1, steps + 1):

            cur_x = start_x + (x - start_x) * step / steps
            cur_y = start_y + (y - start_y) * step / steps

            driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {"type": "mouseMoved", "x": cur_x, "y": cur_y},
            )

            time.sleep(random.uniform(0.01, 0.04))

        random_wait(0.3, 0.8)

        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        )

        driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        )

        print(f"Clicked at position: ({x}, {y})")

        random_wait(3, 6)

        return True

    except Exception as e:

        print(f"Click failed: {e}")

        return False


def random_position_click(driver):
    """Click a random on-screen position (not necessarily a real link), so
    not every click is link-driven."""

    try:
        window_size = driver.get_window_size()
        x = random.randint(50, max(51, window_size["width"] - 50))
        y = random.randint(100, max(101, window_size["height"] - 100))
    except Exception as e:
        print(f"Could not read window size for random click: {e}")
        return False

    print(f"Random exploratory click at ({x}, {y})")

    return move_cursor_and_click(driver, x=x, y=y)


def browse_page(driver):

    total_time = random.randint(MIN_STAY, MAX_STAY)

    time.sleep(total_time)


def scroll_bottom_then_top(driver, steps=10):

    try:

        scroll_height = driver.execute_script("return document.body.scrollHeight")

        for step in range(1, steps + 1):
            driver.execute_script(f"window.scrollTo(0, {scroll_height * step / steps});")
            time.sleep(random.uniform(0.1, 0.3))

        random_wait(1, 2)

        for step in range(1, steps + 1):
            driver.execute_script(
                f"window.scrollTo(0, {scroll_height * (1 - step / steps)});"
            )
            time.sleep(random.uniform(0.1, 0.3))

        driver.execute_script("window.scrollTo(0, 0);")

        random_wait(1, 2)

    except Exception as e:

        print(f"Scroll failed: {e}")


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


def visit(url, proxy, headless, preview_path=None):

    driver, plugin_dir = create_driver(proxy, headless)

    try:

        print(f"\nOpening : {url}")
        print(f"Using proxy : {proxy['host']}:{proxy['port']}")

        driver.get(url)

        random_wait(3, 6)

        # Impression: read the page (scroll down then back up) before any click.
        scroll_bottom_then_top(driver)

        if SAVE_CLICK_PREVIEW:
            save_position_preview(driver, preview_path or "click_preview.png")

        if random.random() < RANDOM_CLICK_CHANCE:
            random_position_click(driver)
            random_wait(1, 2)

        browse_page(driver)

        target_clicks = random.randint(MIN_CLICKS, MAX_CLICKS)

        for click_num in range(1, target_clicks + 1):

            # Keep the page scrolled to top before searching for a link to
            # click, so impression time and click position stay balanced.
            driver.execute_script("window.scrollTo(0, 0);")
            random_wait(1, 2)

            links = find_visible_target_links(driver)

            if not links:
                print(f"No visible {TARGET_DOMAIN} link found to click, stopping.")
                break

            chosen = random.choice(links)

            print(f"Click {click_num}/{target_clicks} -> {chosen['href']}")

            clicked = move_cursor_and_click(driver, x=chosen["x"], y=chosen["y"])

            if not clicked:
                break

            random_wait(2, 4)

            # Landed on a new page: read it too before deciding on the next click.
            scroll_bottom_then_top(driver)

            if random.random() < RANDOM_CLICK_CHANCE:
                random_position_click(driver)
                random_wait(1, 2)

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
        description="Visit site and click a fixed on-screen position via proxies."
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

    for index, url in enumerate(LINKS, start=1):

        proxy = random.choice(proxies)

        visit(url, proxy, headless, preview_path=f"click_preview_{index}.png")

        print("Browser Closed.")

        time.sleep(random.randint(5, 10))


if __name__ == "__main__":
    main()
