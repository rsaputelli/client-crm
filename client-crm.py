# === Streamlit CRM App for Multi-Client Tracking ===
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === CONFIGURATION ===
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
EMAIL_HOST = st.secrets["EMAIL_HOST"]
EMAIL_PORT = st.secrets["EMAIL_PORT"]
EMAIL_USER = st.secrets["EMAIL_USER"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="Client Prospect CRM", layout="wide")
st.title("📇 Multi-Client Prospect Tracker")

CLIENT_OPTIONS = [
    "WOEMA", "SCAAP", "CTAAP", "NJAFP", "DAFP", "MAFP", "HAFP",
    "PAACP", "DEACP", "ACPNJ", "NSSA", "SEMPA", "WAPA"
]

# === Function to Send Email ===
def send_email(to_address, subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = to_address
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        st.error(f"Failed to send email to {to_address}: {e}")

# === Live Usage Summary ===
try:
    count_res = supabase.table("prospects").select("id", count="exact").execute()
    row_count = getattr(count_res, "count", 0) or 0
    st.sidebar.markdown(f"### 📊 Total Prospects: {row_count}")
    if row_count > 18000:
        st.sidebar.warning("⚠️ Approaching Supabase Free Tier limit (20,000 rows)")
except Exception:
    st.sidebar.error("Could not fetch prospect count")

# === Form to Add New Prospect ===
st.sidebar.header("➕ Add New Prospect")
with st.sidebar.form("add_prospect"):
    first = st.text_input("First Name")
    last = st.text_input("Last Name")
    title = st.text_input("Title")
    company = st.text_input("Company")
    phone = st.text_input("Phone")
    email = st.text_input("Email")
    address = st.text_area("Address")
    website = st.text_input("Website")
    assigned_to = st.text_input("Assigned To (Email)")
    clients = st.multiselect("Assign to Client(s)", CLIENT_OPTIONS)
    notes = st.text_area("Notes")
    follow_up = st.date_input("Follow-Up Date", value=datetime.today() + timedelta(days=7))
    submitted = st.form_submit_button("Add Prospect")

    if submitted:
        data = {
            "first_name": first,
            "last_name": last,
            "title": title,
            "company": company,
            "phone": phone,
            "email": email,
            "address": address,
            "website": website,
            "assigned_to_email": assigned_to,
            "follow_up_date": follow_up.strftime("%Y-%m-%d"),
            "notes": notes,
            "clients": ",".join(clients)
        }
        try:
            resp = supabase.table("prospects").insert(data).execute()
            if getattr(resp, "data", None):
                st.success("Prospect added successfully!")
            else:
                err = getattr(resp, "error", None)
                st.error(f"Failed to add prospect. {err or 'No rows returned.'}")
        except Exception as e:
            st.error(f"Failed to add prospect: {e}")

# === Upload CSV ===
st.sidebar.header("📄 Upload Prospects CSV")
uploaded_file = st.sidebar.file_uploader("Choose a CSV file", type="csv")
if uploaded_file:
    df_upload = pd.read_csv(uploaded_file)
    if "follow_up_date" in df_upload.columns:
        df_upload["follow_up_date"] = pd.to_datetime(df_upload["follow_up_date"]).dt.strftime("%Y-%m-%d")
    if "notes" in df_upload.columns:
        df_upload.drop(columns=["notes"], inplace=True)
    df_upload = df_upload.where(pd.notnull(df_upload), None)
    try:
        resp = supabase.table("prospects").insert(df_upload.to_dict(orient="records")).execute()
        if getattr(resp, "data", None):
            st.success("CSV uploaded and processed successfully.")
        else:
            err = getattr(resp, "error", None)
            st.error(f"CSV upload failed. {err or 'No rows returned.'}")
    except Exception as e:
        st.error(f"CSV upload failed: {e}")

# === Load, Display, Edit, and Delete Prospects ===
try:
    data = supabase.table("prospects").select("*").execute()
    df = pd.DataFrame(getattr(data, "data", []) or [])
except Exception as e:
    st.error(f"Failed to load prospects: {e}")
    df = pd.DataFrame()

filter_clients = st.multiselect("Filter by Client", CLIENT_OPTIONS)
if not df.empty:
    df = df.sort_values(by="follow_up_date")

    if filter_clients:
        df = df[df["clients"].apply(lambda x: any(client in x for client in filter_clients if isinstance(x, str)))]

    if not df.empty:
        with st.expander("📋 View All Prospects", expanded=True):
            safe_cols = [c for c in df.columns if c != "id"]
            st.dataframe(df[safe_cols])

            selected = st.selectbox("Select a prospect to edit or delete", df["email"])
            row = df[df["email"] == selected].iloc[0]

            st.markdown("---")
            st.subheader("✏️ Edit Prospect")
            with st.form("edit_prospect"):
                new_first = st.text_input("First Name", row.get("first_name", ""))
                new_last = st.text_input("Last Name", row.get("last_name", ""))
                new_title = st.text_input("Title", row.get("title", ""))
                new_company = st.text_input("Company", row.get("company", ""))
                new_phone = st.text_input("Phone", row.get("phone", ""))
                new_email = st.text_input("Email", row.get("email", ""))
                new_address = st.text_area("Address", row.get("address", ""))
                new_website = st.text_input("Website", row.get("website", ""))
                new_assigned_to = st.text_input("Assigned To (Email)", row.get("assigned_to_email", ""))
                new_clients = st.multiselect(
                    "Assign to Client(s)",
                    CLIENT_OPTIONS,
                    row.get("clients", "").split(",") if row.get("clients") else []
                )
                st.text_area("Existing Notes", row.get("notes", ""), disabled=True)
                additional_notes = st.text_area("Notes (appended with date)", "")
                new_follow_up = st.date_input("Follow-Up Date", value=pd.to_datetime(row.get("follow_up_date")))
                updated = st.form_submit_button("Update Prospect")

                if updated:
                    old_notes = row.get("notes")
                    appended_notes = str(old_notes) if pd.notnull(old_notes) else ""
                    if additional_notes:
                        today_str = date.today().strftime("%Y-%m-%d")
                        appended_notes += f"\n[{today_str}] {additional_notes}"

                    update_data = {
                        "first_name": new_first,
                        "last_name": new_last,
                        "title": new_title,
                        "company": new_company,
                        "phone": new_phone,
                        "email": new_email,
                        "address": new_address,
                        "website": new_website,
                        "assigned_to_email": new_assigned_to,
                        "follow_up_date": new_follow_up.strftime("%Y-%m-%d"),
                        "clients": ",".join(new_clients),
                        "notes": appended_notes,
                    }

                    if "id" in row and pd.notnull(row["id"]):
                        try:
                            update_data["notes"] = str(update_data["notes"])
                            update_data["clients"] = ",".join(new_clients) if new_clients else ""
                            resp = supabase.table("prospects").update(update_data).eq("id", row["id"]).execute()
                            if getattr(resp, "data", None):
                                st.success("Prospect updated. Please reload the app to see changes.")

                                subject = f"Follow-Up Updated: {new_first} {new_last}"
                                body = f"The follow-up for {new_first} {new_last} at {new_company} has been updated to {new_follow_up}."
                                send_email(new_assigned_to, subject, body)
                            else:
                                err = getattr(resp, "error", None)
                                st.error(f"Failed to update prospect. {err or 'No rows returned.'}")
                        except Exception as e:
                            st.error(f"Failed to update prospect: {e}")
                    else:
                        st.error("Prospect ID not found. Cannot update.")

            if st.button("🗑️ Delete Prospect"):
                if "id" in row and row["id"]:
                    try:
                        resp = supabase.table("prospects").delete().eq("id", row["id"]).execute()
                        st.success("Prospect deleted. Please reload the app to see changes.")
                    except Exception as e:
                        st.error(f"Failed to delete prospect: {e}")
                else:
                    st.error("Prospect ID not found. Cannot delete.")
    else:
        st.info("No prospects match the selected client(s).")
else:
    st.info("No prospects found.")

# === Reminders (Overdue+Next 7d, Once/Day, Batched by Recipient) ===
from zoneinfo import ZoneInfo
from collections import defaultdict

REMINDER_WINDOW_DAYS = 7
today = datetime.now(ZoneInfo("America/New_York")).date()
window_end = today + timedelta(days=REMINDER_WINDOW_DAYS)

st.subheader("🔔 Follow-Ups: Overdue + Next 7 Days")

if not df.empty:
    # Normalize
    df["follow_up_date"] = pd.to_datetime(df["follow_up_date"], errors="coerce").dt.date
    if "last_reminded_on" not in df.columns:
        df["last_reminded_on"] = None
    else:
        df["last_reminded_on"] = pd.to_datetime(df["last_reminded_on"], errors="coerce").dt.date

    # Filter: overdue OR due within next 7 days
    due = df[df["follow_up_date"] <= window_end].copy()

    if not due.empty:
        # Show table (helpful for on-screen awareness)
        st.warning("These follow-ups are overdue or due within the next 7 days:")
        st.table(due[["first_name", "last_name", "company", "follow_up_date", "assigned_to_email"]])

        # Exclude anything already reminded today (once/day gate)
        due_needing_email = due[(due["last_reminded_on"] != today) | (due["last_reminded_on"].isna())].copy()

        # Group into digests by recipient
        batches = defaultdict(list)
        for _, r in due_needing_email.iterrows():
            recipient = (r.get("assigned_to_email") or "").strip()
            if recipient:
                status = "OVERDUE" if r["follow_up_date"] < today else f"Due {r['follow_up_date']}"
                line = f"- {r.get('first_name','')} {r.get('last_name','')} @ {r.get('company','')}  [{status}]"
                batches[recipient].append({"id": r.get("id"), "line": line})

        # Send one email per recipient, then mark all included records as reminded today
        for recipient, items in batches.items():
            if not items:
                continue
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

                # Mark all those records as reminded today (so we don't resend on pings)
                prospect_ids = [it["id"] for it in items if it["id"] is not None]
                if prospect_ids:
                    supabase.table("prospects").update(
                        {"last_reminded_on": today.isoformat()}
                    ).in_("id", prospect_ids).execute()

            except Exception as e:
                st.error(f"Failed to send digest to {recipient}: {e}")
    else:
        st.success("No due or overdue follow-ups within the next 7 days!")
else:
    st.info("No prospects found.")






