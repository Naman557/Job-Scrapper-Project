import re
import time
import random
import urllib.parse
from urllib.parse import urljoin
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

# ---------------------------------------------------------------------------
# Global Session & Driver Cache (Eliminates redundant network checks)
# ---------------------------------------------------------------------------
_CACHED_DRIVER_PATH = None
_DRIVER_PATH_LOCK = threading.Lock()

def get_chromedriver_path():
    """
    Caches the ChromeDriver installation path to prevent repeated network
    lookups on GitHub, saving 15-30s on every driver initialization.
    """
    global _CACHED_DRIVER_PATH
    with _DRIVER_PATH_LOCK:
        if not _CACHED_DRIVER_PATH:
            _CACHED_DRIVER_PATH = ChromeDriverManager().install()
        return _CACHED_DRIVER_PATH

def create_http_session():
    """
    Creates an optimized requests.Session with connection pooling,
    keep-alive, and retry backoff for rapid HTTP/API/RSS queries.
    """
    session = requests.Session()
    retries = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    })
    return session

GLOBAL_SESSION = create_http_session()


# ---------------------------------------------------------------------------
# High-Performance Selenium Driver Setup
# ---------------------------------------------------------------------------
def get_chrome_driver():
    """
    Initializes and returns a high-performance Selenium Chrome WebDriver:
    - Eager page load (does not block waiting for heavy ads, video, fonts)
    - Image loading disabled (saves 70%+ bandwidth and CPU)
    - Performance and anti-detection flags
    - Strict timeouts to avoid hanging indefinitely on slow websites
    """
    chrome_options = Options()
    if config.HEADLESS_MODE:
        chrome_options.add_argument("--headless=new")

    # Fast eager loading: return control as soon as DOM is interactive
    if getattr(config, "FAST_PAGE_LOAD", True):
        chrome_options.page_load_strategy = "eager"

    # Disable images and unnecessary media streams to maximize speed
    if getattr(config, "DISABLE_IMAGES", True):
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.images": 2,
            "profile.default_content_setting_values.media_stream": 2,
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_setting_values.geolocation": 2,
            "profile.default_content_settings.popups": 0,
        }
        chrome_options.add_experimental_option("prefs", prefs)

    # Performance and anti-detection flags
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-sync")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--disable-background-networking")
    chrome_options.add_argument("--disable-default-apps")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--dns-prefetch-disable")
    chrome_options.add_argument("--log-level=3")

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ]
    chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    driver_path = get_chromedriver_path()
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Set strict timeouts so slow pages don't block execution
    timeout_secs = getattr(config, "PAGE_LOAD_TIMEOUT", 15)
    driver.set_page_load_timeout(timeout_secs)
    driver.set_script_timeout(10)

    # Mask WebDriver flag
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
    except Exception:
        pass

    return driver


def fast_scroll_and_wait(driver, min_pause=0.3):
    """
    Rapidly triggers lazy-loading content with quick scroll increments
    without wasting seconds on blind sleeps.
    """
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
        time.sleep(min_pause)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(min_pause)
    except Exception:
        pass


def safe_driver_get(driver, url):
    """
    Safely navigates to a URL, catching TimeoutException if eager DOM is already loaded.
    """
    try:
        driver.get(url)
        return True
    except TimeoutException:
        # With eager loading, timeout often fires after DOMContentLoaded, which is fine
        return True
    except Exception as e:
        print(f"[!] Navigation error for {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# Job Classification and Filtering
# ---------------------------------------------------------------------------
def classify_job_type(job):
    """
    Classifies a job as 'freelance' or 'permanent' based on portal name and keywords.
    """
    portal = job.get("portal", "").lower()
    title = job.get("title", "").lower()

    # Portal checks
    freelance_portals = ["upwork", "freelancer", "fiverr", "guru", "peopleperhour"]
    for fp in freelance_portals:
        if fp in portal:
            return "freelance"

    # Keyword checks
    freelance_keywords = ["freelance", "contractor", "contract", "hourly", "gig", "part-time", "temporary", "consultant"]
    for kw in freelance_keywords:
        if kw in title:
            return "freelance"

    return "permanent"


# Known Indian cities and regions used to verify a job is India-based
INDIA_TERMS = [
    "india", "pune", "mumbai", "bengaluru", "bangalore",
    "hyderabad", "delhi", "gurgaon", "gurugram", "noida",
    "chennai", "kolkata", "ahmedabad", "jaipur", "surat",
    "lucknow", "nagpur", "indore", "bhopal", "patna",
    "chandigarh", "coimbatore", "kochi", "vizag", "vadodara"
]

NON_INDIA_COUNTRY_TERMS = [
    "united states", " usa", "u.s.a", "new york", "san francisco",
    "seattle", "chicago", "austin", "boston", "los angeles",
    "united kingdom", " uk ", "london", "manchester", "birmingham",
    "canada", "toronto", "vancouver", "ontario",
    "australia", "sydney", "melbourne", "brisbane",
    "germany", "berlin", "munich", "frankfurt",
    "singapore", "dubai", "abu dhabi", "netherlands", "amsterdam",
    "france", "paris", "japan", "tokyo", "china", "beijing",
    "brazil", "mexico", "russia", "moscow", "south korea"
]

REMOTE_TERMS = [
    "remote", "worldwide", "global", "anywhere", "work from home",
    "wfh", "distributed"
]

def is_india_eligible(job):
    """
    Returns True if an Indian job-seeker can reasonably apply for this job.
    """
    loc = str(job.get("location", "")).lower()
    portal = str(job.get("portal", "")).lower()

    always_remote_portals = ["upwork", "weworkremotely", "remoteok", "remotive"]
    if any(p in portal for p in always_remote_portals):
        return True

    if any(term in loc for term in INDIA_TERMS):
        return True

    if any(term in loc for term in REMOTE_TERMS):
        return True

    if any(term in loc for term in NON_INDIA_COUNTRY_TERMS):
        return False

    return True


def get_linkedin_time_param(days):
    """Maps days limit to LinkedIn f_TPR parameter."""
    if days <= 1:
        return "r86400"
    elif days <= 7:
        return "r604800"
    elif days <= 14:
        return "r1209600"
    else:
        return "r2592000"


def extract_posted_age_days(card):
    """Return a card's explicit posting age in days, or None when unavailable."""
    now = datetime.now(timezone.utc)

    for time_element in card.find_all("time"):
        date_value = time_element.get("datetime", "").strip()
        if date_value:
            try:
                posted_at = datetime.fromisoformat(date_value.replace("Z", "+00:00"))
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                return max(0, (now - posted_at.astimezone(timezone.utc)).total_seconds() / 86400)
            except ValueError:
                pass

        age_text = time_element.get_text(" ", strip=True).lower()
        age = parse_relative_posted_age(age_text)
        if age is not None:
            return age

    return parse_relative_posted_age(card.get_text(" ", strip=True).lower())


def parse_relative_posted_age(text):
    """Parse common relative posting labels such as '4 months ago'."""
    if re.search(r"\b(just posted|today|minutes? ago|hours? ago)\b", text):
        return 0
    if re.search(r"\byesterday\b", text):
        return 1

    match = re.search(
        r"\b(?:posted|reposted)?\s*(\d+)\+?\s*"
        r"(minute|hour|day|week|month|year)s?\s+ago\b",
        text,
    )
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    days_per_unit = {
        "minute": 1 / 1440,
        "hour": 1 / 24,
        "day": 1,
        "week": 7,
        "month": 30.4375,
        "year": 365.25,
    }
    return amount * days_per_unit[unit]


def is_within_max_age(posted_age_days, max_age_days=None):
    """Reject listings with an explicit age beyond the configured cutoff."""
    if posted_age_days is None:
        return True
    age_limit = config.MAX_AGE_DAYS if max_age_days is None else max_age_days
    return posted_age_days <= age_limit


# ---------------------------------------------------------------------------
# Sandbox Scraper (RealPython Fake Jobs)
# ---------------------------------------------------------------------------
def scrape_fake_jobs_sandbox(driver, search_item):
    """
    Scrapes the RealPython fake jobs sandbox page.
    """
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    location_query = search_item.get("location", "").lower()

    print(f"Scraping sandbox environment: {url}")
    if not safe_driver_get(driver, url):
        return []

    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, "ResultsContainer"))
        )
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")
    job_elements = soup.find_all("div", class_="card-content")

    results = []
    for job_elem in job_elements:
        title_elem = job_elem.find("h2", class_="title")
        company_elem = job_elem.find("h3", class_="company")
        location_elem = job_elem.find("p", class_="location")
        link_elems = job_elem.find_all("a")

        title = title_elem.text.strip() if title_elem else "N/A"
        company = company_elem.text.strip() if company_elem else "N/A"
        location = location_elem.text.strip() if location_elem else "N/A"

        if job_title_query and job_title_query not in title.lower():
            continue
        if location_query and location_query != "remote" and location_query not in location.lower():
            continue

        apply_link = "N/A"
        if len(link_elems) > 1:
            apply_link = link_elems[1]["href"]
        elif len(link_elems) == 1:
            apply_link = link_elems[0]["href"]

        job = {
            "portal": "RealPython Sandbox",
            "title": title,
            "company": company,
            "location": location,
            "experience": search_item.get("experience", "Not Specified"),
            "apply_link": apply_link,
            "recruiter_contact": "sandbox-recruiter@realpython.io"
        }
        job["job_type"] = classify_job_type(job)
        results.append(job)

        if config.MAX_JOBS_PER_PORTAL > 0 and len(results) >= config.MAX_JOBS_PER_PORTAL:
            break

    return results


# ---------------------------------------------------------------------------
# LinkedIn Scrapers (Fast Guest API + Selenium Fallback)
# ---------------------------------------------------------------------------
def scrape_linkedin_guest_api(search_item, session=None):
    """
    Ultra-fast LinkedIn Guest API endpoint.
    Fetches raw HTML job card snippets directly over HTTP in ~200ms
    without spinning up Selenium or rendering JavaScript.
    """
    portal_url = search_item.get("portal_url", "")
    job_title_query = search_item.get("job_title", "")
    location_query = search_item.get("location", "")
    max_jobs = config.MAX_JOBS_PER_PORTAL

    time_param = get_linkedin_time_param(config.MAX_AGE_DAYS)
    keywords = urllib.parse.quote(job_title_query)
    india_location = location_query if location_query else "India"
    if "india" not in india_location.lower():
        india_location = f"{india_location}, India"
    location_enc = urllib.parse.quote(india_location)

    base_api = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location={location_enc}&f_TPR={time_param}"

    sess = session or GLOBAL_SESSION
    results = []
    seen_links = set()
    page_offset = 0
    PAGE_SIZE = 10
    max_pages = 5 if max_jobs > 0 and max_jobs <= 50 else (15 if max_jobs == 0 else max(1, max_jobs // PAGE_SIZE + 1))

    print(f"Scraping LinkedIn Fast Guest API: {job_title_query} in {india_location}")

    for _ in range(max_pages):
        url = f"{base_api}&start={page_offset}"
        try:
            resp = sess.get(url, timeout=8)
            if resp.status_code != 200 or not resp.text.strip():
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("li")
            if not cards:
                cards = soup.find_all("div", class_=re.compile("job-search-card|base-card"))
            if not cards:
                break

            new_cards = 0
            for card in cards:
                posted_age_days = extract_posted_age_days(card)
                if not is_within_max_age(posted_age_days):
                    print(
                        f"[Date Filter] LinkedIn: rejected listing posted "
                        f"{posted_age_days:.0f} days ago (limit: {config.MAX_AGE_DAYS} days)."
                    )
                    continue

                title_elem = card.find(["h3", "h2"], class_=re.compile("job-search-card__title|base-search-card__title|title"))
                company_elem = card.find(["h4", "h3", "span"], class_=re.compile("job-search-card__subtitle|base-search-card__subtitle|subtitle"))
                loc_elem = card.find("span", class_=re.compile("job-search-card__location|location"))
                link_elem = card.find("a", href=True)

                title = title_elem.text.strip() if title_elem else "N/A"
                company = company_elem.text.strip() if company_elem else "N/A"
                location = loc_elem.text.strip() if loc_elem else "India"
                apply_link = link_elem["href"] if link_elem else "N/A"
                if apply_link != "N/A" and "?" in apply_link:
                    apply_link = apply_link.split("?")[0]

                if apply_link in seen_links or apply_link == "N/A":
                    continue
                seen_links.add(apply_link)
                new_cards += 1

                if job_title_query.lower() not in title.lower():
                    continue

                job = {
                    "portal": "LinkedIn",
                    "title": title,
                    "company": company,
                    "location": location,
                    "experience": search_item.get("experience", "3-5 years"),
                    "posted_age_days": posted_age_days,
                    "apply_link": apply_link,
                    "recruiter_contact": "Refer to Apply Link"
                }
                job["job_type"] = classify_job_type(job)
                results.append(job)

                if max_jobs > 0 and len(results) >= max_jobs:
                    break

            page_offset += PAGE_SIZE
            if new_cards == 0 or (max_jobs > 0 and len(results) >= max_jobs):
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"LinkedIn Fast API request note: {e}")
            break

    return results


def scrape_linkedin_public(driver, search_item):
    """
    Selenium fallback for LinkedIn job search with eager loading & rapid scrolling.
    """
    portal_url = search_item.get("portal_url", "")
    job_title_query = search_item.get("job_title", "")
    location_query = search_item.get("location", "")
    max_jobs = config.MAX_JOBS_PER_PORTAL

    time_param = get_linkedin_time_param(config.MAX_AGE_DAYS)

    if "linkedin.com/jobs" not in portal_url:
        keywords = urllib.parse.quote(job_title_query)
        india_location = location_query if location_query else "India"
        if "india" not in india_location.lower():
            india_location = f"{india_location}, India"
        location_enc = urllib.parse.quote(india_location)
        base_url = f"https://www.linkedin.com/jobs/search?keywords={keywords}&location={location_enc}&f_TPR={time_param}"
    else:
        base_url = portal_url
        if "f_TPR" not in base_url:
            connector = "&" if "?" in base_url else "?"
            base_url += f"{connector}f_TPR={time_param}"
        if "india" not in base_url.lower() and "location" not in base_url.lower():
            base_url += "&location=India"

    results = []
    seen_links = set()
    page_offset = 0
    PAGE_SIZE = 25
    max_pages = 4 if max_jobs > 0 and max_jobs <= 50 else (10 if max_jobs == 0 else max(1, max_jobs // PAGE_SIZE + 1))

    print(f"Scraping LinkedIn via Selenium: {base_url}")

    for _ in range(max_pages):
        url = f"{base_url}&start={page_offset}"
        if not safe_driver_get(driver, url):
            break

        fast_scroll_and_wait(driver, min_pause=0.3)

        # Click 'See more jobs' button if present
        try:
            see_more = driver.find_element(By.XPATH, "//button[contains(@aria-label,'See more jobs')]")
            driver.execute_script("arguments[0].click();", see_more)
            time.sleep(0.5)
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.find_all("div", class_=re.compile("job-search-card|base-card"))

        new_cards_found = 0
        for card in job_cards:
            try:
                posted_age_days = extract_posted_age_days(card)
                if not is_within_max_age(posted_age_days):
                    print(
                        f"[Date Filter] LinkedIn: rejected listing posted "
                        f"{posted_age_days:.0f} days ago (limit: {config.MAX_AGE_DAYS} days)."
                    )
                    continue

                title_elem = card.find("h3", class_=re.compile("job-search-card__title|base-search-card__title"))
                title = title_elem.text.strip() if title_elem else "N/A"

                company_elem = card.find("h4", class_=re.compile("job-search-card__subtitle|base-search-card__subtitle"))
                company = company_elem.text.strip() if company_elem else "N/A"

                loc_elem = card.find("span", class_=re.compile("job-search-card__metadata-item|job-search-card__location"))
                location = loc_elem.text.strip() if loc_elem else "N/A"

                link_elem = card.find("a", class_=re.compile("job-search-card__link|base-card__full-link"))
                apply_link = link_elem["href"] if link_elem else "N/A"
                if apply_link != "N/A" and "?" in apply_link:
                    apply_link = apply_link.split("?")[0]

                if apply_link in seen_links or apply_link == "N/A":
                    continue
                seen_links.add(apply_link)
                new_cards_found += 1

                if job_title_query.lower() not in title.lower():
                    continue

                job = {
                    "portal": "LinkedIn",
                    "title": title,
                    "company": company,
                    "location": location,
                    "experience": search_item.get("experience", "3-5 years"),
                    "posted_age_days": posted_age_days,
                    "apply_link": apply_link,
                    "recruiter_contact": "Refer to Apply Link"
                }
                job["job_type"] = classify_job_type(job)
                results.append(job)

                if max_jobs > 0 and len(results) >= max_jobs:
                    break
            except Exception:
                continue

        if new_cards_found == 0 or (max_jobs > 0 and len(results) >= max_jobs):
            break

        page_offset += PAGE_SIZE
        if page_offset > 300:
            break

    print(f"  LinkedIn Selenium collected {len(results)} jobs.")
    return results


# ---------------------------------------------------------------------------
# Indeed Scraper
# ---------------------------------------------------------------------------
def scrape_indeed_public(driver, search_item):
    """
    Scrapes Indeed India jobs with fast eager page loads and smart early exits.
    """
    portal_url = search_item.get("portal_url", "")
    job_title = search_item.get("job_title", "")
    location = search_item.get("location", "")
    max_jobs = config.MAX_JOBS_PER_PORTAL

    if "indeed.com" not in portal_url:
        q = urllib.parse.quote(job_title)
        india_location = location if location else "India"
        if "india" not in india_location.lower():
            india_location = f"{india_location}, India"
        l = urllib.parse.quote(india_location)
        base_url = f"https://in.indeed.com/jobs?q={q}&l={l}&fromage={config.MAX_AGE_DAYS}"
    else:
        base_url = portal_url.replace("www.indeed.com", "in.indeed.com")
        if "fromage" not in base_url:
            connector = "&" if "?" in base_url else "?"
            base_url += f"{connector}fromage={config.MAX_AGE_DAYS}"

    results = []
    seen_links = set()
    PAGE_SIZE = 10
    max_pages = 3 if max_jobs > 0 and max_jobs <= 30 else (8 if max_jobs == 0 else max(1, max_jobs // PAGE_SIZE + 1))

    print(f"Scraping Indeed India Jobs: {base_url}")

    for page_num in range(max_pages):
        start_offset = page_num * PAGE_SIZE
        url = f"{base_url}&start={start_offset}"

        if not safe_driver_get(driver, url):
            break

        # Fast bot protection check
        page_source_lower = driver.page_source.lower()
        if "hcaptcha" in page_source_lower or "cloudflare" in page_source_lower or "just a moment" in driver.title.lower():
            print(f"Warning: Indeed page {page_num + 1} encountered bot challenge. Skipping further pages.")
            break

        fast_scroll_and_wait(driver, min_pause=0.3)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.find_all("div", class_=re.compile("job_seen_beacon|slider_container"))

        if not job_cards:
            break

        new_cards_found = 0
        for card in job_cards:
            try:
                posted_age_days = extract_posted_age_days(card)
                if not is_within_max_age(posted_age_days):
                    continue

                title_elem = card.find("h2", class_=re.compile("jobTitle"))
                title = title_elem.text.strip() if title_elem else "N/A"

                company_elem = card.find("span", data_testid="company-name")
                company = company_elem.text.strip() if company_elem else "N/A"

                loc_elem = card.find("div", data_testid="text-location")
                location_val = loc_elem.text.strip() if loc_elem else "N/A"

                link_elem = card.find("a", class_=re.compile("jcs-JobTitle"))
                apply_link = "N/A"
                if link_elem and "href" in link_elem.attrs:
                    apply_link = "https://in.indeed.com" + link_elem["href"]

                if apply_link in seen_links or apply_link == "N/A":
                    continue
                seen_links.add(apply_link)
                new_cards_found += 1

                job = {
                    "portal": "Indeed",
                    "title": title,
                    "company": company,
                    "location": location_val,
                    "experience": search_item.get("experience", "Not Specified"),
                    "posted_age_days": posted_age_days,
                    "apply_link": apply_link,
                    "recruiter_contact": "Refer to Apply Link"
                }
                job["job_type"] = classify_job_type(job)
                results.append(job)

                if max_jobs > 0 and len(results) >= max_jobs:
                    break
            except Exception:
                continue

        if new_cards_found == 0 or (max_jobs > 0 and len(results) >= max_jobs):
            break

    print(f"Indeed scraping complete. Collected {len(results)} jobs.")
    return results


# ---------------------------------------------------------------------------
# Fast RSS & REST API Scrapers
# ---------------------------------------------------------------------------
def scrape_remoteok(search_item, session=None):
    """Scrapes RemoteOK public JSON API with session connection reuse."""
    query = search_item.get("job_title", "").lower()
    sess = session or GLOBAL_SESSION
    url = "https://remoteok.com/api"

    results = []
    try:
        response = sess.get(url, timeout=10)
        if response.status_code != 200:
            return []

        jobs_data = response.json()
        if len(jobs_data) <= 1:
            return []

        now = datetime.now(timezone.utc)
        for job_entry in jobs_data[1:]:
            title = job_entry.get("position", "")
            company = job_entry.get("company", "")
            apply_link = job_entry.get("url", "")
            tags = job_entry.get("tags", [])
            date_str = job_entry.get("date", "")

            if query and query not in title.lower() and not any(query in str(tag).lower() for tag in tags):
                continue

            if date_str:
                try:
                    pub_dt = datetime.fromisoformat(date_str).astimezone(timezone.utc)
                    if (now - pub_dt).total_seconds() > config.MAX_AGE_DAYS * 86400:
                        continue
                except Exception:
                    pass

            job = {
                "portal": "RemoteOK",
                "title": title,
                "company": company,
                "location": "Remote",
                "experience": search_item.get("experience", "Not Specified"),
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if config.MAX_JOBS_PER_PORTAL > 0 and len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
    except Exception as e:
        print(f"Error scraping RemoteOK: {e}")

    return results


def parse_xml_feed(content):
    """Parses XML RSS feed, trying lxml/xml parser first, falling back to html.parser."""
    try:
        return BeautifulSoup(content, features="xml")
    except Exception:
        return BeautifulSoup(content, "html.parser")

def scrape_weworkremotely(search_item, session=None):
    """Scrapes WeWorkRemotely RSS feed with connection reuse."""
    query = search_item.get("job_title", "").lower()
    sess = session or GLOBAL_SESSION
    url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"

    results = []
    try:
        response = sess.get(url, timeout=10)
        if response.status_code != 200:
            return []

        soup = parse_xml_feed(response.content)
        items = soup.find_all("item")
        now = datetime.now(timezone.utc)

        for item in items:
            title_text = item.find("title").text if item.find("title") else "N/A"
            link = item.find("link").text if item.find("link") else "N/A"
            pub_date_text = item.find("pubDate").text if item.find("pubDate") else ""

            company = "N/A"
            title = title_text
            if ":" in title_text:
                parts = title_text.split(":", 1)
                company = parts[0].strip()
                title = parts[1].strip()

            if query and query not in title.lower():
                continue

            if pub_date_text:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_text)
                    if (now - pub_dt).total_seconds() > config.MAX_AGE_DAYS * 86400:
                        continue
                except Exception:
                    pass

            job = {
                "portal": "WeWorkRemotely",
                "title": title,
                "company": company,
                "location": "Remote",
                "experience": search_item.get("experience", "Not Specified"),
                "apply_link": link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if config.MAX_JOBS_PER_PORTAL > 0 and len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
    except Exception as e:
        print(f"Error scraping WeWorkRemotely RSS: {e}")

    return results


def scrape_upwork_rss(search_item, session=None):
    """Scrapes Upwork RSS feed for the query with connection pooling."""
    query = search_item.get("job_title", "")
    sess = session or GLOBAL_SESSION
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.upwork.com/ab/feed/jobs/rss?q={encoded_query}"

    results = []
    try:
        response = sess.get(url, timeout=10)
        if response.status_code != 200:
            return []

        soup = parse_xml_feed(response.content)
        items = soup.find_all("item")
        now = datetime.now(timezone.utc)

        for item in items:
            title = item.find("title").text if item.find("title") else "N/A"
            link = item.find("link").text if item.find("link") else "N/A"
            pub_date_text = item.find("pubDate").text if item.find("pubDate") else ""
            desc_text = item.find("description").text if item.find("description") else ""

            if pub_date_text:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_text)
                    if (now - pub_dt).total_seconds() > config.MAX_AGE_DAYS * 86400:
                        continue
                except Exception:
                    pass

            title = title.replace(" - Upwork", "").strip()

            recruiter_contact = "Refer to Apply Link"
            budget_match = re.search(r"<b>Budget</b>:\s*\$([\d,]+)", desc_text)
            hourly_match = re.search(r"<b>Hourly Range</b>:\s*([^\n<]+)", desc_text)
            if budget_match:
                recruiter_contact = f"Budget: ${budget_match.group(1)}"
            elif hourly_match:
                recruiter_contact = f"Hourly: {hourly_match.group(1).strip()}"

            job = {
                "portal": "Upwork",
                "title": title,
                "company": "Upwork Client",
                "location": "Remote",
                "experience": search_item.get("experience", "Not Specified"),
                "apply_link": link,
                "recruiter_contact": recruiter_contact,
                "job_type": "freelance"
            }
            results.append(job)

            if config.MAX_JOBS_PER_PORTAL > 0 and len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
    except Exception as e:
        print(f"Error scraping Upwork RSS: {e}")

    return results


def scrape_remotive(search_item, session=None):
    """Scrapes Remotive.com RSS feed for remote developer jobs."""
    query = search_item.get("job_title", "").lower()
    sess = session or GLOBAL_SESSION
    url = "https://remotive.com/remote-jobs/feed/software-dev"
    results = []

    try:
        response = sess.get(url, timeout=10)
        if response.status_code != 200:
            return []

        soup = parse_xml_feed(response.content)
        items = soup.find_all("item")
        now = datetime.now(timezone.utc)

        for item in items:
            title = item.find("title").text.strip() if item.find("title") else "N/A"
            link = item.find("link").text.strip() if item.find("link") else "N/A"
            pub_date_text = item.find("pubDate").text if item.find("pubDate") else ""

            if query and query not in title.lower():
                continue

            if pub_date_text:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_text)
                    if (now - pub_dt).total_seconds() > config.MAX_AGE_DAYS * 86400:
                        continue
                except Exception:
                    pass

            job = {
                "portal": "Remotive",
                "title": title,
                "company": "Remotive Partner",
                "location": "Remote",
                "experience": search_item.get("experience", "Not Specified"),
                "apply_link": link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if config.MAX_JOBS_PER_PORTAL > 0 and len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
    except Exception as e:
        print(f"Error scraping Remotive RSS: {e}")

    return results


# ---------------------------------------------------------------------------
# Selenium Portal Scrapers (Optimized Eager Rendering + Smart Waits)
# ---------------------------------------------------------------------------
def scrape_naukri(driver, search_item):
    """Scrapes Naukri.com with rapid DOM detection."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Naukri: {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("article", class_=re.compile("jobTuple|job-container|cust-job-tuple"))
    if not cards:
        cards = soup.find_all("div", class_=re.compile("jobTuple|srp-jobtuple-wrapper"))

    results = []
    seen = set()

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find("a", class_=re.compile("title|jobTitle")) or card.find("h2")
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("a", class_=re.compile("subTitle|comp-name")) or card.find("span", class_=re.compile("company"))
            company = company_elem.text.strip() if company_elem else "N/A"

            loc_elem = card.find("li", class_=re.compile("location")) or card.find("span", class_=re.compile("location|loc"))
            location = loc_elem.text.strip() if loc_elem else search_item.get("location", "India")

            link_elem = title_elem if title_elem and title_elem.name == "a" else card.find("a", href=True)
            apply_link = link_elem["href"] if link_elem and "href" in link_elem.attrs else "N/A"
            if apply_link != "N/A" and not apply_link.startswith("http"):
                apply_link = "https://www.naukri.com" + apply_link

            if apply_link in seen:
                continue
            seen.add(apply_link)

            if job_title_query and job_title_query not in title.lower():
                continue

            job = {
                "portal": "Naukri",
                "title": title,
                "company": company,
                "location": location,
                "experience": search_item.get("experience", "3-5 years"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  Naukri: Collected {len(results)} jobs.")
    return results


def scrape_foundit(driver, search_item):
    """Scrapes Foundit job listings with fast eager load."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Foundit: {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_=re.compile("card-body|job-card|srpResultCardContainer"))

    results = []
    seen = set()

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find("h3") or card.find("a", class_=re.compile("job-title"))
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("a", class_=re.compile("company")) or card.find("span", class_=re.compile("company"))
            company = company_elem.text.strip() if company_elem else "N/A"

            loc_elem = card.find("span", class_=re.compile("location")) or card.find("li", class_=re.compile("loc"))
            location = loc_elem.text.strip() if loc_elem else search_item.get("location", "India")

            link_elem = card.find("a", href=True)
            apply_link = link_elem["href"] if link_elem else "N/A"
            if apply_link != "N/A" and not apply_link.startswith("http"):
                apply_link = "https://www.foundit.in" + apply_link

            if apply_link in seen:
                continue
            seen.add(apply_link)

            if job_title_query and job_title_query not in title.lower():
                continue

            job = {
                "portal": "Foundit",
                "title": title,
                "company": company,
                "location": location,
                "experience": search_item.get("experience", "3-5 years"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  Foundit: Collected {len(results)} jobs.")
    return results


def scrape_shine(driver, search_item):
    """Scrapes Shine.com listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Shine.com: {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_=re.compile("job-listing|jobCardWrapper|job_listing"))

    results = []
    seen = set()

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find("h3") or card.find("a", class_=re.compile("jobTitle|job-title"))
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("span", class_=re.compile("company")) or card.find("a", class_=re.compile("comp"))
            company = company_elem.text.strip() if company_elem else "N/A"

            loc_elem = card.find("span", class_=re.compile("location|city"))
            location = loc_elem.text.strip() if loc_elem else search_item.get("location", "India")

            link_elem = card.find("a", href=True)
            apply_link = link_elem["href"] if link_elem else "N/A"
            if apply_link != "N/A" and not apply_link.startswith("http"):
                apply_link = "https://www.shine.com" + apply_link

            if apply_link in seen:
                continue
            seen.add(apply_link)

            if job_title_query and job_title_query not in title.lower():
                continue

            job = {
                "portal": "Shine",
                "title": title,
                "company": company,
                "location": location,
                "experience": search_item.get("experience", "3-5 years"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  Shine: Collected {len(results)} jobs.")
    return results


def scrape_timesjobs(driver, search_item):
    """Scrapes TimesJobs listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping TimesJobs: {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("li", class_=re.compile("clearfix|job-bx"))

    results = []
    seen = set()

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find("h2") or card.find("a", class_=re.compile("jobTitle"))
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("h3", class_=re.compile("joblist-comp-name")) or card.find("span", class_=re.compile("company"))
            company = company_elem.text.strip() if company_elem else "N/A"

            location_ul = card.find("ul", class_=re.compile("top-jd-dtl"))
            location = "India"
            if location_ul:
                lis = location_ul.find_all("li")
                if len(lis) >= 2:
                    location = lis[1].text.strip()

            link_elem = card.find("a", href=True)
            apply_link = link_elem["href"] if link_elem else "N/A"

            if apply_link in seen:
                continue
            seen.add(apply_link)

            if job_title_query and job_title_query not in title.lower():
                continue

            job = {
                "portal": "TimesJobs",
                "title": title,
                "company": company,
                "location": location,
                "experience": search_item.get("experience", "3-5 years"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  TimesJobs: Collected {len(results)} jobs.")
    return results


def scrape_glassdoor(driver, search_item):
    """Scrapes Glassdoor listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Glassdoor: {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("li", class_=re.compile("JobsList_jobListItem|react-job-listing"))
    if not cards:
        cards = soup.find_all("div", attrs={"data-test": "jobListing"})

    results = []
    seen = set()

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find("a", class_=re.compile("jobTitle|JobCard_jobTitle"))
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("span", class_=re.compile("EmployerProfile_compactEmployerName|employerName"))
            company = company_elem.text.strip() if company_elem else "N/A"

            loc_elem = card.find("div", class_=re.compile("JobCard_location|location"))
            location = loc_elem.text.strip() if loc_elem else search_item.get("location", "India")

            apply_link = "N/A"
            if title_elem and title_elem.get("href"):
                href = title_elem["href"]
                apply_link = f"https://www.glassdoor.co.in{href}" if not href.startswith("http") else href

            if apply_link in seen:
                continue
            seen.add(apply_link)

            if job_title_query and job_title_query not in title.lower():
                continue

            job = {
                "portal": "Glassdoor",
                "title": title,
                "company": company,
                "location": location,
                "experience": search_item.get("experience", "3-5 years"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  Glassdoor: Collected {len(results)} jobs.")
    return results


def scrape_wellfound(driver, search_item):
    """Scrapes Wellfound (AngelList) startup job listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Wellfound: {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.4)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_=re.compile("styles_component|JobListings_jobListings|job-listing"))

    results = []
    seen = set()

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find("a", class_=re.compile("JobListing_title|title"))
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("a", class_=re.compile("company|startup"))
            company = company_elem.text.strip() if company_elem else "N/A"

            loc_elem = card.find("span", class_=re.compile("location"))
            location = loc_elem.text.strip() if loc_elem else "Remote"

            apply_link = "N/A"
            if title_elem and title_elem.get("href"):
                href = title_elem["href"]
                apply_link = f"https://wellfound.com{href}" if not href.startswith("http") else href

            if apply_link in seen:
                continue
            seen.add(apply_link)

            if job_title_query and job_title_query not in title.lower():
                continue

            job = {
                "portal": "Wellfound",
                "title": title,
                "company": company,
                "location": location,
                "experience": search_item.get("experience", "Not Specified"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  Wellfound: Collected {len(results)} jobs.")
    return results


def scrape_generic_selenium(driver, search_item):
    """
    Generic fallback Selenium scraper for company career pages and ATS platforms.
    """
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping (generic): {url}")
    if not safe_driver_get(driver, url):
        return []

    fast_scroll_and_wait(driver, min_pause=0.3)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = (
        soup.find_all("div", class_=re.compile("job|career|opening|position|listing", re.I))
        or soup.find_all("li", class_=re.compile("job|career|opening|position", re.I))
        or soup.find_all("tr", class_=re.compile("job|career|opening", re.I))
    )

    results = []
    seen = set()

    # Anchor fallback if card blocks not found
    if not cards:
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            text = a.get_text(strip=True)
            if job_title_query and job_title_query not in text.lower():
                continue
            href = a["href"]
            if not href.startswith("http"):
                href = urljoin(url, href)
            if href in seen:
                continue
            seen.add(href)
            job = {
                "portal": urllib.parse.urlparse(url).netloc,
                "title": text or job_title_query,
                "company": urllib.parse.urlparse(url).netloc,
                "location": search_item.get("location", "India"),
                "experience": search_item.get("experience", "Not Specified"),
                "apply_link": href,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)
            if max_jobs > 0 and len(results) >= max_jobs:
                break
        return results

    for card in cards:
        try:
            posted_age_days = extract_posted_age_days(card)
            if not is_within_max_age(posted_age_days):
                continue

            title_elem = card.find(["h2", "h3", "h4", "a"])
            title = title_elem.text.strip() if title_elem else "N/A"

            if job_title_query and job_title_query not in title.lower():
                continue

            link_elem = card.find("a", href=True)
            apply_link = "N/A"
            if link_elem:
                href = link_elem["href"]
                if not href.startswith("http"):
                    href = urljoin(url, href)
                apply_link = href

            if apply_link in seen:
                continue
            seen.add(apply_link)

            job = {
                "portal": urllib.parse.urlparse(url).netloc,
                "title": title,
                "company": urllib.parse.urlparse(url).netloc,
                "location": search_item.get("location", "India"),
                "experience": search_item.get("experience", "Not Specified"),
                "posted_age_days": posted_age_days,
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    return results


def scrape_google_search(driver, search_item):
    """Scrapes Google Search results for job query links."""
    url = search_item.get("portal_url")
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Google Search: {url}")
    if not safe_driver_get(driver, url):
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")
    results = []
    seen = set()

    search_cards = soup.find_all("div", class_=re.compile(r"\bg\b|MjjYud|tF2Cxc"))

    for card in search_cards:
        try:
            h3 = card.find("h3")
            if not h3:
                continue
            title = h3.get_text(" ", strip=True)

            # The first anchor in a Google card may be a related-search link;
            # use the anchor wrapping the result title so the URL stays paired
            # with the job title in both the UI and CSV export.
            a_tag = h3.find_parent("a", href=True)
            if not a_tag:
                continue
            link = a_tag["href"]

            parsed_link = urllib.parse.urlsplit(urllib.parse.urljoin("https://www.google.com", link))
            if parsed_link.hostname and parsed_link.hostname.endswith("google.com"):
                redirect_params = urllib.parse.parse_qs(parsed_link.query)
                for param in ("q", "url", "uddg"):
                    candidate = redirect_params.get(param, [None])[0]
                    if candidate and candidate.startswith(("http://", "https://")):
                        link = candidate
                        break
                else:
                    # Search/refinement links are not job applications. Google
                    # /goto links remain usable browser redirects when their
                    # destination is opaque to the scraper.
                    if parsed_link.path != "/goto":
                        continue
                    link = urllib.parse.urlunsplit(parsed_link)
            else:
                link = urllib.parse.urlunsplit(parsed_link)

            if not link.startswith(("http://", "https://")):
                continue

            if link in seen:
                continue
            seen.add(link)

            snippet_elem = card.find("div", class_=re.compile("VwiCwb|IsZvec|aCOpRe"))
            snippet = snippet_elem.text.strip() if snippet_elem else ""
            posted_age_days = extract_posted_age_days(card)
            if posted_age_days is None:
                posted_age_days = parse_relative_posted_age(snippet.lower())
            if not is_within_max_age(posted_age_days):
                continue

            result_host = urllib.parse.urlsplit(link).hostname or ""
            company = result_host.removeprefix("www.") if "google.com" not in result_host else "Google result"
            job = {
                "portal": "Google Search",
                "title": title,
                "company": company,
                "location": search_item.get("location", "India"),
                "experience": search_item.get("experience", "Not Specified"),
                "posted_age_days": posted_age_days,
                "apply_link": link,
                "recruiter_contact": f"Snippet: {snippet[:100]}..." if snippet else "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    return results


# ---------------------------------------------------------------------------
# Routing and Concurrency Engine
# ---------------------------------------------------------------------------
RSS_API_MAP = {
    "remoteok.com":         scrape_remoteok,
    "weworkremotely.com":   scrape_weworkremotely,
    "upwork.com":           scrape_upwork_rss,
    "remotive.com":         scrape_remotive,
    "freelancer.com":       scrape_upwork_rss,
    "guru.com":             scrape_upwork_rss,
    "peopleperhour.com":    scrape_upwork_rss,
    "remote.co":            scrape_weworkremotely,
    "workingnomads.com":    scrape_weworkremotely,
    "jobgether.com":        scrape_remotive,
    "dailyremote.com":      scrape_remotive,
    "justremote.co":        scrape_remotive,
    "remotefront.io":       scrape_remotive,
    "nodesk.co":            scrape_remotive,
    "virtualvocations.com": scrape_remotive,
    "remotewoman.com":      scrape_remotive,
    "flexjobs.com":         scrape_remotive,
    "remotelyawesome.com":  scrape_remotive,
    "remoteleaf.com":       scrape_remotive,
    "avasarai.com":         scrape_remotive,
}

def dispatch_selenium_target(driver, item):
    """Routes an item to the correct Selenium portal scraper."""
    url = item.get("portal_url", "").lower()
    if "google.com/search" in url:
        return scrape_google_search(driver, item)
    elif "realpython" in url or "fake-jobs" in url:
        return scrape_fake_jobs_sandbox(driver, item)
    elif "linkedin.com" in url:
        return scrape_linkedin_public(driver, item)
    elif "indeed.com" in url:
        return scrape_indeed_public(driver, item)
    elif "naukri.com" in url:
        return scrape_naukri(driver, item)
    elif "foundit.in" in url:
        return scrape_foundit(driver, item)
    elif "shine.com" in url:
        return scrape_shine(driver, item)
    elif "timesjobs.com" in url:
        return scrape_timesjobs(driver, item)
    elif "glassdoor" in url:
        return scrape_glassdoor(driver, item)
    elif "wellfound.com" in url or "angel.co" in url:
        return scrape_wellfound(driver, item)
    else:
        return scrape_generic_selenium(driver, item)


def scrape_jobs(search_items, on_batch_callback=None):
    """
    Optimized concurrent scraping orchestrator:
    1. Splits targets into fast API/RSS targets vs browser-based Selenium targets.
    2. Runs fast API targets concurrently using ThreadPoolExecutor (~2-4 seconds total).
    3. Runs Selenium targets concurrently across dedicated headless Chrome worker instances.
    4. Applies global deduplication and India-eligibility filtering in real-time.
    5. Synchronizes UI streaming updates thread-safely as results arrive.
    """
    start_time = time.time()
    all_jobs = []
    seen_dedup_keys = set()
    callback_lock = threading.Lock()

    # Clean input list
    valid_items = [item for item in search_items if item.get("portal_url", "").strip()]
    if not valid_items:
        return []

    print(f"\n[+] Total targets to scrape: {len(valid_items)}")

    # Classify targets
    api_items = []
    selenium_items = []

    for item in valid_items:
        url = item.get("portal_url", "").lower()
        # LinkedIn will be tried via fast Guest API first
        if "linkedin.com" in url:
            api_items.append((item, "linkedin_guest"))
        elif any(domain in url for domain in RSS_API_MAP):
            matched_fn = next(fn for domain, fn in RSS_API_MAP.items() if domain in url)
            api_items.append((item, matched_fn))
        else:
            selenium_items.append(item)

    def process_and_stream(batch_jobs):
        """Thread-safe filter, deduplicate, and stream callback."""
        if not batch_jobs:
            return 0
        filtered = []
        with callback_lock:
            for j in batch_jobs:
                if not is_india_eligible(j):
                    continue
                posted_age_days = j.get("posted_age_days")
                if posted_age_days is not None and not is_within_max_age(posted_age_days):
                    print(
                        f"[Date Filter] {j.get('portal', 'Job board')}: rejected listing "
                        f"posted {posted_age_days:.0f} days ago "
                        f"(limit: {config.MAX_AGE_DAYS} days)."
                    )
                    continue
                # Canonical dedup key
                link = j.get("apply_link", "").strip().lower()
                key = link if link and link != "n/a" else f"{j.get('portal','')}_{j.get('title','')}_{j.get('company','')}".lower()
                if key in seen_dedup_keys:
                    continue
                seen_dedup_keys.add(key)
                filtered.append(j)

            if filtered:
                all_jobs.extend(filtered)
                if on_batch_callback:
                    try:
                        on_batch_callback(filtered, list(all_jobs))
                    except Exception as cb_err:
                        print(f"[!] Warning in batch callback: {cb_err}")
        return len(filtered)

    # -----------------------------------------------------------------------
    # Phase 1: High-Speed Concurrent API / RSS Scraping
    # -----------------------------------------------------------------------
    if api_items:
        api_workers = getattr(config, "API_WORKERS", 6)
        print(f"\n[Phase 1] Launching {len(api_items)} fast API/RSS targets across {api_workers} concurrent threads...")
        failed_linkedin_items = []

        def run_api_task(item_tuple):
            target_item, target_fn = item_tuple
            try:
                if target_fn == "linkedin_guest":
                    res = scrape_linkedin_guest_api(target_item)
                    if not res:
                        # Fallback to Selenium later if Guest API yielded nothing
                        return target_item, []
                    return None, res
                else:
                    res = target_fn(target_item)
                    return None, res
            except Exception as e:
                print(f"[-] API target error ({target_item.get('portal_url')}): {e}")
                return None, []

        with ThreadPoolExecutor(max_workers=api_workers) as executor:
            futures = [executor.submit(run_api_task, it) for it in api_items]
            for f in as_completed(futures):
                try:
                    fallback_item, jobs = f.result()
                    if fallback_item:
                        failed_linkedin_items.append(fallback_item)
                    if jobs:
                        added = process_and_stream(jobs)
                        if added:
                            print(f"[+] API Streamed: +{added} jobs (Total: {len(all_jobs)})")
                except Exception as fut_err:
                    print(f"[-] Worker future error: {fut_err}")

        # Add any LinkedIn targets that need Selenium fallback
        if failed_linkedin_items:
            print(f"[!] Falling back {len(failed_linkedin_items)} LinkedIn targets to Selenium worker pool.")
            selenium_items.extend(failed_linkedin_items)

    # -----------------------------------------------------------------------
    # Phase 2: Parallel Selenium Browser Scraping
    # -----------------------------------------------------------------------
    if selenium_items:
        num_workers = max(1, min(getattr(config, "SELENIUM_WORKERS", 2), len(selenium_items)))
        print(f"\n[Phase 2] Launching {len(selenium_items)} browser targets across {num_workers} parallel Selenium workers...")

        # Partition items across workers
        chunks = [selenium_items[i::num_workers] for i in range(num_workers)]

        def selenium_worker_loop(worker_id, items_to_scrape):
            driver = None
            try:
                driver = get_chrome_driver()
                for idx, item in enumerate(items_to_scrape):
                    url = item.get("portal_url", "")
                    print(f"[Worker-{worker_id}] [{idx+1}/{len(items_to_scrape)}] {url}")
                    try:
                        jobs = dispatch_selenium_target(driver, item)
                        if jobs:
                            added = process_and_stream(jobs)
                            if added:
                                print(f"[+] [Worker-{worker_id}] Streamed: +{added} jobs (Total: {len(all_jobs)})")
                    except WebDriverException as wde:
                        print(f"[Worker-{worker_id}] Driver hiccup on {url}: {wde}. Restarting driver...")
                        try:
                            driver.quit()
                        except Exception:
                            pass
                        driver = get_chrome_driver()
                    except Exception as err:
                        print(f"[Worker-{worker_id}] Error scraping {url}: {err}")
                    time.sleep(0.3)
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    print(f"[Worker-{worker_id}] Closed driver.")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(selenium_worker_loop, i + 1, chunks[i])
                for i in range(num_workers) if chunks[i]
            ]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as w_err:
                    print(f"[-] Selenium worker error: {w_err}")

    elapsed = round(time.time() - start_time, 2)
    print(f"\n{'='*70}")
    print(f" SCRAPING COMPLETE: Collected {len(all_jobs)} unique India-eligible jobs in {elapsed}s")
    print(f"{'='*70}")
    return all_jobs
