# === Streamlit CRM App for NSSA (Enhanced) ===
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta
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

st.set_page_config(page_title="NSSA CRM", layout="wide")
st.title("📇 NSSA Prospect CRM")

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
            "follow_up_date": str(follow_up),
            "assigned_to_email": assigned_to
        }
        response = supabase.table("prospects").insert(data).execute()
        if response.status_code == 201:
            st.success("Prospect added successfully!")
        else:
            st.error("Failed to add prospect. Please check your fields.")

# === Upload CSV ===
st.sidebar.header("📤 Upload Prospects CSV")
uploaded_file = st.sidebar.file_uploader("Choose a CSV file", type="csv")
if uploaded_file:
    df_upload = pd.read_csv(uploaded_file)
    if "follow_up_date" in df_upload.columns:
        df_upload["follow_up_date"] = pd.to_datetime(df_upload["follow_up_date"]).dt.date
    if "notes" in df_upload.columns:
        df_upload.drop(columns=["notes"], inplace=True)
    df_upload = df_upload.where(pd.notnull(df_upload), None)  # Replace NaNs with None for JSON compliance
    try:
        supabase.table("prospects").insert(df_upload.to_dict(orient="records")).execute()
        st.success("CSV uploaded and processed successfully.")
    except Exception as e:
        st.error(f"CSV upload failed: {e}")

# === Load and Display Prospects ===
with st.expander("📋 View All Prospects", expanded=True):
    data = supabase.table("prospects").select("*").execute()
    df = pd.DataFrame(data.data)
    if not df.empty:
        df = df.sort_values(by="follow_up_date")
        st.dataframe(df.drop(columns=["id"]))
    else:
        st.info("No prospects found.")

# === Reminders ===
today = datetime.today().date()
st.subheader("🔔 Follow-Ups Due Soon")
if not df.empty:
    df["follow_up_date"] = pd.to_datetime(df["follow_up_date"]).dt.date
    upcoming = df[df["follow_up_date"] <= today + timedelta(days=3)]
    if not upcoming.empty:
        st.warning("These follow-ups are due in the next 3 days:")
        st.table(upcoming[["first_name", "last_name", "company", "follow_up_date"]])

        for _, row in upcoming.iterrows():
            recipient = row.get("assigned_to_email")
            if recipient:
                subject = f"Follow-Up Reminder: {row['first_name']} {row['last_name']}"
                body = f"Reminder to follow up with {row['company']} on {row['follow_up_date']}"
                send_email(recipient, subject, body)
    else:
        st.success("No upcoming follow-ups!")

