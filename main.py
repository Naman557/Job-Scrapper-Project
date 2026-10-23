import os
import sys
import re
import urllib.parse
import time
import pandas as pd

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import config
from excel_reader import read_jobs_sheet
from scraper import scrape_jobs
from emailer import send_jobs_email

def get_location_weight(location_str):
    """
    Returns an integer weight based on the location priority specified by the user.
    Lower weights indicate higher priority:
    0: Pune
    1: Bangalore/Bengaluru
    2: Hyderabad
    3: Mumbai
    4: Delhi/Gurgaon/Noida/NCR
    5: Kolkata
    6: Remote
    7: Others / Unspecified
    """
    loc = str(location_str).lower()
    
    priorities = [
        ["pune"],
        ["bangalore", "bengaluru"],
        ["hyderabad"],
        ["mumbai"],
        ["delhi", "gurgaon", "gurugram", "noida", "ncr"],
        ["kolkata", "calcutta"]
    ]
    
    for weight, terms in enumerate(priorities):
        for term in terms:
            if term in loc:
                return weight
                
    if "remote" in loc:
        return len(priorities)
        
    return len(priorities) + 1

def generate_portal_targets(job_title=".NET Developer", experience="5-8 years", location="Pune, India", max_age_days=14):
    """Build search targets from every portal URL configured in jobs_input.xlsx."""
    clean_title = (job_title or ".NET Developer").strip()
    clean_exp = (experience or "5-8 years").strip()
    clean_loc = (location or "Pune, India").strip()
    targets = read_jobs_sheet("jobs_input.xlsx")
    search_keys = {"q", "keywords", "query", "txtkeywords", "keyword"}
    location_keys = {"l", "location", "locations", "txtlocation", "loc"}
    slug_title = clean_title.lower().replace(".net", "dot-net")
    title_slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug_title).strip("-")

    for target in targets:
        configured_location = target.get("location", "")
        target_location = (
            configured_location
            if "remote" in configured_location.lower()
            else clean_loc
        )
        target["job_title"] = clean_title
        target["experience"] = clean_exp
        target["location"] = target_location

        parsed = urllib.parse.urlsplit(target["portal_url"])
        host = parsed.netloc.lower()
        slug_location = re.sub(r",?\s*india$", "", target_location, flags=re.IGNORECASE)
        location_slug = re.sub(
            r"[^a-zA-Z0-9]+", "-", slug_location.lower()
        ).strip("-")
        query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        updated_query = []
        for key, value in query:
            normalized_key = key.lower()
            if normalized_key in search_keys:
                if "google.com/search" in target["portal_url"].lower() and normalized_key == "q":
                    value = f"{clean_title} jobs {target_location}"
                else:
                    value = clean_title
            elif normalized_key in location_keys:
                value = target_location
            updated_query.append((key, value))
        path = parsed.path
        if "naukri.com" in host:
            path = f"/{title_slug}-jobs-in-{location_slug}"
        elif "shine.com" in host:
            path = f"/job-search/{title_slug}-jobs-in-{location_slug}"
        elif "placementindia.com" in host:
            path = f"/job-search/{title_slug}-jobs-in-{location_slug}.htm"
        elif "glassdoor" in host:
            path = "/Job/jobs.htm"
            updated_query.extend([
                ("sc.keyword", clean_title),
                ("locT", "C"),
                ("locKeyword", target_location),
            ])
        target["portal_url"] = urllib.parse.urlunsplit((
            parsed.scheme,
            parsed.netloc,
            path,
            urllib.parse.urlencode(updated_query),
            parsed.fragment,
        ))

    return targets

def run_scraper_flow(custom_criteria=None, max_age_days=None):
    print("\n" + "="*70)
    print(f"       SCRAPER RUN STARTING AT: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    if max_age_days is not None:
        config.MAX_AGE_DAYS = int(max_age_days)
        print(f"[Config] Updated MAX_AGE_DAYS to: {config.MAX_AGE_DAYS}")
    
    # 1. Validate configuration
    config_valid = config.validate_config()
    
    # 2. Determine search criteria
    if custom_criteria:
        search_criteria = custom_criteria
        print(f"[+] Loaded {len(search_criteria)} dynamic targets for custom user query.")
    else:
        excel_file = "jobs_input.xlsx"
        if not os.path.exists(excel_file):
            print(f"\n[!] Input file '{excel_file}' not found. Generating sample file...")
            try:
                import create_sample_excel
                create_sample_excel.create_sample()
            except ImportError:
                print("Error: Could not import create_sample_excel.py script.")
                return []
                
        try:
            search_criteria = generate_portal_targets(
                job_title=".NET Developer",
                experience="5-8 years",
                location="Pune, India",
                max_age_days=config.MAX_AGE_DAYS,
            )
        except Exception as e:
            print(f"Error loading search configurations: {e}")
            return []
            
        if not search_criteria:
            print("No job portal targets found in the input spreadsheet.")
            return []
        
    # 3. Perform Scraping across all job boards
    print(f"\n[+] Starting scraping phase for {len(search_criteria)} targets across all boards...")
    # Scrape all boards until completion before consolidating to UI
    scraped_jobs = scrape_jobs(search_criteria)
    print(f"\n[+] Scraping complete from all job boards. Scraped {len(scraped_jobs)} total listings.")
    
    if not scraped_jobs:
        print("No listings found matching search criteria. Updating UI with empty set.")
        try:
            from export_data import export_jobs_to_json
            export_jobs_to_json(jobs=scraped_jobs)
        except Exception as export_err:
            print(f"[!] Warning syncing empty scrape results to UI: {export_err}")
        return []
        
    # 4. Filter, Consolidate and Route Listings (Permanent vs. Freelance)
    permanent_jobs = []
    freelance_jobs = []
    
    for job in scraped_jobs:
        if job.get("job_type") == "freelance":
            freelance_jobs.append(job)
        else:
            permanent_jobs.append(job)
            
    # 5. Sort Listings by Location Priority
    permanent_jobs.sort(key=lambda j: get_location_weight(j.get("location", "")))
    freelance_jobs.sort(key=lambda j: get_location_weight(j.get("location", "")))
    
    print(f"[+] Consolidated: {len(permanent_jobs)} Permanent jobs, {len(freelance_jobs)} Freelance jobs.")
    
    # 6. Save consolidated results locally
    timestamp = time.strftime('%Y%m%d_%H%M%S')
    if permanent_jobs:
        try:
            df_perm = pd.DataFrame(permanent_jobs)
            df_perm.columns = [col.replace("_", " ").title() for col in df_perm.columns]
            try:
                df_perm.to_excel("scraped_jobs_permanent.xlsx", index=False, engine='openpyxl')
                print("[+] Saved permanent job listings to 'scraped_jobs_permanent.xlsx'.")
            except PermissionError:
                fallback_file = f"scraped_jobs_permanent_{timestamp}.xlsx"
                df_perm.to_excel(fallback_file, index=False, engine='openpyxl')
                print(f"[!] Primary file locked by Excel. Saved to fallback '{fallback_file}'.")
        except Exception as save_err:
            print(f"[-] Could not save local permanent jobs file: {save_err}")
            
    if freelance_jobs:
        try:
            df_free = pd.DataFrame(freelance_jobs)
            df_free.columns = [col.replace("_", " ").title() for col in df_free.columns]
            try:
                df_free.to_excel("scraped_jobs_freelance.xlsx", index=False, engine='openpyxl')
                print("[+] Saved freelance job listings to 'scraped_jobs_freelance.xlsx'.")
            except PermissionError:
                fallback_file = f"scraped_jobs_freelance_{timestamp}.xlsx"
                df_free.to_excel(fallback_file, index=False, engine='openpyxl')
                print(f"[!] Primary file locked by Excel. Saved to fallback '{fallback_file}'.")
        except Exception as save_err:
            print(f"[-] Could not save local freelance jobs file: {save_err}")
            
    # 7. Fully export consolidated data to UI JSON now that all scraping is complete
    try:
        from export_data import export_jobs_to_json
        export_jobs_to_json(jobs=scraped_jobs)
        print(f"[+] All job boards scraped & consolidated! Successfully exported {len(scraped_jobs)} jobs to UI.")
    except Exception as export_err:
        print(f"[!] Warning syncing UI data: {export_err}")
            
    # 8. Print Console Summaries
    print("\n" + "="*80)
    print(f"                    PERMANENT JOB LISTINGS (SORTED BY LOCATION)")
    print("="*80)
    for idx, job in enumerate(permanent_jobs, 1):
        print(f"{idx}. {job['title']} at {job['company']}")
        print(f"   Location: {job['location']} | Experience: {job['experience']}")
        print(f"   Link: {job['apply_link']}")
        print(f"   Contact: {job['recruiter_contact']}")
        print("-"*80)
        
    print("\n" + "="*80)
    print(f"                    FREELANCE JOB LISTINGS (SORTED BY LOCATION)")
    print("="*80)
    for idx, job in enumerate(freelance_jobs, 1):
        print(f"{idx}. {job['title']} at {job['company']}")
        print(f"   Location: {job['location']} | Experience: {job['experience']}")
        print(f"   Link: {job['apply_link']}")
        print(f"   Contact: {job['recruiter_contact']}")
        print("-"*80)
        
    # 9. Send Email Reports
    if not config_valid:
        print("\n[!] Skipping email notifications: SMTP settings in .env are not configured.")
        return scraped_jobs
        
    if permanent_jobs:
        send_jobs_email(permanent_jobs, report_type="Permanent")
    else:
        print("No permanent jobs found; skipping permanent email.")
        
    if freelance_jobs:
        send_jobs_email(freelance_jobs, report_type="Freelance")
    else:
        print("No freelance jobs found; skipping freelance email.")

    return scraped_jobs

def main():
    print("="*60)
    print("        ANTIGRAVITY AUTOMATED JOB SEARCH AGENT (V2)")
    print("="*60)
    print(f"Headless Mode: {config.HEADLESS_MODE}")
    print(f"Max Age: {config.MAX_AGE_DAYS} days")
    print(f"Loop Interval: {config.LOOP_INTERVAL} seconds")
    
    # Start the UI first so the browser can show its loader during the initial scrape.
    try:
        import run_ui
        from run_ui import start_ui_in_background
        url = start_ui_in_background(port=5000, open_browser=False)
        started = run_ui.trigger_background_scrape({
            "job_title": ".NET Developer",
            "experience": "5-8 years",
            "max_age_days": config.MAX_AGE_DAYS,
            "location": "Pune, India",
        })
        if not started:
            raise RuntimeError("Could not start the initial portal search.")
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as browser_err:
            print(f"[!] Could not open the UI automatically: {browser_err}")
    except Exception as ui_err:
        print(f"[!] Error starting the UI search workflow: {ui_err}")
        return

    try:
        while True:
            while run_ui.IS_SCRAPING:
                time.sleep(1)

            if config.LOOP_INTERVAL > 0:
                print(
                    f"\n[+] Search complete. Next automatic search in "
                    f"{config.LOOP_INTERVAL} seconds..."
                )
                time.sleep(config.LOOP_INTERVAL)
                if not run_ui.trigger_background_scrape({
                    "job_title": ".NET Developer",
                    "experience": "5-8 years",
                    "max_age_days": config.MAX_AGE_DAYS,
                    "location": "Pune, India",
                }):
                    print("[!] Automatic search skipped because another scrape is active.")
            else:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Scraper loop stopped by user. Exiting.")
        sys.exit(0)

if __name__ == '__main__':
    main()
