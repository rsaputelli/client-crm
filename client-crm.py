# === Streamlit CRM App for Multi-Client Tracking (RLS-aware UI) ===
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta, date
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from zoneinfo import ZoneInfo
from collections import defaultdict
import os

# ✅ Page config MUST be the first Streamlit call or favicon/logo can be ignored
st.set_page_config(page_title="Client Prospect CRM", page_icon="assets/logo.png", layout="wide")

# === CONFIGURATION ===
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]  # anon key is fine for app init; auth will attach user JWT after sign-in
EMAIL_HOST = st.secrets["EMAIL_HOST"]
EMAIL_PORT = st.secrets["EMAIL_PORT"]
EMAIL_USER = st.secrets["EMAIL_USER"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 🔐 Restore Supabase session across Streamlit reruns (prevents logout on UI interactions)
if "sb_session" in st.session_state and st.session_state["sb_session"]:
    try:
        supabase.auth.set_session(
            st.session_state["sb_session"].get("access_token"),
            st.session_state["sb_session"].get("refresh_token"),
        )
    except Exception:
        # If token expired/invalid, user can sign in again
        pass

# === Branding header ===
header_left, header_right = st.columns([1, 8])
with header_left:
    logo_path = "assets/logo.png"
    if os.path.exists(logo_path):
        st.image(logo_path, width=56)
    else:
        st.caption("(logo missing: assets/logo.png)")
with header_right:
    st.markdown("## Multi-Client Prospect Tracker")

CLIENT_OPTIONS = [
    "WOEMA", "SCAAP", "CTAAP", "NJAFP", "DAFP", "MAFP", "HAFP",
    "PAACP", "DEACP", "ACPNJ", "NSSA", "SEMPA", "WAPA"
]

# Optional: sidebar logo
if os.path.exists("assets/logo.png"):
    st.sidebar.image("assets/logo.png", use_column_width=True)

# === Auth UI (required for RLS to identify users) ===
st.sidebar.markdown("### 🔐 Sign in")
email_login = st.sidebar.text_input("Email", key="login_email")
password_login = st.sidebar.text_input("Password", type="password", key="login_pw")
col_a, col_b = st.sidebar.columns(2)
if col_a.button("Sign in"):
    try:
        auth_res = supabase.auth.sign_in_with_password({"email": email_login, "password": password_login})
        sess = getattr(auth_res, "session", None) or auth_res
        # Save tokens so auth survives Streamlit reruns
        st.session_state["sb_session"] = {
            "access_token": getattr(sess, "access_token", None),
            "refresh_token": getattr(sess, "refresh_token", None),
        }
        st.session_state["session"] = sess
        st.success("Signed in.")
        st.rerun()
    except Exception as e:
        st.error(f"Sign-in failed: {e}")
if col_b.button("Sign out"):
    try:
        supabase.auth.sign_out()
    except Exception:
        pass
    st.session_state.pop("session", None)
    st.session_state.pop("sb_session", None)
    st.rerun()

# Helper to get current user email from session

def _current_user_email():
    try:
        sess_res = supabase.auth.get_session()
        session = getattr(sess_res, "session", None) or sess_res
        user = getattr(session, "user", None) if session else None
        email = getattr(user, "email", None)
        if email:
            return email
        # Fallback
        got = supabase.auth.get_user()
        return getattr(getattr(got, "user", None), "email", None)
    except Exception:
        return None

# ---- Access helpers (UI convenience; RLS is the real gate) ----

def get_user_access():
    """Return dict(email, allowed_clients, is_admin). Requires authenticated session."""
    email = _current_user_email()
    if not email:
        return {"email": None, "allowed_clients": [], "is_admin": False}
    try:
        # Use ilike for case-insensitive email match
        ua = (
            supabase.table("user_access")
            .select("allowed_clients,is_admin")
            .ilike("email", email)
            .single()
            .execute()
        )
        row = getattr(ua, "data", None) or {}
    except Exception:
        row = {}
    allowed = row.get("allowed_clients") or []
    is_admin = bool(row.get("is_admin", False))
    if is_admin:
        allowed = CLIENT_OPTIONS
    return {"email": email, "allowed_clients": allowed, "is_admin": is_admin}

# Block app if not signed in (so UI mirrors RLS)
access = get_user_access()
USER_EMAIL = access["email"]
ALLOWED = access["allowed_clients"]
IS_ADMIN = access["is_admin"]
if USER_EMAIL is None:
    st.warning("Please sign in to view and manage prospects.")
    st.stop()

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
clients_choices_for_user = CLIENT_OPTIONS if IS_ADMIN else ALLOWED
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
    clients = st.multiselect("Assign to Client(s)", clients_choices_for_user)
    notes = st.text_area("Notes")
    follow_up = st.date_input("Follow-Up Date", value=datetime.today() + timedelta(days=7))
    submitted = st.form_submit_button("Add Prospect")

    if submitted:
        safe_clients = clients if IS_ADMIN else [c for c in clients if c in ALLOWED]
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
            "clients": ",".join(safe_clients),
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

    # Sanitize client assignments for non-admins
    if not IS_ADMIN and "clients" in df_upload.columns:
        df_upload["clients"] = df_upload["clients"].fillna("")
        df_upload["clients"] = df_upload["clients"].apply(
            lambda s: ",".join([c for c in str(s).split(',') if c in ALLOWED])
        )

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

# UI filter choices limited by role
client_choices = CLIENT_OPTIONS if IS_ADMIN else ALLOWED
filter_clients = st.multiselect(
    "Filter by Client",
    client_choices,
    default=([] if IS_ADMIN else ALLOWED),
)

if not df.empty:
    # Hard-limit non-admin view to allowed clients (belt-and-suspenders; RLS should also enforce)
    if not IS_ADMIN:
        df = df[df["clients"].apply(lambda x: any(c in x for c in ALLOWED) if isinstance(x, str) else False)]

    # Apply selected filter
    if filter_clients:
        df = df[df["clients"].apply(lambda x: any(client in x for client in filter_clients) if isinstance(x, str) else False)]

    if not df.empty:
        df = df.sort_values(by="follow_up_date")
        with st.expander("📋 View All Prospects", expanded=True):
            safe_cols = [c for c in df.columns if c != "id"]
            st.dataframe(df[safe_cols])

            # Protect against empty selection list
            try:
                selected = st.selectbox("Select a prospect to edit or delete", df["email"])
                row = df[df["email"] == selected].iloc[0]
            except Exception:
                st.info("No selectable rows.")
                row = None

            if row is not None:
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

                    existing_clients = row.get("clients", "").split(",") if row.get("clients") else []
                    preselected = [c for c in existing_clients if (IS_ADMIN or c in ALLOWED)]
                    new_clients = st.multiselect(
                        "Assign to Client(s)",
                        CLIENT_OPTIONS if IS_ADMIN else ALLOWED,
                        preselected,
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
                            appended_notes += f"[{today_str}] {additional_notes}"

                        safe_new_clients = new_clients if IS_ADMIN else [c for c in new_clients if c in ALLOWED]
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
                            "clients": ",".join(safe_new_clients),
                            "notes": appended_notes,
                        }

                        if "id" in row and pd.notnull(row["id"]):
                            try:
                                update_data["notes"] = str(update_data["notes"])
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
                    if row is not None and "id" in row and row["id"]:
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
REMINDER_WINDOW_DAYS = 7
_today = datetime.now(ZoneInfo("America/New_York")).date()
window_end = _today + timedelta(days=REMINDER_WINDOW_DAYS)

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
        st.warning("These follow-ups are overdue or due within the next 7 days:")
        st.table(due[["first_name", "last_name", "company", "follow_up_date", "assigned_to_email"]])

        # Exclude anything already reminded today (once/day gate)
        due_needing_email = due[(due["last_reminded_on"] != _today) | (due["last_reminded_on"].isna())].copy()

        # Group into digests by recipient
        batches = defaultdict(list)
        for _, r in due_needing_email.iterrows():
            recipient = (r.get("assigned_to_email") or "").strip()
            if recipient:
                status = "OVERDUE" if r["follow_up_date"] < _today else f"Due {r['follow_up_date']}"
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
                        {"last_reminded_on": _today.isoformat()}
                    ).in_("id", prospect_ids).execute()

            except Exception as e:
                st.error(f"Failed to send digest to {recipient}: {e}")
    else:
        st.success("No due or overdue follow-ups within the next 7 days!")
else:
    st.info("No prospects found.")















