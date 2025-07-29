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
        response = supabase.table("prospects").insert(data).execute()
        if response.status_code == 201:
            st.success("Prospect added successfully!")
        else:
            st.error("Failed to add prospect. Please check your fields.")

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
        supabase.table("prospects").insert(df_upload.to_dict(orient="records")).execute()
        st.success("CSV uploaded and processed successfully.")
    except Exception as e:
        st.error(f"CSV upload failed: {e}")

# === Load, Display, Edit, and Delete Prospects ===
with st.expander("📋 View All Prospects", expanded=True):
    data = supabase.table("prospects").select("*").execute()
    df = pd.DataFrame(data.data)
    if not df.empty:
        df = df.sort_values(by="follow_up_date")

        filter_clients = st.multiselect("Filter by Client", CLIENT_OPTIONS)
        if filter_clients:
            df = df[df["clients"].apply(lambda x: any(client in x for client in filter_clients if isinstance(x, str)))]

        st.dataframe(df.drop(columns=["id"]))

        selected = st.selectbox("Select a prospect to edit or delete", df["email"])
        row = df[df["email"] == selected].iloc[0]

        st.markdown("---")
        st.subheader("✏️ Edit Prospect")
        with st.form("edit_prospect"):
            new_first = st.text_input("First Name", row["first_name"])
            new_last = st.text_input("Last Name", row["last_name"])
            new_title = st.text_input("Title", row["title"])
            new_company = st.text_input("Company", row["company"])
            new_phone = st.text_input("Phone", row["phone"])
            new_email = st.text_input("Email", row["email"])
            new_address = st.text_area("Address", row["address"])
            new_website = st.text_input("Website", row["website"])
            new_assigned_to = st.text_input("Assigned To (Email)", row["assigned_to_email"])
            new_clients = st.multiselect("Assign to Client(s)", CLIENT_OPTIONS, row.get("clients", "").split(",") if row.get("clients") else [])
            st.text_area("Existing Notes", row.get("notes", ""), disabled=True)
            additional_notes = st.text_area("Notes (appended with date)", "")
            new_follow_up = st.date_input("Follow-Up Date", value=pd.to_datetime(row["follow_up_date"]))
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
                    "notes": appended_notes
                }

                if "id" in row and pd.notnull(row["id"]):
                    try:
                        update_data["notes"] = str(update_data["notes"])
                        update_data["clients"] = ",".join(new_clients) if new_clients else ""
                        supabase.table("prospects").update(update_data).eq("id", row["id"]).execute()
                        st.success("Prospect updated. Please reload the app to see changes.")

                        subject = f"Follow-Up Updated: {new_first} {new_last}"
                        body = f"The follow-up for {new_first} {new_last} at {new_company} has been updated to {new_follow_up}."
                        send_email(new_assigned_to, subject, body)
                    except Exception as e:
                        st.error(f"Failed to update prospect: {e}")
                else:
                    st.error("Prospect ID not found. Cannot update.")

        if st.button("🗑️ Delete Prospect"):
            if "id" in row and row["id"]:
                supabase.table("prospects").delete().eq("id", row["id"]).execute()
                st.success("Prospect deleted. Please reload the app to see changes.")
            else:
                st.error("Prospect ID not found. Cannot delete.")
    else:
        st.info("No prospects found.")

# === Reminders ===
today = datetime.today().date()
st.subheader("🔔 Follow-Ups Due Soon")
if not df.empty:
    df["follow_up_date"] = pd.to_datetime(df["follow_up_date"]).dt.date
    upcoming = df[df["follow_up_date"] <= today + timedelta(days=5)]
    if not upcoming.empty:
        st.warning("These follow-ups are due in the next 5 days:")
        st.table(upcoming[["first_name", "last_name", "company", "follow_up_date"]])

        for _, row in upcoming.iterrows():
            recipient = row.get("assigned_to_email")
            if recipient:
                subject = f"Follow-Up Reminder: {row['first_name']} {row['last_name']}"
                body = f"Reminder to follow up with {row['company']} on {row['follow_up_date']}"
                send_email(recipient, subject, body)
    else:
        st.success("No upcoming follow-ups!")
