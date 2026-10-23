import os
import sys
import json
import socket
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# Reconfigure console encoding for Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from export_data import export_jobs_to_json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui")

SCRAPING_LOCK = threading.Lock()
IS_SCRAPING = False
ACTIVE_PORT = 5000

SCRAPING_INFO = {
    "is_scraping": False,
    "job_title": ".NET Developer",
    "experience": "5-8 years",
    "max_age_days": 14,
    "location": "Pune, India",
    "start_time": 0,
    "status_message": "Ready",
    "last_error": ""
}

def find_available_port(start_port=5000, max_attempts=20):
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    return start_port

def trigger_background_scrape(params=None):
    global IS_SCRAPING, SCRAPING_INFO
    with SCRAPING_LOCK:
        if IS_SCRAPING:
            return False
        IS_SCRAPING = True
        params = params or {}
        SCRAPING_INFO["is_scraping"] = True
        SCRAPING_INFO["job_title"] = params.get("job_title") or ".NET Developer"
        SCRAPING_INFO["experience"] = params.get("experience") or "5-8 years"
        try:
            SCRAPING_INFO["max_age_days"] = int(params.get("max_age_days", 14))
        except (ValueError, TypeError):
            SCRAPING_INFO["max_age_days"] = 14
        SCRAPING_INFO["location"] = params.get("location") or "Pune, India"
        SCRAPING_INFO["start_time"] = time.time()
        SCRAPING_INFO["status_message"] = "Preparing all configured portal searches..."
        SCRAPING_INFO["last_error"] = ""

    def worker():
        global IS_SCRAPING, SCRAPING_INFO
        try:
            print(f"\n[UI Trigger] Custom scrape requested for '{SCRAPING_INFO['job_title']}' ({SCRAPING_INFO['experience']}, {SCRAPING_INFO['max_age_days']} days, {SCRAPING_INFO['location']})...")
            import main
            if params and params.get("job_title"):
                targets = main.generate_portal_targets(
                    job_title=SCRAPING_INFO["job_title"],
                    experience=SCRAPING_INFO["experience"],
                    location=SCRAPING_INFO["location"],
                    max_age_days=SCRAPING_INFO["max_age_days"]
                )
                SCRAPING_INFO["status_message"] = (
                    f"Searching {len(targets)} configured portal URLs in parallel..."
                )
                main.run_scraper_flow(custom_criteria=targets, max_age_days=SCRAPING_INFO["max_age_days"])
            else:
                main.run_scraper_flow()
            print("[UI Trigger] Scraper run completed.")
        except Exception as e:
            SCRAPING_INFO["last_error"] = str(e)
            SCRAPING_INFO["status_message"] = "Scrape failed"
            print(f"[UI Trigger Error] Scraper execution failed: {e}")
        finally:
            with SCRAPING_LOCK:
                IS_SCRAPING = False
                SCRAPING_INFO["is_scraping"] = False
                if not SCRAPING_INFO["last_error"]:
                    SCRAPING_INFO["status_message"] = "Completed"

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return True

class JobRadarHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=UI_DIR, **kwargs)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/scrape":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
            try:
                params = json.loads(body)
            except Exception:
                params = {}

            started = trigger_background_scrape(params)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            resp = {
                "started": started,
                "is_scraping": IS_SCRAPING,
                "running": IS_SCRAPING,
                "status": SCRAPING_INFO["status_message"],
                "error": SCRAPING_INFO["last_error"],
                "info": SCRAPING_INFO,
                "message": f"Scraping started for {SCRAPING_INFO['job_title']}" if started else "Scraper is already active"
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/jobs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            json_path = os.path.join(UI_DIR, "data", "jobs.json")
            if os.path.exists(json_path):
                with open(json_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                data = export_jobs_to_json()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            return

        elif path == "/api/refresh":
            try:
                data = export_jobs_to_json()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        elif path == "/api/scrape":
            query_params = parse_qs(parsed.query)
            params = {}
            if "job_title" in query_params or "title" in query_params:
                params["job_title"] = query_params.get("job_title", query_params.get("title", [".NET Developer"]))[0]
            if "experience" in query_params or "exp" in query_params:
                params["experience"] = query_params.get("experience", query_params.get("exp", ["5-8 years"]))[0]
            if "max_age_days" in query_params or "days" in query_params:
                try:
                    params["max_age_days"] = int(query_params.get("max_age_days", query_params.get("days", [14]))[0])
                except Exception:
                    params["max_age_days"] = 14
            if "location" in query_params or "loc" in query_params:
                params["location"] = query_params.get("location", query_params.get("loc", ["Pune, India"]))[0]

            started = trigger_background_scrape(params)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            resp = {
                "started": started,
                "is_scraping": IS_SCRAPING,
                "info": SCRAPING_INFO,
                "message": f"Scraping started for {SCRAPING_INFO['job_title']}" if started else "Scraper is already active"
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        elif path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            elapsed = int(time.time() - SCRAPING_INFO["start_time"]) if SCRAPING_INFO["is_scraping"] else 0
            resp = {
                "is_scraping": IS_SCRAPING,
                "running": IS_SCRAPING,
                "status": SCRAPING_INFO["status_message"],
                "error": SCRAPING_INFO["last_error"],
                "info": SCRAPING_INFO,
                "elapsed": elapsed
            }
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # Serve static UI files
        return super().do_GET()

    def log_message(self, format, *args):
        msg = str(args[0])
        if any(msg.startswith(p) for p in ["GET /api", "POST /api", "GET / "]):
            sys.stdout.write(f"[UI Server] {args[0]} - {args[1]}\n")
            sys.stdout.flush()

def start_ui_in_background(port=5000, open_browser=True):
    global ACTIVE_PORT
    export_jobs_to_json()
    ACTIVE_PORT = find_available_port(port)
    url = f"http://localhost:{ACTIVE_PORT}"

    server = ThreadingHTTPServer(('127.0.0.1', ACTIVE_PORT), JobRadarHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    print("\n" + "=" * 70)
    print("       🚀 ANTIGRAVITY JOB RADAR WEB UI IS RUNNING 🚀")
    print(f"       👉 Open your browser at: {url}")
    print("=" * 70 + "\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"[!] Could not open browser automatically: {e}")

    return url

def main():
    print("=" * 68)
    print("          ANTIGRAVITY JOB RADAR - INTERACTIVE WEB UI")
    print("=" * 68)
    
    # 1. Sync & export latest Excel listings
    print("[1/3] Syncing latest saved job listings...")
    export_jobs_to_json()

    # 2. Start Web Server
    port = find_available_port(5000)
    url = f"http://localhost:{port}"

    server = ThreadingHTTPServer(('127.0.0.1', port), JobRadarHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[2/3] Web UI is active and listening at:")
    print(f"\n      🚀  {url}  🚀\n")
    print("[3/3] Starting the initial search across all configured portals...")
    print("=" * 68)

    trigger_background_scrape({
        "job_title": ".NET Developer",
        "experience": "5-8 years",
        "max_age_days": 14,
        "location": "Pune, India",
    })

    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"[!] Could not automatically launch browser: {e}")

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\n[!] Shutting down Job Radar UI server...")
        server.shutdown()
        server.server_close()
        server_thread.join()
        print("[+] Server stopped.")

if __name__ == '__main__':
    main()
