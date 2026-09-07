import random
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


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
            f"""
            window.scrollBy({{
                top:{pixels * direction},
                left:0,
                behavior:'smooth'
            }});
            """
        )

        time.sleep(random.uniform(0.8, 2.5))


def create_driver():

    options = Options()

    # options.add_argument("--headless=new")

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

    driver = webdriver.Chrome(options=options)

    driver.execute_script("""
    Object.defineProperty(navigator,'webdriver',{
        get:()=>undefined
    });
    """)

    return driver


def visit(url):

    driver = create_driver()

    try:

        print(f"\nOpening : {url}")

        driver.get(url)

        random_wait(3, 6)

        total_time = random.randint(MIN_STAY, MAX_STAY)

        start = time.time()

        while time.time() - start < total_time:

            human_scroll(driver, random.uniform(3, 7))

            random_wait(2, 5)

        print("Finished.")

    except Exception as e:

        print(e)

    finally:

        random_wait(2, 4)

        driver.quit()


def main():

    for url in LINKS:

        visit(url)

        print("Browser Closed.")

        time.sleep(random.randint(5, 10))


if __name__ == "__main__":
    main()