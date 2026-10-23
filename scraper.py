import re
import time
import random
import urllib.parse
from urllib.parse import urljoin
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import config

def get_chrome_driver():
    """
    Initializes and returns a Selenium Chrome WebDriver with stealth configurations.
    """
    chrome_options = Options()
    if config.HEADLESS_MODE:
        chrome_options.add_argument("--headless=new")
    
    # Anti-detection options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # List of common User-Agents to rotate
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0"
    ]
    chrome_options.add_argument(f"user-agent={random.choice(user_agents)}")
    
    # Avoid Selenium signature detection
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Execute CDP commands to bypass WebDriver flags
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver

def classify_job_type(job):
    """
    Classifies a job as 'freelance' or 'permanent' based on portal name and keywords.
    """
    portal = job.get("portal", "").lower()
    title = job.get("title", "").lower()
    
    # Portal checks
    freelance_portals = ["upwork", "freelancer", "fiverr", "guru"]
    for fp in freelance_portals:
        if fp in portal:
            return "freelance"
            
    # Keyword checks
    freelance_keywords = ["freelance", "contractor", "contract", "hourly", "gig", "part-time", "temporary", "consultant"]
    for kw in freelance_keywords:
        if kw in title:
            return "freelance"
            
    return "permanent"

# ---------------------------------------------------------------------------
# India Eligibility Filter
# ---------------------------------------------------------------------------

# Known Indian cities and regions used to verify a job is India-based
INDIA_TERMS = [
    "india", "pune", "mumbai", "bengaluru", "bangalore",
    "hyderabad", "delhi", "gurgaon", "gurugram", "noida",
    "chennai", "kolkata", "ahmedabad", "jaipur", "surat",
    "lucknow", "nagpur", "indore", "bhopal", "patna",
    "chandigarh", "coimbatore", "kochi", "vizag", "vadodara"
]

# Terms that clearly indicate a non-Indian location (not allowed unless remote)
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

# Terms that signal a worldwide/remote-friendly job
REMOTE_TERMS = [
    "remote", "worldwide", "global", "anywhere", "work from home",
    "wfh", "distributed"
]

def is_india_eligible(job):
    """
    Returns True if an Indian job-seeker can reasonably apply for this job.

    Rules:
    1. PASS if location contains an Indian city/country name.
    2. PASS if location contains a remote/worldwide keyword  
       (the job is location-agnostic, so Indian applicants can apply).
    3. FAIL if location contains a clearly non-Indian country/city
       (e.g., London, New York) and is NOT remote.
    4. PASS for unknown / unspecified locations (give benefit of doubt).
    """
    loc = str(job.get("location", "")).lower()
    portal = str(job.get("portal", "")).lower()

    # Freelance platforms (Upwork, WWR, RemoteOK) are always global-remote -> PASS
    always_remote_portals = ["upwork", "weworkremotely", "remoteok"]
    if any(p in portal for p in always_remote_portals):
        return True

    # Explicit India mention -> PASS
    if any(term in loc for term in INDIA_TERMS):
        return True

    # Remote / worldwide mention -> PASS
    if any(term in loc for term in REMOTE_TERMS):
        return True

    # Clearly non-Indian country/city without remote -> FAIL
    if any(term in loc for term in NON_INDIA_COUNTRY_TERMS):
        return False

    # Unknown or blank location -> PASS (benefit of doubt)
    return True

def get_linkedin_time_param(days):
    """
    Maps days limit to LinkedIn f_TPR parameter.
    r86400: past 24h
    r604800: past week
    r1209600: past 2 weeks
    r2592000: past month
    """
    if days <= 1:
        return "r86400"
    elif days <= 7:
        return "r604800"
    elif days <= 14:
        return "r1209600"
    else:
        return "r2592000"

def scrape_fake_jobs_sandbox(driver, search_item):
    """
    Scrapes the RealPython fake jobs sandbox page.
    Filters mock entries locally by title, location, and date (mocked to recent).
    """
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    location_query = search_item.get("location", "").lower()
    
    print(f"Scraping sandbox environment: {url}")
    driver.get(url)
    
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "ResultsContainer"))
    )
    
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
        
        # Filters
        if job_title_query and job_title_query not in title.lower():
            continue
        if location_query and location_query != "remote" and location_query not in location.lower():
            continue
            
        apply_link = "N/A"
        if len(link_elems) > 1:
            apply_link = link_elems[1]["href"]
        elif len(link_elems) == 1:
            apply_link = link_elems[0]["href"]
            
        recruiter_contact = "sandbox-recruiter@realpython.io"
        
        job = {
            "portal": "RealPython Sandbox",
            "title": title,
            "company": company,
            "location": location,
            "experience": search_item.get("experience", "Not Specified"),
            "apply_link": apply_link,
            "recruiter_contact": recruiter_contact
        }
        job["job_type"] = classify_job_type(job)
        results.append(job)
        
        if len(results) >= config.MAX_JOBS_PER_PORTAL:
            break
            
    return results

def scrape_linkedin_public(driver, search_item):
    """
    Scrapes LinkedIn's public job search interface with infinite-scroll pagination.
    Keeps scrolling and loading more pages until no new cards appear.
    Filters by posting date using &f_TPR parameter.
    """
    portal_url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "")
    location_query = search_item.get("location", "")
    max_jobs = config.MAX_JOBS_PER_PORTAL  # 0 = unlimited

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
    PAGE_SIZE = 25  # LinkedIn loads 25 results per page offset

    print(f"Scraping LinkedIn Public Jobs (Max Age: {config.MAX_AGE_DAYS} days, all pages): {base_url}")

    while True:
        # LinkedIn pagination uses &start= offset parameter
        url = f"{base_url}&start={page_offset}"
        driver.get(url)
        time.sleep(random.uniform(2.5, 4.0))

        # Scroll down slowly to trigger lazy-loaded cards
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(4):
            driver.execute_script("window.scrollBy(0, window.innerHeight);")
            time.sleep(0.8)

        # Click "See more jobs" button if it exists (some pages show it)
        try:
            see_more = driver.find_element(By.XPATH, "//button[contains(@aria-label,'See more jobs')]")
            driver.execute_script("arguments[0].click();", see_more)
            time.sleep(1.5)
        except Exception:
            pass

        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.find_all("div", class_=re.compile("job-search-card|base-card"))

        new_cards_found = 0
        for card in job_cards:
            try:
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

                # Deduplicate
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
                    "apply_link": apply_link,
                    "recruiter_contact": "Refer to Apply Link"
                }
                job["job_type"] = classify_job_type(job)
                results.append(job)

            except Exception as card_err:
                print(f"Error parsing LinkedIn job card: {card_err}")
                continue

        print(f"  LinkedIn page offset={page_offset}: {new_cards_found} new cards, {len(results)} total collected so far.")

        # Stop if no new cards were loaded on this page (end of results)
        if new_cards_found == 0:
            print("  LinkedIn: No new cards found. End of results.")
            break

        # Stop if we hit the user-defined cap (0 = unlimited)
        if max_jobs > 0 and len(results) >= max_jobs:
            print(f"  LinkedIn: Reached MAX_JOBS_PER_PORTAL cap ({max_jobs}).")
            break

        page_offset += PAGE_SIZE

        # Safety limit: LinkedIn public search rarely shows more than 1000 results
        if page_offset > 975:
            print("  LinkedIn: Reached maximum offset (1000). Stopping.")
            break

    print(f"LinkedIn scraping complete. Collected {len(results)} jobs total.")
    return results


def scrape_indeed_public(driver, search_item):
    """
    Scrapes Indeed India jobs across multiple pages using &start= offset pagination.
    Filters by date using &fromage parameter. Deduplicates results.
    """
    portal_url = search_item.get("portal_url")
    job_title = search_item.get("job_title", "")
    location = search_item.get("location", "")
    max_jobs = config.MAX_JOBS_PER_PORTAL  # 0 = unlimited

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
    PAGE_SIZE = 10   # Indeed shows ~10 jobs per page

    print(f"Scraping Indeed India Jobs (Max Age: {config.MAX_AGE_DAYS} days, all pages): {base_url}")

    for page_num in range(50):  # max 50 pages = 500 jobs safety cap
        start_offset = page_num * PAGE_SIZE
        url = f"{base_url}&start={start_offset}"

        driver.get(url)
        time.sleep(random.uniform(3.0, 5.0))

        # Check for bot blocks
        if ("hcaptcha" in driver.page_source.lower()
                or "cloudflare" in driver.page_source.lower()
                or "just a moment" in driver.title.lower()):
            print(f"Warning: Indeed page {page_num + 1} was blocked by bot protection. Stopping pagination.")
            break

        soup = BeautifulSoup(driver.page_source, "html.parser")
        job_cards = soup.find_all("div", class_=re.compile("job_seen_beacon|slider_container"))

        if not job_cards:
            print(f"  Indeed page {page_num + 1}: No job cards found. End of results.")
            break

        new_cards_found = 0
        for card in job_cards:
            try:
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

                # Deduplicate
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
                    "apply_link": apply_link,
                    "recruiter_contact": "Refer to Apply Link"
                }
                job["job_type"] = classify_job_type(job)
                results.append(job)

            except Exception as e:
                print(f"Error parsing Indeed job card: {e}")
                continue

        print(f"  Indeed page {page_num + 1} (start={start_offset}): {new_cards_found} new cards, {len(results)} total.")

        if new_cards_found == 0:
            print("  Indeed: No new cards on this page. End of results.")
            break

        if max_jobs > 0 and len(results) >= max_jobs:
            print(f"  Indeed: Reached MAX_JOBS_PER_PORTAL cap ({max_jobs}).")
            break

    print(f"Indeed scraping complete. Collected {len(results)} jobs total.")
    return results


def scrape_remoteok(search_item):
    """
    Scrapes RemoteOK public JSON API. Returns remote jobs matching the query.
    Filters out jobs older than config.MAX_AGE_DAYS.
    """
    query = search_item.get("job_title", "").lower()
    print(f"Scraping RemoteOK API for: {query}")
    
    url = "https://remoteok.com/api"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    results = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[-] RemoteOK API returned status code {response.status_code}")
            return []
            
        jobs_data = response.json()
        
        # RemoteOK API returns legal disclaimer as the first element
        if len(jobs_data) <= 1:
            return []
            
        now = datetime.now(timezone.utc)
        
        for job_entry in jobs_data[1:]:
            title = job_entry.get("position", "")
            company = job_entry.get("company", "")
            apply_link = job_entry.get("url", "")
            tags = job_entry.get("tags", [])
            date_str = job_entry.get("date", "") # ISO format e.g. "2026-07-01T12:00:00-07:00"
            
            # Apply keywords filter
            if query and query not in title.lower() and not any(query in tag.lower() for tag in tags):
                continue
                
            # Date filter
            if date_str:
                try:
                    # ISO string parse. In python 3.11+, fromisoformat supports Z and timezone offsets
                    pub_dt = datetime.fromisoformat(date_str)
                    # Convert to utc for comparison
                    pub_dt_utc = pub_dt.astimezone(timezone.utc)
                    age_days = (now - pub_dt_utc).days
                    if age_days > config.MAX_AGE_DAYS:
                        continue
                except Exception as date_err:
                    # Fallback to direct string check or keep job if unparseable
                    print(f"Date parse error: {date_err}")
            
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
            
            if len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
                
    except Exception as e:
        print(f"Error scraping RemoteOK: {e}")
        
    return results

def scrape_weworkremotely(search_item):
    """
    Scrapes WeWorkRemotely RSS feed for remote programming jobs.
    Filters by search query and date.
    """
    query = search_item.get("job_title", "").lower()
    print(f"Scraping WeWorkRemotely RSS feed for: {query}")
    
    url = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    
    results = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[-] WeWorkRemotely RSS returned status code {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.content, features="xml")
        items = soup.find_all("item")
        
        now = datetime.now(timezone.utc)
        
        for item in items:
            title_text = item.find("title").text if item.find("title") else "N/A"
            link = item.find("link").text if item.find("link") else "N/A"
            pub_date_text = item.find("pubDate").text if item.find("pubDate") else ""
            
            # WWR RSS titles are formatted as: "Company Name: Job Title"
            company = "N/A"
            title = title_text
            if ":" in title_text:
                parts = title_text.split(":", 1)
                company = parts[0].strip()
                title = parts[1].strip()
                
            # Filter title keyword
            if query and query not in title.lower():
                continue
                
            # Date filter
            if pub_date_text:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_text)
                    age_days = (now - pub_dt).days
                    if age_days > config.MAX_AGE_DAYS:
                        continue
                except Exception as date_err:
                    print(f"WWR date parsing failed: {date_err}")
                    
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
            
            if len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
                
    except Exception as e:
        print(f"Error scraping WeWorkRemotely RSS: {e}")
        
    return results

def scrape_upwork_rss(search_item):
    """
    Scrapes Upwork RSS feed for the given search query.
    Always classifies jobs as 'freelance'.
    """
    query = search_item.get("job_title", "")
    print(f"Scraping Upwork RSS for query: {query}")
    
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.upwork.com/ab/feed/jobs/rss?q={encoded_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    results = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[-] Upwork RSS returned status code {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.content, features="xml")
        items = soup.find_all("item")
        
        now = datetime.now(timezone.utc)
        
        for item in items:
            title = item.find("title").text if item.find("title") else "N/A"
            link = item.find("link").text if item.find("link") else "N/A"
            pub_date_text = item.find("pubDate").text if item.find("pubDate") else ""
            desc_text = item.find("description").text if item.find("description") else ""
            
            # Filter date
            if pub_date_text:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_text)
                    age_days = (now - pub_dt).days
                    if age_days > config.MAX_AGE_DAYS:
                        continue
                except Exception as date_err:
                    print(f"Upwork date parsing failed: {date_err}")
            
            # Clean up Upwork title which often contains category metadata
            title = title.replace(" - Upwork", "").strip()
            
            # Parse budget/hourly rate from description if available
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
                "job_type": "freelance"  # Upwork is always freelance
            }
            results.append(job)
            
            if len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
                
    except Exception as e:
        print(f"Error scraping Upwork RSS: {e}")
        
    return results

# ─────────────────────────────────────────────────────────────────────────────
# NEW PORTAL SCRAPERS
# ─────────────────────────────────────────────────────────────────────────────

def scrape_naukri(driver, search_item):
    """Scrapes Naukri.com job listings for the given search URL."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Naukri: {url}")
    driver.get(url)
    time.sleep(random.uniform(3.0, 5.0))

    # Scroll to load lazy cards
    for _ in range(3):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(0.8)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    # Naukri job cards are inside article tags or divs with class 'jobTuple'
    cards = soup.find_all("article", class_=re.compile("jobTuple|job-container|cust-job-tuple"))
    if not cards:
        cards = soup.find_all("div", class_=re.compile("jobTuple|srp-jobtuple-wrapper"))

    results = []
    seen = set()
    print(f"  Naukri: Found {len(cards)} cards.")

    for card in cards:
        try:
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
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception as e:
            continue

    print(f"  Naukri: Collected {len(results)} jobs.")
    return results


def scrape_foundit(driver, search_item):
    """Scrapes Foundit (formerly Monster India) job listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Foundit: {url}")
    driver.get(url)
    time.sleep(random.uniform(3.5, 5.5))

    for _ in range(3):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(0.8)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_=re.compile("card-body|job-card|srpResultCardContainer"))

    results = []
    seen = set()
    print(f"  Foundit: Found {len(cards)} cards.")

    for card in cards:
        try:
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
    """Scrapes Shine.com job listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Shine.com: {url}")
    driver.get(url)
    time.sleep(random.uniform(3.0, 5.0))

    for _ in range(3):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(0.7)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_=re.compile("job-listing|jobCardWrapper|job_listing"))

    results = []
    seen = set()
    print(f"  Shine: Found {len(cards)} cards.")

    for card in cards:
        try:
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
    """Scrapes TimesJobs job listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping TimesJobs: {url}")
    driver.get(url)
    time.sleep(random.uniform(3.0, 5.5))

    for _ in range(3):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(0.7)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("li", class_=re.compile("clearfix|job-bx"))

    results = []
    seen = set()
    print(f"  TimesJobs: Found {len(cards)} cards.")

    for card in cards:
        try:
            title_elem = card.find("h2") or card.find("a", class_=re.compile("jobTitle"))
            title = title_elem.text.strip() if title_elem else "N/A"

            company_elem = card.find("h3", class_=re.compile("joblist-comp-name")) or card.find("span", class_=re.compile("company"))
            company = company_elem.text.strip() if company_elem else "N/A"

            loc_elem = card.find("span", class_=re.compile("srp-skills"))
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
    """Scrapes Glassdoor India job listings."""
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Glassdoor India: {url}")
    driver.get(url)
    time.sleep(random.uniform(4.0, 6.0))

    for _ in range(3):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(0.8)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("li", class_=re.compile("JobsList_jobListItem|react-job-listing"))
    if not cards:
        cards = soup.find_all("div", attrs={"data-test": "jobListing"})

    results = []
    seen = set()
    print(f"  Glassdoor: Found {len(cards)} cards.")

    for card in cards:
        try:
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
    driver.get(url)
    time.sleep(random.uniform(4.0, 6.0))

    for _ in range(4):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(1.0)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("div", class_=re.compile("styles_component|JobListings_jobListings|job-listing"))

    results = []
    seen = set()
    print(f"  Wellfound: Found {len(cards)} cards.")

    for card in cards:
        try:
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


def scrape_remotive(search_item):
    """Scrapes Remotive.com RSS feed for remote developer jobs."""
    query = search_item.get("job_title", "").lower()
    print(f"Scraping Remotive RSS for: {query}")

    url = "https://remotive.com/remote-jobs/feed/software-dev"
    headers = {"User-Agent": "Mozilla/5.0"}
    results = []

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"  [-] Remotive RSS returned {response.status_code}")
            return []

        soup = BeautifulSoup(response.content, features="xml")
        items = soup.find_all("item")
        now = datetime.now(timezone.utc)

        for item in items:
            title = item.find("title").text.strip() if item.find("title") else "N/A"
            link  = item.find("link").text.strip()  if item.find("link")  else "N/A"
            pub_date_text = item.find("pubDate").text if item.find("pubDate") else ""

            if query and query not in title.lower():
                continue

            if pub_date_text:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_text)
                    if (now - pub_dt).days > config.MAX_AGE_DAYS:
                        continue
                except Exception:
                    pass

            job = {
                "portal": "Remotive",
                "title": title,
                "company": "N/A",
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

    print(f"  Remotive: Collected {len(results)} jobs.")
    return results


def scrape_generic_selenium(driver, search_item):
    """
    Generic fallback Selenium scraper for company career pages and other portals.
    Attempts to find common job listing patterns on any page.
    Matches links whose text contains the job title keyword.
    """
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping (generic): {url}")
    driver.get(url)
    time.sleep(random.uniform(3.5, 5.5))

    for _ in range(3):
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(0.7)

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Try common job card selectors
    cards = (
        soup.find_all("div",  class_=re.compile("job|career|opening|position|listing", re.I))
        or soup.find_all("li",   class_=re.compile("job|career|opening|position", re.I))
        or soup.find_all("tr",   class_=re.compile("job|career|opening", re.I))
    )

    results = []
    seen = set()

    # Fallback: scan all anchor tags whose text matches the job title
    if not cards:
        anchors = soup.find_all("a", href=True)
        for a in anchors:
            text = a.get_text(strip=True)
            if job_title_query and job_title_query not in text.lower():
                continue
            href = a["href"]
            if not href.startswith("http"):
                from urllib.parse import urljoin
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
        print(f"  Generic (anchor fallback): Collected {len(results)} jobs from {url}")
        return results

    for card in cards:
        try:
            title_elem = card.find(["h2", "h3", "h4", "a"])
            title = title_elem.text.strip() if title_elem else "N/A"

            if job_title_query and job_title_query not in title.lower():
                continue

            link_elem = card.find("a", href=True)
            apply_link = "N/A"
            if link_elem:
                href = link_elem["href"]
                if not href.startswith("http"):
                    from urllib.parse import urljoin
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
                "apply_link": apply_link,
                "recruiter_contact": "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    print(f"  Generic: Collected {len(results)} jobs from {url}")
    return results


def scrape_google_search(driver, search_item):
    """
    Scrapes Google Search results for job query links and snippets.
    """
    url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "").lower()
    max_jobs = config.MAX_JOBS_PER_PORTAL

    print(f"Scraping Google Search: {url}")
    driver.get(url)
    time.sleep(random.uniform(3.0, 4.5))

    soup = BeautifulSoup(driver.page_source, "html.parser")
    results = []
    seen = set()

    # Google search result cards are typically div.g or div.MjjYud
    search_cards = soup.find_all("div", class_=re.compile(r"\bg\b|MjjYud|tF2Cxc"))

    for card in search_cards:
        try:
            h3 = card.find("h3")
            if not h3:
                continue
            title = h3.text.strip()

            a_tag = card.find("a", href=True)
            if not a_tag:
                continue
            link = a_tag["href"]

            # Handle Google redirect URLs like /url?q=https://target.com...
            if link.startswith("/url?"):
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                if "q" in parsed_q and parsed_q["q"]:
                    link = parsed_q["q"][0]

            if not link.startswith("http") or "google.com" in link:
                continue

            if link in seen:
                continue
            seen.add(link)

            snippet_elem = card.find("div", class_=re.compile("VwiCwb|IsZvec|aCOpRe"))
            snippet = snippet_elem.text.strip() if snippet_elem else ""

            job = {
                "portal": "Google Search",
                "title": title,
                "company": "Aggregated via Google",
                "location": search_item.get("location", "India"),
                "experience": search_item.get("experience", "Not Specified"),
                "apply_link": link,
                "recruiter_contact": f"Snippet: {snippet[:100]}..." if snippet else "Refer to Apply Link"
            }
            job["job_type"] = classify_job_type(job)
            results.append(job)

            if max_jobs > 0 and len(results) >= max_jobs:
                break
        except Exception:
            continue

    if not results:
        return scrape_generic_selenium(driver, search_item)

    print(f"  Google Search: Collected {len(results)} search result links.")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────

# Domains that explicitly require Selenium
SELENIUM_DOMAINS = [
    "linkedin.com", "indeed.com", "naukri.com", "foundit.in",
    "shine.com", "timesjobs.com", "glassdoor.co.in", "glassdoor.com",
    "wellfound.com", "angel.co", "cutshort.io", "instahyre.com",
    "hirist.tech", "techgig.com", "realpython", "fake-jobs",
    "google.com",
    # Company career pages & ATS sources
    "tcs.com", "infosys.com", "wipro.com", "hcltech.com",
    "techmahindra.com", "persistent.com", "ltimindtree.com",
    "nagarro.com", "zoho.com", "freshworks.com", "cybage.com",
    "zensar.com", "greenhouse.io", "lever.co", "workday.com",
    "smartrecruiters.com", "ashbyhq.com", "icims.com", "jobvite.com"
]

# Domains routed to their specific RSS / API scrapers (no Selenium needed)
RSS_API_MAP = {
    "remoteok.com":       scrape_remoteok,
    "weworkremotely.com": scrape_weworkremotely,
    "upwork.com":         scrape_upwork_rss,
    "remotive.com":       scrape_remotive,
    # Freelancer / Guru / PeoplePerHour → Upwork RSS as best-effort proxy
    "freelancer.com":     scrape_upwork_rss,
    "guru.com":           scrape_upwork_rss,
    "peopleperhour.com":  scrape_upwork_rss,
    # Remote job boards with known RSS/API feeds
    "remote.co":          scrape_weworkremotely,
    "workingnomads.com":  scrape_weworkremotely,
    "jobgether.com":      scrape_remotive,
    "dailyremote.com":    scrape_remotive,
    "justremote.co":      scrape_remotive,
    "remotefront.io":     scrape_remotive,
    "nodesk.co":          scrape_remotive,
    "virtualvocations.com": scrape_remotive,
    "remotewoman.com":    scrape_remotive,
    "flexjobs.com":       scrape_remotive,
    "remotelyawesome.com": scrape_remotive,
    "remoteleaf.com":     scrape_remotive,
    "avasarai.com":       scrape_remotive,
}


def scrape_jobs(search_items):
    """
    Iterates through search configurations from Excel and scrapes jobs.
    Routes each URL to the best-matching scraper.
    """
    driver = None
    all_jobs = []

    # Initialize Selenium if at least one target is NOT handled by RSS/API
    need_selenium = any(
        not any(rss_domain in item.get("portal_url", "").lower() for rss_domain in RSS_API_MAP)
        for item in search_items
    )

    try:
        if need_selenium:
            driver = get_chrome_driver()

        for idx, item in enumerate(search_items):
            url_raw = item.get("portal_url", "").strip()
            if not url_raw:
                continue

            url = url_raw.lower()
            print(f"\n{'─'*60}")
            print(f"[{idx+1}/{len(search_items)}] {url_raw}")
            print(f"Query: {item.get('job_title')} | Exp: {item.get('experience')} | Loc: {item.get('location')}")

            try:
                jobs = []

                # ── RSS / API portals ──────────────────────────────────────
                matched_rss = False
                for domain, fn in RSS_API_MAP.items():
                    if domain in url:
                        jobs = fn(item)
                        matched_rss = True
                        break

                if not matched_rss:
                    # ── Selenium portals ───────────────────────────────────
                    if not driver:
                        driver = get_chrome_driver()

                    if "google.com/search" in url:
                        jobs = scrape_google_search(driver, item)
                    elif "realpython" in url or "fake-jobs" in url:
                        jobs = scrape_fake_jobs_sandbox(driver, item)
                    elif "linkedin.com" in url:
                        jobs = scrape_linkedin_public(driver, item)
                    elif "indeed.com" in url:
                        jobs = scrape_indeed_public(driver, item)
                    elif "naukri.com" in url:
                        jobs = scrape_naukri(driver, item)
                    elif "foundit.in" in url:
                        jobs = scrape_foundit(driver, item)
                    elif "shine.com" in url:
                        jobs = scrape_shine(driver, item)
                    elif "timesjobs.com" in url:
                        jobs = scrape_timesjobs(driver, item)
                    elif "glassdoor" in url:
                        jobs = scrape_glassdoor(driver, item)
                    elif "wellfound.com" in url or "angel.co" in url:
                        jobs = scrape_wellfound(driver, item)
                    else:
                        # Generic Selenium fallback for company career pages, ATS portals, etc.
                        jobs = scrape_generic_selenium(driver, item)

                # ── India eligibility filter ───────────────────────────────
                before = len(jobs)
                jobs = [j for j in jobs if is_india_eligible(j)]
                dropped = before - len(jobs)
                if dropped:
                    print(f"[India Filter] Dropped {dropped} non-India / non-remote listings.")

                print(f"✓ {len(jobs)} India-eligible jobs collected.")
                all_jobs.extend(jobs)

                # Short delay between requests to be polite
                time.sleep(random.uniform(1.0, 2.0))

            except Exception as entry_err:
                print(f"✗ Failed to scrape {url_raw}: {entry_err}")
                continue

    finally:
        if driver:
            print("\nClosing Chrome WebDriver...")
            driver.quit()

    print(f"\n{'═'*60}")
    print(f"Total India-eligible jobs collected: {len(all_jobs)}")
    return all_jobs



