import pandas as pd

def create_sample():
    """
    Generates jobs_input.xlsx with all major job portals categorised by type.
    Portal URL         – the search/listing page to scrape.
    Job Title          – keyword to match in scraped results.
    Experience         – experience range to display in report.
    Location           – location hint; 'Remote' for remote-only portals.
    """

    rows = []

    # ─── helpers ────────────────────────────────────────────────────────────────
    def add(url, title=".NET Developer", exp="5-8 years", loc="Pune, India"):
        url = url.strip()
        if not url:
            return
        rows.append({"Portal URL": url, "Job Title": title,
                     "Experience": exp, "Location": loc})

    # ════════════════════════════════════════════════════════════════════════════
    # 1. MAJOR INDIA JOB PORTALS
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.naukri.com/dot-net-developer-jobs-in-pune", loc="Pune, India")
    add("https://www.linkedin.com/jobs/search?keywords=.NET+Developer&location=Pune", loc="Pune, India")
    add("https://in.indeed.com/jobs?q=.net+developer&l=Pune", loc="Pune, India")
    add("https://www.foundit.in/srp/results?query=.net%20developer&locations=Pune", loc="Pune, India")
    add("https://www.shine.com/job-search/net-developer-jobs-in-pune", loc="Pune, India")
    add("https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&from=submit&txtKeywords=.NET+Developer&txtLocation=Pune", loc="Pune, India")
    add("https://www.glassdoor.co.in/Job/pune-net-developer-jobs-SRCH_IL.0,4_IC2856202_KO5,18.htm", loc="Pune, India")
    add("https://www.placementindia.com/job-search/dot-net-developer-jobs-in-pune.htm", loc="Pune, India")
    add("https://www.freshersworld.com/jobs/jobsearch/dot-net-developer-jobs-in-pune", loc="Pune, India")
    add("https://www.apna.co/jobs", loc="India")
    add("https://www.quikr.com/jobs", loc="India")

    # ════════════════════════════════════════════════════════════════════════════
    # 2. TECH JOB PORTALS
    # ════════════════════════════════════════════════════════════════════════════
    add("https://cutshort.io/jobs", loc="India")
    add("https://www.cutshort.io/jobs/dot-net-developer-jobs-in-pune", loc="Pune, India")
    add("https://www.instahyre.com/search-jobs/", loc="India")
    add("https://www.hirist.tech/", loc="India")
    add("https://www.hirist.tech/search/dot-net-developer-jobs-in-pune", loc="Pune, India")
    add("https://www.techgig.com/jobs", loc="India")
    add("https://www.turing.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.flexiple.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.uplers.com/jobs/", loc="Remote", exp="Not Specified")
    add("https://www.avasarai.com/remote-jobs/dot-net", loc="Remote", exp="Not Specified")

    # ════════════════════════════════════════════════════════════════════════════
    # 3. STARTUP / PRODUCT JOBS
    # ════════════════════════════════════════════════════════════════════════════
    add("https://wellfound.com/jobs", loc="India")
    add("https://www.ycombinator.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.ventureloop.com/", loc="Remote", exp="Not Specified")
    add("https://startup.jobs/", loc="Remote", exp="Not Specified")
    add("https://www.builtin.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.builtinpune.com/jobs", loc="Pune, India")

    # ════════════════════════════════════════════════════════════════════════════
    # 4. REMOTE JOB PORTALS
    # ════════════════════════════════════════════════════════════════════════════
    add("https://remoteok.com", loc="Remote", exp="Not Specified")
    add("https://weworkremotely.com", loc="Remote", exp="Not Specified")
    add("https://remote.co/remote-jobs", loc="Remote", exp="Not Specified")
    add("https://remotive.com/remote-jobs/software-dev", loc="Remote", exp="Not Specified")
    add("https://remote.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.flexjobs.com/", loc="Remote", exp="Not Specified")
    add("https://www.workingnomads.com/jobs", loc="Remote", exp="Not Specified")
    add("https://jobgether.com/", loc="Remote", exp="Not Specified")
    add("https://remotefront.io/", loc="Remote", exp="Not Specified")
    add("https://nodesk.co/remote-jobs/", loc="Remote", exp="Not Specified")
    add("https://www.virtualvocations.com/", loc="Remote", exp="Not Specified")
    add("https://dailyremote.com/", loc="Remote", exp="Not Specified")
    add("https://justremote.co/", loc="Remote", exp="Not Specified")
    add("https://remotewoman.com/", loc="Remote", exp="Not Specified")

    # ════════════════════════════════════════════════════════════════════════════
    # 5. DEVELOPER / SOFTWARE JOBS
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.dice.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.hackerrank.com/jobs", loc="Remote", exp="Not Specified")
    add("https://angel.co/jobs", loc="Remote", exp="Not Specified")
    add("https://stackoverflow.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.codementor.io/jobs", loc="Remote", exp="Not Specified")
    add("https://www.gun.io/", loc="Remote", exp="Not Specified")
    add("https://otta.com/", loc="Remote", exp="Not Specified")

    # ════════════════════════════════════════════════════════════════════════════
    # 6. FREELANCE / CONTRACT
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.upwork.com/", loc="Remote", exp="Not Specified")
    add("https://www.toptal.com/talent/apply", loc="Remote", exp="Not Specified")
    add("https://www.freelancer.com/jobs/", loc="Remote", exp="Not Specified")
    add("https://www.guru.com/d/freelancers/q/.net/", loc="Remote", exp="Not Specified")
    add("https://www.peopleperhour.com/", loc="Remote", exp="Not Specified")

    # ════════════════════════════════════════════════════════════════════════════
    # 7. GLOBAL REMOTE
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.remotelyawesome.com/", loc="Remote", exp="Not Specified")
    add("https://remoteleaf.com/", loc="Remote", exp="Not Specified")
    add("https://remoteok.com/remote-dev-jobs", loc="Remote", exp="Not Specified")
    add("https://weworkremotely.com/categories/remote-programming-jobs", loc="Remote", exp="Not Specified")
    add("https://remote.co/remote-jobs/developer/", loc="Remote", exp="Not Specified")
    add("https://www.workingnomads.com/remote-software-development-jobs", loc="Remote", exp="Not Specified")

    # ════════════════════════════════════════════════════════════════════════════
    # 8. JOB AGGREGATORS
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.google.com/search?q=.NET+Developer+jobs+Pune", loc="Pune, India")
    add("https://www.google.com/search?q=.NET+Developer+remote+India+jobs", loc="Remote")
    add("https://www.google.com/search?q=C%23+Developer+jobs+Pune", loc="Pune, India")
    add("https://www.google.com/search?q=.NET+Core+Developer+jobs+Pune", loc="Pune, India")
    add("https://www.google.com/search?q=ASP.NET+Core+Developer+jobs+Pune", loc="Pune, India")

    # ════════════════════════════════════════════════════════════════════════════
    # 9. COMPANY / ATS JOB SOURCES
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.greenhouse.io/", loc="India")
    add("https://jobs.lever.co/", loc="India")
    add("https://www.workday.com/", loc="India")
    add("https://www.smartrecruiters.com/", loc="India")
    add("https://www.ashbyhq.com/", loc="India")
    add("https://www.icims.com/", loc="India")
    add("https://jobs.jobvite.com/", loc="India")
    add("https://www.successfactors.com/", loc="India")
    add("https://careers.oracle.com/", loc="India")

    # ════════════════════════════════════════════════════════════════════════════
    # 10. INDIA IT COMPANY JOB PAGES
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.tcs.com/careers", loc="India")
    add("https://www.infosys.com/careers", loc="India")
    add("https://www.wipro.com/careers/", loc="India")
    add("https://careers.hcltech.com/", loc="India")
    add("https://www.techmahindra.com/en-in/careers/", loc="India")
    add("https://www.cognizant.com/us/en/careers", loc="India")
    add("https://careers.capgemini.com/", loc="India")
    add("https://www.accenture.com/in-en/careers", loc="India")
    add("https://www.ibm.com/careers", loc="India")
    add("https://www.deloitte.com/in/en/careers.html", loc="India")
    add("https://www.persistent.com/careers/", loc="Pune, India")
    add("https://www.ltimindtree.com/careers/", loc="India")
    add("https://www.nagarro.com/en/careers", loc="India")
    add("https://www.epam.com/careers", loc="India")
    add("https://www.globant.com/careers", loc="India")
    add("https://www.publicissapient.com/careers", loc="India")
    add("https://www.virtusa.com/careers", loc="India")
    add("https://www.zoho.com/careers/", loc="India")
    add("https://careers.freshworks.com/", loc="India")
    add("https://www.oracle.com/in/careers/", loc="India")

    # ════════════════════════════════════════════════════════════════════════════
    # 11. PUNE IT / PRODUCT COMPANIES
    # ════════════════════════════════════════════════════════════════════════════
    add("https://www.cybage.com/careers", loc="Pune, India")
    add("https://www.zensar.com/careers", loc="Pune, India")
    add("https://www.qlik.com/us/company/careers", loc="Pune, India")
    add("https://www.eaton.com/in/en-us/company/careers.html", loc="Pune, India")
    add("https://www.mastercard.com/global/en/careers.html", loc="Pune, India")
    add("https://www.fisglobal.com/en/careers", loc="Pune, India")
    add("https://www.fiserv.com/en/careers.html", loc="Pune, India")
    add("https://www.avalara.com/in/en/careers.html", loc="Pune, India")
    add("https://www.bentley.com/en/careers/", loc="Pune, India")
    add("https://www.vodafoneidea.com/careers", loc="Pune, India")

    # ════════════════════════════════════════════════════════════════════════════
    # 12. REMOTE-FIRST COMPANIES
    # ════════════════════════════════════════════════════════════════════════════
    add("https://remote.com/careers", loc="Remote", exp="Not Specified")
    add("https://about.gitlab.com/jobs/", loc="Remote", exp="Not Specified")
    add("https://automattic.com/work-with-us/", loc="Remote", exp="Not Specified")
    add("https://zapier.com/jobs", loc="Remote", exp="Not Specified")
    add("https://www.shopify.com/careers", loc="Remote", exp="Not Specified")
    add("https://www.atlassian.com/company/careers", loc="Remote", exp="Not Specified")
    add("https://www.github.careers/", loc="Remote", exp="Not Specified")
    add("https://careers.microsoft.com/", loc="Remote", exp="Not Specified")
    add("https://www.google.com/about/careers/applications/", loc="Remote", exp="Not Specified")
    add("https://www.amazon.jobs/", loc="Remote", exp="Not Specified")

    # ════════════════════════════════════════════════════════════════════════════
    # Build & write
    # ════════════════════════════════════════════════════════════════════════════
    df = pd.DataFrame(rows, columns=["Portal URL", "Job Title", "Experience", "Location"])
    df.drop_duplicates(subset=["Portal URL"], inplace=True)

    filename = "jobs_input.xlsx"
    df.to_excel(filename, index=False, engine="openpyxl")
    print(f"Created '{filename}' with {len(df)} portal entries.")

if __name__ == "__main__":
    create_sample()
