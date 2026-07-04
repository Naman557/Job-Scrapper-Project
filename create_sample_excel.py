import pandas as pd

def create_sample():
    # Define sample search configurations including job portals and freelance platforms
    data = {
        'Portal URL': [
            'https://realpython.github.io/fake-jobs/',
            'https://www.linkedin.com/jobs/search?keywords=.NET+Developer&location=Pune',
            'https://www.indeed.com/jobs?q=.net+developer&l=Pune',
            'https://remoteok.com',
            'https://weworkremotely.com',
            'https://upwork.com'
        ],
        'Job Title': [
            '.NET Developer',
            '.NET Developer',
            'Software Engineer (.NET)',
            '.NET Developer',
            '.NET Developer',
            '.NET Developer'
        ],
        'Experience': [
            '3-5 years',
            '3-5 years',
            '3+ years',
            'Not Specified',
            '3-5 years',
            'Not Specified'
        ],
        'Location': [
            'Remote',
            'Pune, India',
            'Pune',
            'Remote',
            'Remote',
            'Remote'
        ]
    }
    
    df = pd.DataFrame(data)
    
    # Save to Excel
    filename = 'jobs_input.xlsx'
    df.to_excel(filename, index=False, engine='openpyxl')
    print(f"Created sample Excel file '{filename}' successfully.")

if __name__ == '__main__':
    create_sample()
