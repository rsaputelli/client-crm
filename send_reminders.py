"""
Standalone reminder sender for Client Prospect CRM
-------------------------------------------------
Runs independently of the Streamlit app.
Should be scheduled (daily/weekly) via cron, GitHub Actions, or Supabase Edge Functions.
"""

import os
import sys
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from collections import defaultdict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
from supabase import create_client, Client

# === CONFIG ===
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
EMAIL_HOST = os.environ["EMAIL_HOST"]
EMAIL_PORT = int(os.environ["EMAIL_PORT"])
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

from datetime import datetime
import sys

# --- Fetch reminder frequency from Supabase ---
try:
    res = supabase.table("reminder_settings").select("frequency").single().execute()
    frequency = (res.data or {}).get("frequency", "daily")
except Exception:
    frequency = "daily"  # fallback default

# --- Apply frequency rules ---
if frequency == "off":
    print("Reminders disabled by admin.")
    sys.exit(0)

# Weekly = only run on Mondays (weekday 0)
if frequency == "weekly" and datetime.today().weekday() != 0:
    print("Weekly reminders only fire on Monday.")
    sys.exit(0)

print(f"Reminder frequency is '{frequency}' → proceeding to send reminders…")

# === Email sending helper ===
def send_email(to_address, subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)

# === Step 1: Check settings for frequency ===
def get_reminder_frequency():
    try:
        res = supabase.table("app_settings").select("*").eq("key", "reminder_frequency").single().execute()
        data = getattr(res, "data", None) or {}
        return data.get("value", "daily")  # default daily
    except Exception:
        return "daily"

# === Step 2: Load prospects ===
def load_prospects():
    res = supabase.table("prospects").select("*").execute()
    df = pd.DataFrame(getattr(res, "data", []) or [])
    return df

# === Step 3: Send digests ===
def run_reminders():
    freq = get_reminder_frequency()
    today = datetime.now(ZoneInfo("America/New_York")).date()

    # Respect frequency
    if freq == "off":
        print("Reminders OFF in settings.")
        return
    if freq == "weekly" and today.weekday() != 0:  # Monday only
        print("Weekly reminders only fire on Monday.")
        return

    df = load_prospects()
    if df.empty:
        print("No prospects found.")
        return

    # Normalize follow_up_date
    df["follow_up_date"] = pd.to_datetime(df["follow_up_date"], errors="coerce").dt.date
    if "last_reminded_on" not in df.columns:
        df["last_reminded_on"] = None
    else:
        df["last_reminded_on"] = pd.to_datetime(df["last_reminded_on"], errors="coerce").dt.date

    window_end = today + timedelta(days=7)
    due = df[df["follow_up_date"] <= window_end].copy()

    if due.empty:
        print("No due or overdue follow-ups.")
        return

    due_needing_email = due[(due["last_reminded_on"] != today) | (due["last_reminded_on"].isna())].copy()

    batches = defaultdict(list)
    for _, r in due_needing_email.iterrows():
        recipient = (r.get("assigned_to_email") or "").strip()
        if recipient:
            status = "OVERDUE" if r["follow_up_date"] < today else f"Due {r['follow_up_date']}"
            line = f"- {r.get('first_name','')} {r.get('last_name','')} @ {r.get('company','')}  [{status}]"
            batches[recipient].append({"id": r.get("id"), "line": line})

    for recipient, items in batches.items():
        body_lines = [
            "Here are your follow-ups that are overdue or due within the next 7 days:",
            "",
            *[it["line"] for it in items],
            "",
            "— Client Prospect CRM",
        ]
        subject = "Follow-Up Digest: Overdue & Upcoming (7 days)"
        try:
            send_email(recipient, subject, "\n".join(body_lines))
            print(f"Sent digest to {recipient}")

            ids = [it["id"] for it in items if it["id"]]
            if ids:
                supabase.table("prospects").update(
                    {"last_reminded_on": today.isoformat()}
                ).in_("id", ids).execute()
        except Exception as e:
            print(f"Failed to send to {recipient}: {e}")

if __name__ == "__main__":
    run_reminders()
