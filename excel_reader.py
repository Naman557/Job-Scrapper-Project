import os
import pandas as pd

def read_jobs_sheet(file_path="jobs_input.xlsx"):
    """
    Reads the Excel file containing job portal search configurations.
    
    Expected Columns:
    - Portal URL: The base URL or search URL of the job board.
    - Job Title: The search terms/role (e.g., ".NET Developer").
    - Experience: Required experience range (e.g., "3-5 years").
    - Location: Target location (e.g., "Pune, India" or "Remote").
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(
            f"The Excel input file '{file_path}' was not found. "
            f"Please ensure it is created in the working directory."
        )
        
    try:
        # Load the sheet using pandas
        df = pd.read_excel(file_path)
        
        # Clean column names (strip spaces, lowercase for easier lookup)
        df.columns = [col.strip().lower() for col in df.columns]
        
        # Define expected column mappings
        column_mapping = {
            'portal url': 'portal_url',
            'job title': 'job_title',
            'experience': 'experience',
            'location': 'location'
        }
        
        # Rename columns based on mapping
        df = df.rename(columns=column_mapping)
        
        # Ensure all required columns exist in some form (case-insensitive)
        required_keys = ['portal_url', 'job_title', 'experience', 'location']
        for key in required_keys:
            if key not in df.columns:
                # Add default empty columns if missing
                df[key] = ""
        
        # Keep only the relevant columns and drop rows where portal_url is empty
        df = df[required_keys]
        df = df.dropna(subset=['portal_url'])
        
        # Convert all entries to string and strip whitespace
        for col in required_keys:
            df[col] = df[col].astype(str).str.strip()
            # Replace 'nan' string (which might result from pandas astype on NaN) with empty string
            df[col] = df[col].apply(lambda x: "" if x.lower() == 'nan' else x)
            
        jobs_to_scrape = df.to_dict(orient='records')
        print(f"Successfully loaded {len(jobs_to_scrape)} job search configurations from '{file_path}'.")
        return jobs_to_scrape
        
    except Exception as e:
        print(f"Error reading Excel file '{file_path}': {e}")
        raise
