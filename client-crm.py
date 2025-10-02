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
from io import BytesIO

# ✅ Page config MUST be the first Streamlit call or favicon/logo can be ignored
st.set_page_config(page_title="Client Prospect CRM", page_icon="logo.png", layout="wide")

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
header_left, header_right = st.columns([3, 8])   # wider left column

def _find_logo():
    for p in ("assets/logo.png", "logo.png"):
        if os.path.exists(p):
            return p
    return None

with header_left:
    _logo = _find_logo()
    if _logo:
        st.image(_logo, width=220)
    else:
        st.caption("(logo not found: assets/logo.png or logo.png)")
with header_right:
    st.markdown("## Multi-Client Prospect Tracker")

CLIENT_OPTIONS = [
    "WOEMA", "SCAAP", "CTAAP", "NJAFP", "DAFP", "MAFP", "HAFP",
    "PAACP", "DEACP", "ACPNJ", "SEMPA", "WAPA", "NHCMA", "ASCIP", "NHCBA", "GBBA", "FCBA"
]

# Optional: sidebar logo
if _find_logo():
    st.sidebar.image(_find_logo(), use_container_width=True)

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

# === Function to Send Email (used for one-off updates, not reminders) ===
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
    
# === Admin-only Reminder Settings ===
if IS_ADMIN:
    st.sidebar.markdown("### ⏰ Reminder Settings")

    # fetch or initialize setting
    try:
        res = supabase.table("reminder_settings").select("frequency").eq("id", 1).single().execute()
        if res.data:
            current_freq = res.data.get("frequency", "daily")
        else:
            # auto-seed with default daily if missing
            supabase.table("reminder_settings").upsert({"id": 1, "frequency": "daily"}).execute()
            current_freq = "daily"
    except Exception:
        # if table missing or other error, default
        current_freq = "daily"

    freq_choice = st.sidebar.radio(
        "Email reminder frequency",
        options=["daily", "weekly", "off"],
        index=["daily", "weekly", "off"].index(current_freq),
        help="Choose how often automated reminders are sent"
    )

    if st.sidebar.button("Save Reminder Setting"):
        try:
            supabase.table("reminder_settings").upsert({"id": 1, "frequency": freq_choice}).execute()
            st.sidebar.success(f"Reminder frequency set to {freq_choice}")
        except Exception as e:
            st.sidebar.error(f"Failed to update: {e}")

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

# === Upload Prospects CSV ===
st.sidebar.header("📄 Upload Prospects CSV")

# Admin-only: downloadable blank CSV template (headers only)
if IS_ADMIN:
    template_cols = [
        "first_name",
        "last_name",
        "title",
        "company",
        "phone",
        "email",
        "address",
        "website",
        "assigned_to_email",
        "follow_up_date",   # YYYY-MM-DD (or leave blank)
        "clients"           # comma-separated, e.g. "WOEMA, SCAAP"
    ]
    # 0-row DataFrame → headers only
    template_df = pd.DataFrame(columns=template_cols)
    template_csv_bytes = template_df.to_csv(index=False).encode("utf-8")
    st.sidebar.download_button(
        "⬇️ Download CSV Template",
        data=template_csv_bytes,
        file_name="prospects_upload_template.csv",
        mime="text/csv",
        use_container_width=True,
    )

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

# === Load Prospects ===
try:
    data = supabase.table("prospects").select("*").execute()
    df = pd.DataFrame(getattr(data, "data", []) or [])
except Exception as e:
    st.error(f"Failed to load prospects: {e}")
    df = pd.DataFrame()

# === Filters (Client + Owner) & Export ===
client_choices = CLIENT_OPTIONS if IS_ADMIN else ALLOWED
filter_clients = st.multiselect(
    "Filter by Client",
    client_choices,
    default=([] if IS_ADMIN else ALLOWED),
)

# Base frame with non-admin restriction applied first
base_df = df.copy()
if not IS_ADMIN and not base_df.empty:
    # clients stored as comma-separated string; treat missing as ""
    base_df["clients"] = base_df["clients"].fillna("")
    base_df = base_df[base_df["clients"].apply(
        lambda x: any(c in [v.strip() for v in str(x).split(",")] for c in ALLOWED)
    )]

# Owner choices based on allowed rows
owner_choices = []
if not base_df.empty and "assigned_to_email" in base_df.columns:
    owner_choices = sorted(base_df["assigned_to_email"].dropna().unique().tolist())

filter_owners = st.multiselect(
    "Filter by Owner (assigned_to_email)",
    owner_choices,
    default=[],
)

# Build filtered frame used for BOTH display and export
df_filtered = base_df

# Apply client filter
if filter_clients:
    df_filtered = df_filtered.copy()
    df_filtered["clients"] = df_filtered["clients"].fillna("")
    df_filtered = df_filtered[df_filtered["clients"].apply(
        lambda x: any(c in [v.strip() for v in str(x).split(",")] for c in filter_clients)
    )]

# Apply owner filter
if filter_owners:
    df_filtered = df_filtered[df_filtered["assigned_to_email"].isin(filter_owners)]

# Sort by follow_up_date if present
if not df_filtered.empty and "follow_up_date" in df_filtered.columns:
    if not pd.api.types.is_datetime64_any_dtype(df_filtered["follow_up_date"]):
        df_filtered["follow_up_date"] = pd.to_datetime(df_filtered["follow_up_date"], errors="coerce")
    df_filtered = df_filtered.sort_values(by="follow_up_date", na_position="last")

# Export buttons
safe_cols = [c for c in df_filtered.columns if c != "id"]
export_df = df_filtered[safe_cols].copy()

st.markdown("#### ⬇️ Export filtered prospects")
col_csv, col_xlsx = st.columns(2)

csv_bytes = export_df.to_csv(index=False).encode("utf-8")
col_csv.download_button(
    "Download CSV",
    data=csv_bytes,
    file_name="prospects_filtered.csv",
    mime="text/csv",
    use_container_width=True,
)

xlsx_buffer = BytesIO()
with pd.ExcelWriter(xlsx_buffer) as writer:
    export_df.to_excel(writer, index=False, sheet_name="Prospects")
xlsx_buffer.seek(0)
col_xlsx.download_button(
    "Download Excel (.xlsx)",
    data=xlsx_buffer,
    file_name="prospects_filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

# === Display, Search, Edit, Delete using the filtered frame ===
def _label_from_row(r):
    fn = (r.get("first_name") or "").strip()
    ln = (r.get("last_name") or "").strip()
    comp = (r.get("company") or "").strip()
    nm = f"{fn} {ln}".strip() or "(no name)"
    return f"{nm} — {comp}" if comp else nm

if not df_filtered.empty:
    with st.expander("📋 View Prospects", expanded=True):
        # ---- Search box filters view by first/last/company ----
        search = st.text_input("Search name or company")
        df_view = df_filtered.copy()
        if search:
            s = search.strip().lower()
            # Coerce missing cols
            for c in ["first_name", "last_name", "company"]:
                if c not in df_view.columns:
                    df_view[c] = ""
            df_view = df_view[df_view[["first_name", "last_name", "company"]]
                              .astype(str).apply(lambda r: any(s in v.lower() for v in r), axis=1)]
        st.dataframe(export_df if df_view is df_filtered else df_view[[c for c in export_df.columns if c in df_view.columns]])

        # ---- Build compact selection list (labels -> id) ----
        options = []
        if "id" in df_view.columns:
            for _, rr in df_view.iterrows():
                if pd.notnull(rr.get("id")):
                    options.append((_label_from_row(rr), rr["id"]))

        # Sticky selection by ID (order-safe)
        label_by_id = { _id: lbl for (lbl, _id) in options }
        ids = list(label_by_id.keys())

        current_id = st.session_state.get("selected_id")
        if current_id not in label_by_id and ids:
            current_id = ids[0]

        if ids:
            selected_id = st.selectbox(
                "Select a prospect",
                options=ids,
                index=(ids.index(current_id) if current_id in ids else 0),
                format_func=lambda _id: label_by_id.get(_id, f"ID {_id}"),
                key="selected_id",
            )
            row = df_view[df_view["id"] == selected_id].iloc[0]
        else:
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

                existing_clients = row.get("clients", "")
                existing_list = [v.strip() for v in existing_clients.split(",")] if existing_clients else []
                preselected = [c for c in existing_list if (IS_ADMIN or c in ALLOWED)]
                new_clients = st.multiselect(
                    "Assign to Client(s)",
                    CLIENT_OPTIONS if IS_ADMIN else ALLOWED,
                    preselected,
                )

                st.text_area("Existing Notes", row.get("notes", ""), disabled=True)
                additional_notes = st.text_area("Notes (appended with date)", "")

                # ---- No follow-up date toggle ----
                raw_fu = row.get("follow_up_date")
                has_no_date = pd.isna(raw_fu) or str(raw_fu).strip() in ("", "None", "NaT")
                no_fu = st.checkbox("No follow-up date", value=has_no_date)
                if no_fu:
                    fu_input = None
                else:
                    fu_val = pd.to_datetime(raw_fu, errors="coerce")
                    fu_val = fu_val.date() if pd.notnull(fu_val) else datetime.today().date()
                    fu_input = st.date_input("Follow-Up Date", value=fu_val)

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
                        "follow_up_date": (None if no_fu else fu_input.strftime("%Y-%m-%d")),
                        "clients": ",".join(safe_new_clients),
                        "notes": appended_notes,
                    }

                    if "id" in row and pd.notnull(row["id"]):
                        try:
                            update_data["notes"] = str(update_data["notes"])
                            resp = supabase.table("prospects").update(update_data).eq("id", row["id"]).execute()
                            if getattr(resp, "data", None):
                                st.success("Prospect updated.")
                                subject = f"Follow-Up Updated: {new_first} {new_last}"
                                body = f"The follow-up for {new_first} {new_last} at {new_company} has been updated to {(fu_input if fu_input else 'No Date')}."
                                if new_assigned_to:
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
                        st.success("Prospect deleted. You may need to reload to see it removed from the list.")
                    except Exception as e:
                        st.error(f"Failed to delete prospect: {e}")
                else:
                    st.error("Prospect ID not found. Cannot delete.")
else:
    st.info("No prospects match the selected filters.")

# === Reminders UI ONLY (no email / no DB writes) ===
# Shows overdue + next 7 days for visibility inside the app; sending is handled by the scheduled script.
REMINDER_WINDOW_DAYS = 7
_today = datetime.now(ZoneInfo("America/New_York")).date()
window_end = _today + timedelta(days=REMINDER_WINDOW_DAYS)

st.subheader("🔔 Follow-Ups: Overdue + Next 7 Days (UI only)")

if not df.empty:
    df_rem = df.copy()
    df_rem["follow_up_date"] = pd.to_datetime(df_rem["follow_up_date"], errors="coerce").dt.date
    due = df_rem[df_rem["follow_up_date"] <= window_end].copy()

    if not due.empty:
        # Add a simple status column for readability
        due["status"] = due["follow_up_date"].apply(lambda d: "OVERDUE" if d < _today else f"Due {d}")
        st.table(due[["first_name", "last_name", "company", "follow_up_date", "status", "assigned_to_email"]])
        st.info("Email reminders are sent by the scheduled job only. No emails are sent from this UI.")
    else:
        st.success("No due or overdue follow-ups within the next 7 days!")
else:
    st.info("No prospects found.")










