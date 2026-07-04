import re
import time
import random
import urllib.parse
import requests
from datetime import datetime, timezone, timedelta
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
    Scrapes LinkedIn's public job search interface.
    Filters by posting date using &f_TPR parameter.
    """
    portal_url = search_item.get("portal_url")
    job_title_query = search_item.get("job_title", "")
    location_query = search_item.get("location", "")
    
    time_param = get_linkedin_time_param(config.MAX_AGE_DAYS)
    
    if "linkedin.com/jobs" not in portal_url:
        keywords = urllib.parse.quote(job_title_query)
        # Always inject India into the location for India-first results
        india_location = location_query if location_query else "India"
        if "india" not in india_location.lower():
            india_location = f"{india_location}, India"
        location_enc = urllib.parse.quote(india_location)
        url = f"https://www.linkedin.com/jobs/search?keywords={keywords}&location={location_enc}&f_TPR={time_param}"
    else:
        # Append time filter to given url; also inject India if location missing
        url = portal_url
        if "f_TPR" not in url:
            connector = "&" if "?" in url else "?"
            url += f"{connector}f_TPR={time_param}"
        if "india" not in url.lower() and "location" not in url.lower():
            url += "&location=India"

    print(f"Scraping LinkedIn Public Jobs (Max Age: {config.MAX_AGE_DAYS} days): {url}")
    driver.get(url)
    time.sleep(random.uniform(2.5, 4.5))
    
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
    time.sleep(1.5)
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    job_cards = soup.find_all("div", class_=re.compile("job-search-card|base-card"))
    
    results = []
    print(f"Found {len(job_cards)} potential job card elements on LinkedIn.")
    
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
            
            if len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
        except Exception as card_err:
            print(f"Error parsing LinkedIn job card: {card_err}")
            continue
            
    return results

def scrape_indeed_public(driver, search_item):
    """
    Scrapes Indeed Jobs. Filters by posting date using &fromage parameter.
    """
    portal_url = search_item.get("portal_url")
    job_title = search_item.get("job_title", "")
    location = search_item.get("location", "")
    
    if "indeed.com" not in portal_url:
        q = urllib.parse.quote(job_title)
        # Use in.indeed.com (India) and force location to India city or India
        india_location = location if location else "India"
        if "india" not in india_location.lower():
            india_location = f"{india_location}, India"
        l = urllib.parse.quote(india_location)
        url = f"https://in.indeed.com/jobs?q={q}&l={l}&fromage={config.MAX_AGE_DAYS}"
    else:
        url = portal_url
        # Redirect global indeed to India subdomain
        url = url.replace("www.indeed.com", "in.indeed.com")
        if "fromage" not in url:
            connector = "&" if "?" in url else "?"
            url += f"{connector}fromage={config.MAX_AGE_DAYS}"
        
    print(f"Scraping Indeed Public Jobs (Max Age: {config.MAX_AGE_DAYS} days): {url}")
    driver.get(url)
    time.sleep(random.uniform(3.0, 5.0))
    
    if "hcaptcha" in driver.page_source.lower() or "cloudflare" in driver.page_source.lower() or "just a moment" in driver.title.lower():
        print("Warning: Indeed scraping was blocked by Cloudflare/CAPTCHA protection.")
        return []
        
    soup = BeautifulSoup(driver.page_source, "html.parser")
    job_cards = soup.find_all("div", class_=re.compile("job_seen_beacon|slider_container"))
    
    results = []
    print(f"Found {len(job_cards)} potential job cards on Indeed.")
    
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
                apply_link = "https://www.indeed.com" + link_elem["href"]
            
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
            
            if len(results) >= config.MAX_JOBS_PER_PORTAL:
                break
        except Exception as e:
            print(f"Error parsing Indeed job card: {e}")
            continue
            
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

def scrape_jobs(search_items):
    """
    Iterates through search configurations from Excel and scrapes jobs.
    Uses Selenium for web pages, and requests for APIs/RSS.
    """
    driver = None
    all_jobs = []
    
    # Determine if we need Selenium by checking if any portal is LinkedIn/Indeed/Sandbox
    need_selenium = any(
        any(x in item.get("portal_url", "").lower() for x in ["linkedin.com", "indeed.com", "realpython", "fake-jobs"])
        for item in search_items
    )
    
    try:
        if need_selenium:
            driver = get_chrome_driver()
            
        for idx, item in enumerate(search_items):
            url = item.get("portal_url", "").lower()
            print(f"\n--- Scraper Processing Record #{idx+1} ---")
            print(f"URL: {url} | Query: {item.get('job_title')} | Experience: {item.get('experience')} | Location: {item.get('location')}")
            
            try:
                jobs = []
                if "realpython" in url or "fake-jobs" in url:
                    if driver:
                        jobs = scrape_fake_jobs_sandbox(driver, item)
                elif "linkedin.com" in url:
                    if driver:
                        jobs = scrape_linkedin_public(driver, item)
                elif "indeed.com" in url:
                    if driver:
                        jobs = scrape_indeed_public(driver, item)
                elif "remoteok" in url:
                    jobs = scrape_remoteok(item)
                elif "weworkremotely" in url:
                    jobs = scrape_weworkremotely(item)
                elif "upwork" in url:
                    jobs = scrape_upwork_rss(item)
                else:
                    # Generic fallback
                    print(f"Unknown portal URL '{url}'. Attempting RSS or API search based on domain...")
                    if "wework" in url:
                        jobs = scrape_weworkremotely(item)
                    elif "remote" in url:
                        jobs = scrape_remoteok(item)
                    else:
                        if driver:
                            jobs = scrape_linkedin_public(driver, item)
                
                # Apply India-eligibility post-scrape filter
                before_filter = len(jobs)
                jobs = [j for j in jobs if is_india_eligible(j)]
                dropped = before_filter - len(jobs)
                if dropped:
                    print(f"[India Filter] Dropped {dropped} non-India / non-remote jobs.")
                print(f"Successfully scraped {len(jobs)} India-eligible jobs for this criteria.")
                all_jobs.extend(jobs)
                
            except Exception as entry_err:
                print(f"Failed to scrape URL {url}: {entry_err}")
                continue
                
    finally:
        if driver:
            print("\nClosing Chrome WebDriver...")
            driver.quit()
            
    return all_jobs
