import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import config

def generate_html_body(jobs, report_type):
    """
    Generates a premium HTML email template with job results formatted inside a CSS table.
    Different styling is applied depending on the report_type ("Permanent" or "Freelance").
    """
    is_freelance = report_type.lower() == "freelance"
    
    # Theme configuration
    if is_freelance:
        header_gradient = "linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)" # Dark Teal Slate
        theme_color = "#203a43"
        report_title = "Freelance & Contract Jobs Report"
        report_subtitle = "Hourly gigs, project contracts, and freelance remote jobs"
        summary_border = "#203a43"
    else:
        header_gradient = "linear-gradient(135deg, #1e3c72 0%, #2a5298 100%)" # Deep Royal Blue
        theme_color = "#2a5298"
        report_title = "Permanent Job Listings Report"
        report_subtitle = "Full-time, permanent, and long-term career placements"
        summary_border = "#3b82f6"

    if not jobs:
        return f"""
        <html>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f4f6f9; color: #333; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                <h2 style="color: #2c3e50; border-bottom: 2px solid {theme_color}; padding-bottom: 10px;">{report_title}</h2>
                <p style="font-size: 16px; line-height: 1.6;">Hello,</p>
                <p style="font-size: 16px; line-height: 1.6; color: #7f8c8d;">No job listings matching your specified search criteria were found during this scraping session.</p>
                <p style="font-size: 14px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 10px; color: #bdc3c7;">Automated Job Scraper Agent</p>
            </div>
        </body>
        </html>
        """

    # Build rows
    rows_html = ""
    for idx, job in enumerate(jobs):
        bg_color = "#ffffff" if idx % 2 == 0 else "#f9fbfd"
        apply_btn = (
            f'<a href="{job["apply_link"]}" target="_blank" style="display: inline-block; padding: 6px 12px; '
            f'background-color: {theme_color}; color: white; text-decoration: none; border-radius: 4px; '
            f'font-size: 12px; font-weight: bold; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);">Apply</a>'
            if job["apply_link"] != "N/A" else '<span style="color: #95a5a6; font-size: 12px;">N/A</span>'
        )
        
        rows_html += f"""
        <tr style="background-color: {bg_color}; border-bottom: 1px solid #eef2f5;">
            <td style="padding: 12px 15px; font-weight: 600; color: #2c3e50;">{job['title']}</td>
            <td style="padding: 12px 15px; color: #576574;">{job['company']}</td>
            <td style="padding: 12px 15px; color: #576574;">{job['location']}</td>
            <td style="padding: 12px 15px; color: #576574;">{job['experience']}</td>
            <td style="padding: 12px 15px; color: #576574; font-size: 13px;">{job['recruiter_contact']}</td>
            <td style="padding: 12px 15px; text-align: center;">{apply_btn}</td>
        </tr>
        """

    html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background-color: #f3f4f6;
                color: #2d3748;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 950px;
                margin: 0 auto;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
                overflow: hidden;
                border: 1px solid #e5e7eb;
            }}
            .header {{
                background: {header_gradient};
                color: #ffffff;
                padding: 35px 30px;
                text-align: left;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 700;
                letter-spacing: -0.5px;
            }}
            .header p {{
                margin: 5px 0 0 0;
                font-size: 14px;
                color: #e2e8f0;
                opacity: 0.9;
            }}
            .content {{
                padding: 30px;
            }}
            .summary-card {{
                background-color: #f8fafc;
                border-left: 4px solid {summary_border};
                padding: 15px 20px;
                margin-bottom: 25px;
                border-radius: 4px;
                font-size: 15px;
                color: #475569;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
                font-size: 14px;
            }}
            th {{
                background-color: #f1f5f9;
                color: #475569;
                text-align: left;
                font-weight: 600;
                padding: 14px 15px;
                border-bottom: 2px solid #e2e8f0;
            }}
            tr:hover {{
                background-color: #f8fafc !important;
            }}
            .footer {{
                background-color: #f9fafb;
                padding: 20px 30px;
                text-align: center;
                font-size: 12px;
                color: #9ca3af;
                border-top: 1px solid #e5e7eb;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{report_title}</h1>
                <p>{report_subtitle}</p>
            </div>
            <div class="content">
                <div class="summary-card">
                    <strong>Search Summary:</strong> Found <strong>{len(jobs)}</strong> matching listings within the past {config.MAX_AGE_DAYS} days.
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Title / Role</th>
                            <th>Company</th>
                            <th>Location</th>
                            <th>Experience</th>
                            <th>Compensation / Contact</th>
                            <th style="text-align: center;">Apply Link</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
            <div class="footer">
                <p>This is an automated email generated by the Antigravity Job Scraper. Runs periodically every {config.LOOP_INTERVAL} seconds.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

def send_jobs_email(jobs, report_type="Permanent"):
    """
    Sends the list of scraped jobs to the configured email receiver using smtplib.
    """
    if not config.SMTP_USERNAME or not config.SMTP_PASSWORD or not config.EMAIL_RECEIVER:
        print(f"Error: SMTP credentials are not configured. Skipping email send for {report_type} jobs.")
        return False
        
    print(f"Preparing to send {report_type} jobs email to {config.EMAIL_RECEIVER}...")
    
    # Create Message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"Scraped {report_type} Job Listings Report ({len(jobs)} Matches)"
    msg['From'] = config.SMTP_USERNAME
    msg['To'] = config.EMAIL_RECEIVER
    
    # Generate HTML content
    html_content = generate_html_body(jobs, report_type)
    msg.attach(MIMEText(html_content, 'html'))
    
    # Send email
    try:
        print(f"Connecting to SMTP Server: {config.SMTP_SERVER}:{config.SMTP_PORT}...")
        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT)
        server.ehlo()
        
        if config.SMTP_PORT == 587:
            print("Starting TLS encryption...")
            server.starttls()
            server.ehlo()
            
        print("Logging in to SMTP server...")
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        
        print("Sending email message...")
        server.sendmail(config.SMTP_USERNAME, config.EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print(f"Email sent successfully for {report_type} jobs!")
        return True
    except Exception as e:
        print(f"Failed to send email via SMTP: {e}")
        return False
