"""
Quick SMTP email diagnostic tool.
Run: python test_email.py
"""
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import config

def test_email():
    print("="*60)
    print("  SMTP EMAIL DIAGNOSTIC TEST")
    print("="*60)
    print(f"  Server   : {config.SMTP_SERVER}:{config.SMTP_PORT}")
    print(f"  From     : {config.SMTP_USERNAME}")
    print(f"  Password : {'*' * len(config.SMTP_PASSWORD)} ({len(config.SMTP_PASSWORD)} chars)")
    print(f"  To       : {config.EMAIL_RECEIVER}")
    print()

    # Step 1: DNS resolution
    print("[1] Resolving SMTP host...")
    try:
        ip = socket.gethostbyname(config.SMTP_SERVER)
        print(f"    OK - {config.SMTP_SERVER} -> {ip}")
    except Exception as e:
        print(f"    FAIL - DNS lookup failed: {e}")
        return

    # Step 2: TCP connection
    print(f"[2] Connecting to {config.SMTP_SERVER}:{config.SMTP_PORT}...")
    try:
        server = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=10)
        server.ehlo()
        print("    OK - TCP connection established.")
    except Exception as e:
        print(f"    FAIL - Connection error: {e}")
        return

    # Step 3: STARTTLS
    print("[3] Starting TLS encryption (STARTTLS)...")
    try:
        server.starttls()
        server.ehlo()
        print("    OK - TLS handshake complete.")
    except Exception as e:
        print(f"    FAIL - TLS error: {e}")
        server.quit()
        return

    # Step 4: Authentication
    print(f"[4] Authenticating as '{config.SMTP_USERNAME}'...")
    try:
        server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        print("    OK - Login successful.")
    except smtplib.SMTPAuthenticationError as e:
        print(f"    FAIL - Authentication error: {e}")
        print()
        print("  POSSIBLE CAUSES:")
        print("  1. Incorrect Gmail App Password in .env (must be 16 chars, can have spaces)")
        print("  2. 2-Step Verification is not enabled on your Google Account")
        print("  3. App Password was revoked or expired")
        print("  4. 'Less secure app access' disabled (use App Password instead)")
        print()
        print("  FIX: Go to https://myaccount.google.com/apppasswords and generate a new App Password")
        server.quit()
        return
    except Exception as e:
        print(f"    FAIL - Login error: {e}")
        server.quit()
        return

    # Step 5: Send test email
    print(f"[5] Sending test email to '{config.EMAIL_RECEIVER}'...")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Test Email - Job Scraper SMTP Diagnostics"
        msg["From"] = config.SMTP_USERNAME
        msg["To"] = config.EMAIL_RECEIVER
        html = """
        <html><body style="font-family:Arial,sans-serif;padding:20px">
        <h2 style="color:#2a5298">SMTP Test Successful!</h2>
        <p>Your Job Scraper email configuration is working correctly.</p>
        <p>You will receive job reports at this address.</p>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))
        server.sendmail(config.SMTP_USERNAME, config.EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print(f"    OK - Test email sent! Check inbox (and spam folder) of {config.EMAIL_RECEIVER}")
    except Exception as e:
        print(f"    FAIL - Send error: {e}")

    print()
    print("="*60)
    print("  Diagnostic complete.")
    print("="*60)

if __name__ == "__main__":
    test_email()
