import argparse
import json
import os
import random
import shutil
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)

import fb_login as fgp


GROUPS_FILE = os.path.join(fgp.BASE_DIR, "fb_groups.jsonl")

# Same message is posted to every group in the loop - edit this directly.
POST_MESSAGE = """
জনগণের নিত্যদিনের সংকট যদি বিবেচনায় নেওয়া হয়, তাহলে চাঁদাবাজি, লুটপাটের অভিযোগ, দ্রব্যমূল্যের ঊর্ধ্বগতি, কর্মসংস্থানের সংকট ও বেকারত্ব—এসব নিয়ে মানুষের উদ্বেগ কমেনি।
এমন বাস্তবতায় শুধু “জনগণ আমাদের ওপর আস্থা রেখেছে” বললেই তো জনগণের আস্থা প্রমাণিত হয় না।
রাজনীতিবিদদের উচিত জনগণের আকাঙ্ক্ষা বুঝে কথা বলা, নিজেদের দলের কর্মী-সমর্থকদের প্রতিক্রিয়াকে পুরো জনগণের মতামত হিসেবে উপস্থাপন না করা।
জনগণের আকাঙ্ক্ষা বুঝতে হলে শুধু দলের কর্মীদের নয়, সাধারণ মানুষের বাস্তব অভিজ্ঞতাও শুনতে হবে।
https://www.facebook.com/share/p/1DnhkjaVXB/
"""

MIN_GROUP_DELAY = 20
MAX_GROUP_DELAY = 45

DIALOG_SELECTOR = 'div[role="dialog"]'

# Target the ancestor role="button" div, not the inner text span - clicking
# the bare span does not reliably trigger Facebook's open-composer handler.
WRITE_SOMETHING_SELECTORS = [
    '//div[@role="button"][.//span[contains(text(),"Write something")]]',
    '//div[@role="button"][.//span[contains(text(),"Write something to")]]',
    '//div[@role="button"][.//span[contains(text(),"What")]]',
]

POST_BOX_SELECTOR = f'{DIALOG_SELECTOR} div[data-lexical-editor="true"][role="textbox"]'

POST_BUTTON_SELECTORS = [
    f'{DIALOG_SELECTOR} div[aria-label="Post"][role="button"]',
    f'{DIALOG_SELECTOR} div[aria-label="Publish"][role="button"]',
]


def load_groups(path=GROUPS_FILE):

    groups = []

    with open(path, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if not line:
                continue

            entry = json.loads(line)

            if "url" not in entry:
                raise ValueError(f"Group entry missing url: {entry}")

            groups.append(entry)

    return groups


def find_write_something(driver):

    for selector in WRITE_SOMETHING_SELECTORS:

        try:
            return WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
        except TimeoutException:
            continue

    return None


def find_post_button(driver):

    for selector in POST_BUTTON_SELECTORS:

        try:
            return WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        except TimeoutException:
            continue

    return None


def dialog_is_open(driver, timeout=10):

    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, DIALOG_SELECTOR))
        )
        return True
    except TimeoutException:
        return False


def click_element(driver, element):

    try:
        element.click()
    except (ElementClickInterceptedException, StaleElementReferenceException):
        driver.execute_script("arguments[0].click();", element)


def ensure_contenteditable(driver, element):

    if element.get_attribute("contenteditable") != "true":
        driver.execute_script(
            "arguments[0].setAttribute('contenteditable', 'true');", element
        )


def focus_post_box(driver, post_box):

    try:
        target = post_box.find_element(By.CSS_SELECTOR, "p span")
    except NoSuchElementException:
        target = post_box

    ActionChains(driver).move_to_element(target).click().perform()


def post_to_group(driver, group_url, message):

    driver.get(group_url)

    fgp.random_wait(3, 6)

    fgp.dismiss_cookie_banner(driver)

    opened = False

    for attempt in range(2):

        trigger = find_write_something(driver)

        if trigger is None:
            print(f"[{group_url}] Could not find the 'Write something...' composer box.")
            fgp.save_debug_snapshot(driver, "group_composer_not_found")
            return False

        click_element(driver, trigger)

        opened = dialog_is_open(driver, timeout=10)

        if opened:
            break

        print(f"[{group_url}] Composer dialog did not open (attempt {attempt + 1}/2), retrying...")

    if not opened:
        print(f"[{group_url}] Post composer modal did not open.")
        fgp.save_debug_snapshot(driver, "group_modal_not_found")
        return False

    # Facebook briefly replaces the dialog's contents right after it opens
    # (loading shell -> real form), so re-locate on every attempt instead of
    # reusing a captured element - a stale reference here is expected, not
    # an error.
    typed = False

    for attempt in range(3):

        try:
            post_box = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, POST_BOX_SELECTOR))
            )
            ensure_contenteditable(driver, post_box)
            focus_post_box(driver, post_box)
            fgp.random_wait(0.5, 1.5)
            post_box.send_keys(message)
            typed = True
            break
        except StaleElementReferenceException:
            fgp.random_wait(0.5, 1)
            continue
        except TimeoutException:
            break

    if not typed:
        print(f"[{group_url}] Post text box not found inside the composer dialog.")
        fgp.save_debug_snapshot(driver, "group_post_box_not_found")
        return False

    fgp.random_wait(1, 2)

    post_button = find_post_button(driver)

    if post_button is None:
        print(f"[{group_url}] Post button not found.")
        fgp.save_debug_snapshot(driver, "group_post_button_not_found")
        return False

    click_element(driver, post_button)

    print(f"[{group_url}] Post submitted, waiting for it to go through...")

    fgp.random_wait(5, 8)

    return True


def run_group_posts(email_selector, headless, group_delay=True):

    accounts = fgp.load_accounts()

    account = fgp.pick_account(accounts, email_selector)

    email = account["email"]

    proxy = fgp.parse_proxy(account["proxy"]) if account.get("proxy") else None

    profile_dir = os.path.join(fgp.PROFILES_DIR, fgp.safe_profile_name(email))

    if not os.path.isdir(profile_dir):
        print(
            f"No saved session found for [{email}]. "
            "Run 'python fgp.py' first to log in and create the session."
        )
        return

    groups = load_groups()

    if not groups:
        print(f"No groups found in '{GROUPS_FILE}'.")
        return

    driver, plugin_dir = fgp.create_driver(profile_dir, proxy, headless)

    try:

        if not fgp.is_logged_in(driver):
            print(
                f"[{email}] Saved session is no longer logged in. "
                "Run 'python fgp.py' first to log in again."
            )
            return

        print(f"[{email}] Reusing saved session, posting to {len(groups)} group(s)...")

        for i, group in enumerate(groups):

            print(f"\n({i + 1}/{len(groups)}) Posting to {group['url']}")

            ok = post_to_group(driver, group["url"], POST_MESSAGE)

            print("Posted." if ok else "Skipped/failed.")

            if group_delay and i < len(groups) - 1:
                time.sleep(random.uniform(MIN_GROUP_DELAY, MAX_GROUP_DELAY))

    finally:

        fgp.random_wait(2, 4)

        driver.quit()

        if plugin_dir:
            shutil.rmtree(plugin_dir, ignore_errors=True)


def parse_args():

    parser = argparse.ArgumentParser(
        description="Post to Facebook groups using an already logged-in session (see fgp.py)."
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

    run_group_posts(args.account, headless)


if __name__ == "__main__":
    main()
