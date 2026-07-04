import os
import sys
import time
import pandas as pd
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

def run_scraper_flow():
    print("\n" + "="*70)
    print(f"       SCRAPER RUN STARTING AT: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    # 1. Validate configuration
    config_valid = config.validate_config()
    
    # 2. Verify spreadsheet exists, create sample if not
    excel_file = "jobs_input.xlsx"
    if not os.path.exists(excel_file):
        print(f"\n[!] Input file '{excel_file}' not found. Generating sample file...")
        try:
            import create_sample_excel
            create_sample_excel.create_sample()
        except ImportError:
            print("Error: Could not import create_sample_excel.py script.")
            return
            
    try:
        search_criteria = read_jobs_sheet(excel_file)
    except Exception as e:
        print(f"Error loading search configurations: {e}")
        return
        
    if not search_criteria:
        print("No job portal targets found in the input spreadsheet.")
        return
        
    # 3. Perform Scraping
    print(f"\n[+] Starting scraping phase for {len(search_criteria)} targets...")
    scraped_jobs = scrape_jobs(search_criteria)
    print(f"\n[+] Scraping complete. Scraped {len(scraped_jobs)} total listings.")
    
    if not scraped_jobs:
        print("No listings found matching search criteria. Skipping report dispatch.")
        return
        
    # 4. Filter and Route Listings (Permanent vs. Freelance)
    permanent_jobs = []
    freelance_jobs = []
    
    for job in scraped_jobs:
        # Separate into permanent and freelance
        if job.get("job_type") == "freelance":
            freelance_jobs.append(job)
        else:
            permanent_jobs.append(job)
            
    # 5. Sort Listings by Location Priority
    permanent_jobs.sort(key=lambda j: get_location_weight(j.get("location", "")))
    freelance_jobs.sort(key=lambda j: get_location_weight(j.get("location", "")))
    
    print(f"[+] Categorized: {len(permanent_jobs)} Permanent jobs, {len(freelance_jobs)} Freelance jobs.")
    
    # 6. Save results locally
    if permanent_jobs:
        try:
            df_perm = pd.DataFrame(permanent_jobs)
            df_perm.columns = [col.replace("_", " ").title() for col in df_perm.columns]
            df_perm.to_excel("scraped_jobs_permanent.xlsx", index=False, engine='openpyxl')
            print("[+] Saved permanent job listings to 'scraped_jobs_permanent.xlsx'.")
        except Exception as save_err:
            print(f"[-] Could not save local permanent jobs file: {save_err}")
            
    if freelance_jobs:
        try:
            df_free = pd.DataFrame(freelance_jobs)
            df_free.columns = [col.replace("_", " ").title() for col in df_free.columns]
            df_free.to_excel("scraped_jobs_freelance.xlsx", index=False, engine='openpyxl')
            print("[+] Saved freelance job listings to 'scraped_jobs_freelance.xlsx'.")
        except Exception as save_err:
            print(f"[-] Could not save local freelance jobs file: {save_err}")
            
    # 7. Print Console Summaries
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
        
    # 8. Send Email Reports
    if not config_valid:
        print("\n[!] Skipping email notifications: SMTP settings in .env are not configured.")
        return
        
    if permanent_jobs:
        send_jobs_email(permanent_jobs, report_type="Permanent")
    else:
        print("No permanent jobs found; skipping permanent email.")
        
    if freelance_jobs:
        send_jobs_email(freelance_jobs, report_type="Freelance")
    else:
        print("No freelance jobs found; skipping freelance email.")

def main():
    print("="*60)
    print("        ANTIGRAVITY AUTOMATED JOB SEARCH AGENT (V2)")
    print("="*60)
    print(f"Headless Mode: {config.HEADLESS_MODE}")
    print(f"Max Age: {config.MAX_AGE_DAYS} days")
    print(f"Loop Interval: {config.LOOP_INTERVAL} seconds")
    
    if config.LOOP_INTERVAL > 0:
        print(f"Starting execution loop. Running every {config.LOOP_INTERVAL} seconds...")
        try:
            while True:
                run_scraper_flow()
                print(f"\n[+] Cycle complete. Next run in {config.LOOP_INTERVAL} seconds...")
                time.sleep(config.LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\n[!] Scraper loop stopped by user. Exiting.")
            sys.exit(0)
    else:
        run_scraper_flow()
        print("\n[+] Single run complete. Exiting.")

if __name__ == '__main__':
    main()
