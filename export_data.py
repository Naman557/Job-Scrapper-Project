import os
import glob
import json
import time
import pandas as pd

def normalize_column_name(col):
    return str(col).strip().lower().replace(" ", "_")

def export_jobs_to_json(output_path=os.path.join("ui", "data", "jobs.json")):
    """
    Reads all available scraped job Excel spreadsheets, cleans and normalizes data,
    deduplicates listings by apply link, and exports to a JSON structure for the UI.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    excel_candidates = [
        "scraped_jobs_permanent.xlsx",
        "scraped_jobs_freelance.xlsx",
        "scraped_jobs.xlsx"
    ]
    # Also find any timestamped fallback files
    excel_candidates.extend(glob.glob("scraped_jobs_permanent_*.xlsx"))
    excel_candidates.extend(glob.glob("scraped_jobs_freelance_*.xlsx"))
    
    existing_files = [f for f in excel_candidates if os.path.exists(f)]
    
    all_jobs = []
    seen_links = set()
    
    for file_path in existing_files:
        try:
            df = pd.read_excel(file_path)
            if df.empty:
                continue
                
            # Rename columns to standard names
            df.columns = [normalize_column_name(c) for c in df.columns]
            
            # Infer default job type from filename if missing
            default_type = "freelance" if "freelance" in file_path.lower() else "permanent"
            if "job_type" not in df.columns:
                df["job_type"] = default_type
                
            for _, row in df.iterrows():
                link = str(row.get("apply_link", "")).strip()
                if not link or link.lower() in ["nan", "none", "n/a", ""]:
                    # Create unique key from title + company if link is missing
                    title_comp = f"{row.get('title', '')}_{row.get('company', '')}".strip()
                    dedup_key = title_comp or f"job_{len(all_jobs)}"
                else:
                    dedup_key = link
                    
                if dedup_key in seen_links:
                    continue
                seen_links.add(dedup_key)
                
                def clean_val(v, default=""):
                    if pd.isna(v) or v is None:
                        return default
                    s = str(v).strip()
                    return default if s.lower() in ["nan", "none"] else s
                
                portal = clean_val(row.get("portal"), "General")
                title = clean_val(row.get("title"), "Job Opening")
                company = clean_val(row.get("company"), "Company Confidential")
                location = clean_val(row.get("location"), "Not specified")
                experience = clean_val(row.get("experience"), "Not specified")
                apply_link = clean_val(row.get("apply_link"), "#")
                recruiter = clean_val(row.get("recruiter_contact"), "Refer to Apply Link")
                job_type = clean_val(row.get("job_type"), default_type).lower()
                
                all_jobs.append({
                    "id": f"job-{len(all_jobs) + 1}",
                    "portal": portal,
                    "title": title,
                    "company": company,
                    "location": location,
                    "experience": experience,
                    "apply_link": apply_link,
                    "recruiter_contact": recruiter,
                    "job_type": job_type
                })
        except Exception as e:
            print(f"[!] Warning reading '{file_path}': {e}")
            
    # Calculate metadata statistics
    portals_count = {}
    types_count = {"permanent": 0, "freelance": 0}
    locations_count = {}
    
    for job in all_jobs:
        p = job["portal"]
        portals_count[p] = portals_count.get(p, 0) + 1
        
        jt = job["job_type"]
        types_count[jt] = types_count.get(jt, 0) + 1
        
        loc = job["location"].split(",")[0].strip()
        if loc:
            locations_count[loc] = locations_count.get(loc, 0) + 1

    payload = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(all_jobs),
        "stats": {
            "portals": portals_count,
            "job_types": types_count,
            "top_locations": dict(sorted(locations_count.items(), key=lambda x: x[1], reverse=True)[:10])
        },
        "jobs": all_jobs
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        
    print(f"[+] Successfully exported {len(all_jobs)} jobs to '{output_path}'.")
    return payload

if __name__ == "__main__":
    export_jobs_to_json()
