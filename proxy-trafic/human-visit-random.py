import random
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    StaleElementReferenceException,
    ElementClickInterceptedException,
    WebDriverException,
)

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

BASE_DOMAIN = "agamirsomoy.com"

MIN_STAY = 15
MAX_STAY = 35

MIN_SCROLL = 200
MAX_SCROLL = 700


def random_wait(a=1, b=3):
    time.sleep(random.uniform(a, b))


def human_scroll(driver, duration):
    end = time.time() + duration

    while time.time() < end:

        direction = random.choice([1, 1, 1, -1])

        pixels = random.randint(MIN_SCROLL, MAX_SCROLL)

        driver.execute_script(
            """
            window.scrollBy({
                top: arguments[0],
                left:0,
                behavior:'smooth'
            });
            """,
            pixels * direction,
        )

        time.sleep(random.uniform(0.8, 2.3))


def create_driver():
    options = Options()

    # options.add_argument("--headless=new")

    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")

    options.add_experimental_option(
        "excludeSwitches",
        ["enable-automation"],
    )

    options.add_experimental_option(
        "useAutomationExtension",
        False,
    )

    driver = webdriver.Chrome(options=options)

    driver.execute_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    return driver


def get_internal_links(driver):

    links = []

    for a in driver.find_elements(By.TAG_NAME, "a"):

        try:

            href = a.get_attribute("href")

            if not href:
                continue

            if not href.startswith("http"):
                continue

            domain = urlparse(href).netloc.lower()

            if BASE_DOMAIN not in domain:
                continue

            if href == driver.current_url:
                continue

            if any(x in href.lower() for x in [
                "/login",
                "/register",
                "/privacy",
                "/terms",
                "/contact",
                "/tag/",
                "/author/",
                "#",
            ]):
                continue

            if a.is_displayed() and a.is_enabled():
                links.append(a)

        except StaleElementReferenceException:
            continue

    return links


def click_internal_link(driver):

    links = get_internal_links(driver)

    if not links:
        print("No internal link found.")
        return False

    random.shuffle(links)

    for link in links:

        try:

            href = link.get_attribute("href")

            print("Click:", href)

            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                link,
            )

            random_wait(1, 2)

            driver.execute_script("""
                arguments[0].removeAttribute('target');
            """, link)

            driver.execute_script(
                "arguments[0].click();",
                link,
            )

            random_wait(3, 5)

            return True

        except (
            ElementClickInterceptedException,
            StaleElementReferenceException,
            WebDriverException,
        ):
            continue

    return False


def visit(url):

    driver = create_driver()

    try:

        print("=" * 60)
        print("Opening:", url)

        driver.get(url)

        random_wait(3, 6)

        human_scroll(driver, random.uniform(5, 8))

        if click_internal_link(driver):

            human_scroll(driver, random.uniform(6, 10))

        total = random.randint(MIN_STAY, MAX_STAY)

        start = time.time()

        while time.time() - start < total:

            human_scroll(driver, random.uniform(3, 6))

            random_wait(2, 4)

        print("Finished")

    except Exception as e:

        print("Error:", e)

    finally:

        random_wait(2, 4)

        driver.quit()

        print("Browser Closed")


def main():

    urls = LINKS[:]

    random.shuffle(urls)

    for url in urls:

        visit(url)

        time.sleep(random.randint(5, 10))


if __name__ == "__main__":
    main()