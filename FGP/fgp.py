import argparse
import json
import os
import random
import re
import shutil
import tempfile
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ACCOUNTS_FILE = os.path.join(BASE_DIR, "fb_accounts.jsonl")
PROFILES_DIR = os.path.join(BASE_DIR, "fb_profiles")
DEBUG_DIR = os.path.join(BASE_DIR, "fb_debug")

LOGIN_URL = "https://www.facebook.com/login"
HOME_URL = "https://www.facebook.com/"

LOGIN_BUTTON_SELECTORS = [
    'div[aria-label="Log in"][role="button"]',
    'button[name="login"]',
    'button[type="submit"]',
]

COOKIE_BUTTON_SELECTORS = [
    'button[data-cookiebanner="accept_button"]',
    'button[title="Allow all cookies"]',
    'button[title="Allow essential and optional cookies"]',
]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""

PROXY_RE = re.compile(
    r"^(?P<username>[^:]+):(?P<password>[^@]+)@(?P<host>[^:]+):(?P<port>\d+)$"
)


def load_accounts(path=ACCOUNTS_FILE):

    accounts = []

    with open(path, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            entry = json.loads(line)

            if "email" not in entry or "password" not in entry:
                raise ValueError(f"Account entry missing email/password: {entry}")

            accounts.append(entry)

    return accounts


def pick_account(accounts, selector):

    if selector is None:
        return accounts[0]

    for account in accounts:
        if account["email"] == selector:
            return account

    try:
        index = int(selector)
        return accounts[index]
    except (ValueError, IndexError):
        raise ValueError(f"No account found matching: {selector}")


def safe_profile_name(email):
    return re.sub(r"[^a-zA-Z0-9_.-]", "_", email)


def random_wait(a=1, b=3):
    time.sleep(random.uniform(a, b))


def parse_proxy(proxy_str):

    match = PROXY_RE.match(proxy_str)

    if not match:
        raise ValueError(f"Bad proxy format: {proxy_str}")

    return match.groupdict()


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


def create_driver(profile_dir, proxy, headless):

    options = Options()

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    # Absolute path is required - Chrome silently crashes on launch with a
    # relative --user-data-dir on some platforms (esp. Windows).
    options.add_argument(f"--user-data-dir={os.path.abspath(profile_dir)}")
    options.add_argument("--profile-directory=Default")

    # Portable across a fresh machine / headless Linux server: skip the
    # first-run/default-browser UI and disable the sandbox restrictions
    # that break inside containers without extra setup.
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=en-US")

    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_experimental_option(
        "excludeSwitches",
        ["enable-automation"]
    )

    options.add_experimental_option(
        "useAutomationExtension",
        False
    )

    plugin_dir = None

    if proxy:
        plugin_dir = build_proxy_extension(proxy)
        options.add_argument(f"--load-extension={plugin_dir}")

    driver = webdriver.Chrome(options=options)

    # CDP hook (unlike execute_script) re-applies on every navigation, not
    # just the current page - needed since we immediately driver.get() away.
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument", {"source": STEALTH_JS}
    )

    return driver, plugin_dir


def is_logged_in(driver):

    driver.get(HOME_URL)

    random_wait(2, 4)

    cookies = driver.get_cookies()

    return any(c["name"] == "c_user" for c in cookies)


def dismiss_cookie_banner(driver):

    for selector in COOKIE_BUTTON_SELECTORS:

        try:
            button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            button.click()
            random_wait(0.5, 1.5)
            return
        except TimeoutException:
            continue


def save_debug_snapshot(driver, label):

    os.makedirs(DEBUG_DIR, exist_ok=True)

    stamp = str(int(time.time()))

    try:
        driver.save_screenshot(os.path.join(DEBUG_DIR, f"{label}_{stamp}.png"))
        with open(
            os.path.join(DEBUG_DIR, f"{label}_{stamp}.html"), "w", encoding="utf-8"
        ) as f:
            f.write(driver.page_source)
    except Exception:
        pass


def find_login_button(driver):

    for selector in LOGIN_BUTTON_SELECTORS:

        try:
            return WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            continue

    return None


def wait_for_login_form(driver, attempts=2):

    for attempt in range(attempts):

        driver.get(LOGIN_URL)

        dismiss_cookie_banner(driver)

        try:
            return WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
        except TimeoutException:
            print(f"Login form not found (attempt {attempt + 1}/{attempts}), retrying...")

    save_debug_snapshot(driver, "login_form_not_found")
    return None


def facebook_login(driver, email, password):

    email_input = wait_for_login_form(driver)

    if email_input is None:
        print(
            "Could not load the Facebook login form. "
            f"Saved a screenshot/HTML snapshot to '{DEBUG_DIR}' for diagnosis."
        )
        return False

    password_input = driver.find_element(By.NAME, "pass")

    email_input.clear()
    email_input.send_keys(email)

    random_wait(0.5, 1.5)

    password_input.clear()
    password_input.send_keys(password)

    random_wait(0.5, 1.5)

    login_button = find_login_button(driver)

    if login_button is None:
        print("Login button not found.")
        return False

    try:
        login_button.click()
    except (ElementClickInterceptedException, StaleElementReferenceException):
        driver.execute_script("arguments[0].click();", login_button)

    print("Submitted login form, waiting for session...")

    for _ in range(20):

        random_wait(1, 1)

        cookies = driver.get_cookies()

        if any(c["name"] == "c_user" for c in cookies):
            return True

        if "checkpoint" in driver.current_url:
            print("Facebook is asking for a checkpoint/verification step.")
            return False

    return False


def run_login(email_selector, headless):

    accounts = load_accounts()

    account = pick_account(accounts, email_selector)

    email = account["email"]
    password = account["password"]

    proxy = parse_proxy(account["proxy"]) if account.get("proxy") else None

    profile_dir = os.path.abspath(os.path.join(PROFILES_DIR, safe_profile_name(email)))

    os.makedirs(profile_dir, exist_ok=True)

    driver, plugin_dir = create_driver(profile_dir, proxy, headless)

    try:

        if is_logged_in(driver):
            print(f"[{email}] Already logged in, reusing saved session.")
            return

        print(f"[{email}] No active session found, logging in...")

        if facebook_login(driver, email, password):
            print(f"[{email}] Login successful, session saved to '{profile_dir}'.")
        else:
            print(f"[{email}] Login failed. Check credentials or resolve checkpoint manually.")

    finally:

        random_wait(2, 4)

        driver.quit()

        if plugin_dir:
            shutil.rmtree(plugin_dir, ignore_errors=True)


def parse_args():

    parser = argparse.ArgumentParser(
        description="Facebook login automation with persistent session reuse."
    )

    parser.add_argument(
        "show_browser",
        nargs="?",
        choices=["yes", "no"],
        default=None,
        help="yes = show the browser window, no = run in background (headless)",
    )

    parser.add_argument(
        "--account",
        "-a",
        default=None,
        help="Email or index (0-based) of the account in fb_accounts.jsonl to use. Defaults to the first account.",
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

    run_login(args.account, headless)


if __name__ == "__main__":
    main()
