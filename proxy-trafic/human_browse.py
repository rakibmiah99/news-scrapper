"""
Selenium human-like browsing bot.
10 ti link visit korbe, ekta pore ekta. Prottek page e:
 - kisukkhon random scroll (upore/nice)
 - majhe majhe page er kono random link e click kore dhuke abar scroll
 - pore back kore original page e ferot ashe
Requirements: pip install selenium   (Selenium 4.6+ hole chromedriver nijei download hoy)
"""

import random
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

# ---------- Ekhane tomar 10 ta link dao ----------
LINKS = [
    "https://www.agamirsomoy.com/",
    "https://www.agamirsomoy.com/national/anptdc5aubqa",
    "https://www.agamirsomoy.com/entertainment/xcy0bvnfgwul",
    "https://www.agamirsomoy.com/lifestyle/9mpicj1jacmq",
    "https://www.agamirsomoy.com/feature/science-technology/dv6z2jp2gedz",
    "https://www.agamirsomoy.com/video/psj7xmcepiam",
    "https://www.agamirsomoy.com/world/middle-east/vyur2fdi6h4r",
    "https://www.agamirsomoy.com/country/5mkptocsgzi1",
    "https://www.agamirsomoy.com/world/clz0fj03zn3q",
    "https://www.agamirsomoy.com/national/parliament/apmbt56xviki",
]

MIN_SCROLL_TIME = 8       # ek session scroll koto second cholbe
MAX_SCROLL_TIME = 20
MIN_CLICKS_PER_PAGE = 1   # prottek page e koyta random link click hobe
MAX_CLICKS_PER_PAGE = 3
MIN_WAIT = 2
MAX_WAIT = 6


def human_wait(a=MIN_WAIT, b=MAX_WAIT):
    time.sleep(random.uniform(a, b))


def human_scroll(driver, duration):
    """Human er moto ektu ektu kore scroll, majhe majhe pause."""
    end_time = time.time() + duration
    while time.time() < end_time:
        amount = random.randint(150, 700)
        direction = random.choice([1, 1, 1, -1])  # beshirvag somoy niche
        driver.execute_script(f"window.scrollBy(0, {amount * direction});")
        time.sleep(random.uniform(0.6, 2.2))


def get_clickable_links(driver):
    anchors = driver.find_elements(By.TAG_NAME, "a")
    valid = []
    for a in anchors:
        try:
            href = a.get_attribute("href")
            if href and href.startswith("http"):
                valid.append(a)
        except StaleElementReferenceException:
            continue
    return valid


def click_random_links(driver, max_clicks):
    done = 0
    attempts = 0
    while done < max_clicks and attempts < max_clicks * 3:
        attempts += 1
        links = get_clickable_links(driver)
        if not links:
            break
        link = random.choice(links)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
            human_wait(0.5, 1.5)
            link.click()
            done += 1
            human_wait()
            human_scroll(driver, random.uniform(MIN_SCROLL_TIME, MAX_SCROLL_TIME))
            driver.back()
            human_wait()
        except (ElementClickInterceptedException, StaleElementReferenceException, NoSuchElementException):
            continue
    return done


def visit_link(driver, url):
    print(f"[+] Visiting: {url}")
    driver.get(url)
    human_wait(2, 4)

    # prothome kisukkhon scroll (poRar moto)
    human_scroll(driver, random.uniform(MIN_SCROLL_TIME, MAX_SCROLL_TIME))

    # majhe majhe random link e click
    n_clicks = random.randint(MIN_CLICKS_PER_PAGE, MAX_CLICKS_PER_PAGE)
    click_random_links(driver, n_clicks)

    # abar shesh e ektu scroll
    human_scroll(driver, random.uniform(MIN_SCROLL_TIME, MAX_SCROLL_TIME))


def main():
    options = Options()
    # options.add_argument("--headless=new")  # dorkar hole headless off/on koro
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(options=options)

    try:
        links = LINKS[:]
        random.shuffle(links)  # order o randomize
        for url in links:
            visit_link(driver, url)
            human_wait(3, 7)  # next link e jawar age break
    finally:
        human_wait(2, 3)
        driver.quit()


if __name__ == "__main__":
    main()
