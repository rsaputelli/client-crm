# === Streamlit CRM App for NSSA (Prototype) ===
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta

# === CONFIGURATION ===
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# === Initialize Supabase ===
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

st.set_page_config(page_title="NSSA CRM", layout="wide")
st.title("📇 NSSA Prospect CRM")

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
            "notes": notes,
            "follow_up_date": str(follow_up)
        }
        response = supabase.table("prospects").insert(data).execute()
        if response.status_code == 201:
            st.success("Prospect added successfully!")
        else:
            st.error("Failed to add prospect. Please check your fields.")

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
    else:
        st.success("No upcoming follow-ups!")
