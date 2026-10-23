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

def generate_portal_targets(job_title=".NET Developer", experience="3-5 years", location="Pune, India", max_age_days=14):
    """
    Dynamically generates targets across major job portals based on user search criteria.
    """
    clean_title = (job_title or ".NET Developer").strip()
    clean_exp = (experience or "3-5 years").strip()
    clean_loc = (location or "Pune, India").strip()
    
    title_slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_title.lower()).strip('-')
    loc_slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean_loc.lower()).strip('-')
    enc_title = urllib.parse.quote(clean_title)
    enc_loc = urllib.parse.quote(clean_loc)

    targets = [
        # Major India Portals
        {
            "portal_url": f"https://www.linkedin.com/jobs/search?keywords={enc_title}&location={enc_loc}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        {
            "portal_url": f"https://in.indeed.com/jobs?q={enc_title}&l={enc_loc}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        {
            "portal_url": f"https://www.naukri.com/{title_slug}-jobs-in-{loc_slug}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        {
            "portal_url": f"https://www.foundit.in/srp/results?query={enc_title}&locations={enc_loc}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        {
            "portal_url": f"https://www.shine.com/job-search/{title_slug}-jobs-in-{loc_slug}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        {
            "portal_url": f"https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&from=submit&txtKeywords={enc_title}&txtLocation={enc_loc}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        {
            "portal_url": f"https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword={enc_title}&locT=C&locKeyword={enc_loc}",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        # Remote & Freelance Portals
        {
            "portal_url": "https://remoteok.com",
            "job_title": clean_title, "experience": clean_exp, "location": "Remote"
        },
        {
            "portal_url": "https://weworkremotely.com",
            "job_title": clean_title, "experience": clean_exp, "location": "Remote"
        },
        {
            "portal_url": "https://www.upwork.com/",
            "job_title": clean_title, "experience": clean_exp, "location": "Remote"
        },
        {
            "portal_url": "https://remotive.com/remote-jobs/software-dev",
            "job_title": clean_title, "experience": clean_exp, "location": "Remote"
        },
        {
            "portal_url": "https://wellfound.com/jobs",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        },
        # Testing Sandbox
        {
            "portal_url": "https://realpython.github.io/fake-jobs/",
            "job_title": clean_title, "experience": clean_exp, "location": clean_loc
        }
    ]
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
            search_criteria = read_jobs_sheet(excel_file)
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
            export_jobs_to_json()
        except Exception:
            pass
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
        export_jobs_to_json()
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
    
    # 1. Start Web UI in background & open browser
    try:
        from run_ui import start_ui_in_background
        start_ui_in_background(port=5000, open_browser=True)
    except Exception as ui_err:
        print(f"[!] Warning launching Web UI: {ui_err}")

    # 2. Run execution loop
    if config.LOOP_INTERVAL > 0:
        print(f"Starting execution loop. Running every {config.LOOP_INTERVAL} seconds...")
        try:
            while True:
                run_scraper_flow()
                print(f"\n[+] Cycle complete. Web UI remains live at http://localhost:5000. Next run in {config.LOOP_INTERVAL}s...")
                time.sleep(config.LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\n[!] Scraper loop stopped by user. Exiting.")
            sys.exit(0)
    else:
        run_scraper_flow()
        print("\n[+] Single run complete. Web UI is live at http://localhost:5000.")
        print("Press Ctrl+C in terminal to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[!] Exiting.")

if __name__ == '__main__':
    main()
