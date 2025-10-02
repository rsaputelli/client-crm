[README_CRM_Reminders.md](https://github.com/user-attachments/files/22670067/README_CRM_Reminders.md)
# Client Prospect CRM — Reminder System Guide

This document explains how reminder emails are configured, scheduled, and controlled from the Streamlit app and GitHub Actions.

---

## Overview

- **Streamlit app (`client-crm_STICKY_ID_FIXED_UI_ONLY.py`)**
  - Shows a **UI-only** table of follow‑ups (overdue + next 7 days).
  - Contains an **Admin‑only “Reminder Settings”** control in the sidebar to set `daily`, `weekly`, or `off`.
  - Does **not** send reminder emails on page load (prevents duplicate sends).

- **Supabase**
  - Stores prospects (`prospects` table) and the global reminder frequency in `reminder_settings` (single row with `id = 1`).
  - The job updates `prospects.last_reminded_on` after sending to suppress duplicates during the same day.

- **GitHub Actions (scheduled job)**
  - Runs `send_reminders.py` on a schedule (daily cron).
  - Reads `reminder_settings.frequency` to determine whether to send today.
  - Sends **one digest per owner** (grouped by `assigned_to_email`).
  - Updates `last_reminded_on` for included prospects.

---

## Data Model

**Table: `prospects` (relevant columns)**
- `id` (primary key)
- `first_name`, `last_name`, `company`
- `assigned_to_email` (recipient for reminders)
- `follow_up_date` (date)
- `last_reminded_on` (date; used as daily suppression)

**Table: `reminder_settings`**
```
create table if not exists reminder_settings (
  id int primary key,
  frequency text not null check (frequency in ('daily','weekly','off'))
);

insert into reminder_settings (id, frequency)
values (1, 'daily')
on conflict (id) do nothing;
```
- Single row (`id = 1`), with `frequency` set by admin in the app.
- App auto‑seeds the row if missing.

---

## Admin UI (inside Streamlit)

- Sidebar section **“⏰ Reminder Settings”** visible **only** to admins (`IS_ADMIN`).
- Options: `daily`, `weekly`, `off`.
- Uses `upsert({"id": 1, "frequency": <choice>})` to store the setting.
- If the row is missing, the app auto‑creates it with `daily` as default.

> Location: placed **after login/access checks** and **before “Add New Prospect”** in the sidebar.

---

## Scheduled Job (GitHub Actions)

**Workflow file:** `.github/workflows/reminders.yml`

Example:
```
name: Send CRM Reminders

on:
  workflow_dispatch:   # Manual run button
  schedule:
    - cron: "0 13 * * *"  # 13:00 UTC (9AM ET during DST)

jobs:
  reminders:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - name: Run reminder script
        run: python send_reminders.py
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          EMAIL_HOST: ${{ secrets.EMAIL_HOST }}
          EMAIL_PORT: ${{ secrets.EMAIL_PORT }}
          EMAIL_USER: ${{ secrets.EMAIL_USER }}
          EMAIL_PASSWORD: ${{ secrets.EMAIL_PASSWORD }}
```
> **DST Tip:** If you want a fixed local time (e.g., 9am New York), run hourly and add a local‑hour gate in `send_reminders.py`.

---

## `send_reminders.py` (key points)

- Uses the **service role** key to bypass RLS for server‑side job:
  ```python
  SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"]
  ```
- Reads frequency from `reminder_settings`:
  ```python
  res = supabase.table("reminder_settings").select("frequency").single().execute()
  frequency = (res.data or {}).get("frequency", "daily")
  if frequency == "off": sys.exit(0)
  if frequency == "weekly" and datetime.today().weekday() != 0: sys.exit(0)  # Monday only
  ```
- Selects due items: `follow_up_date <= today + 7 days`.
- Skips any with `last_reminded_on = today` (daily suppression).
- Groups by `assigned_to_email` and sends one digest per recipient.
- Updates `last_reminded_on` for included IDs.

**Dependencies (`requirements.txt`):**
```
pandas
supabase
python-dateutil
```
(Standard libs used: `smtplib`, `email`, `zoneinfo`, `ssl`, `socket`, etc.)

---

## SMTP Configuration (Office 365 example)

- Host: `smtp.office365.com`
- Port: `587` (STARTTLS)
- User: full UPN (e.g., `user@domain.com`)
- Password: 
  - If MFA enabled → **App Password** (not interactive password)
  - Ensure **SMTP AUTH** is enabled for the mailbox in Exchange Admin
- Secrets must be set **without quotes** in GitHub (`Settings → Secrets and variables → Actions`).

---

## How Emails Are Selected and Sent

1. **Window:** prospects with `follow_up_date <= today + 7 days`.
2. **Suppression:** exclude rows with `last_reminded_on = today`.
3. **Recipient:** use `assigned_to_email` (non‑empty).
4. **Digest content:** lines of `First Last @ Company  [OVERDUE or Due YYYY-MM-DD]`.
5. **After send:** set `last_reminded_on = today` for included records.

---

## Testing & Verification

- In the Streamlit app, the **Follow‑Ups (UI only)** table should show due items.
- To force a test send for one record:
  ```sql
  update prospects
  set last_reminded_on = null, follow_up_date = current_date
  where id = <your_id>;
  ```
- Trigger the workflow manually (`Actions → Send CRM Reminders → Run workflow`).
- Check logs: “Sent digest to …” and row’s `last_reminded_on` should update.

---

## Troubleshooting

- **No prospects found.**  
  Use the **service role** key; otherwise RLS may hide all rows from the job.

- **DNS error (host not found).**  
  Correct `EMAIL_HOST` or ensure the provider is publicly reachable from GitHub runners.

- **535 Authentication unsuccessful (Office 365).**  
  Enable SMTP AUTH for the mailbox; use App Password if MFA; correct UPN; port 587 STARTTLS.

- **No email but table shows due items.**  
  Check `assigned_to_email` is present, and `last_reminded_on` isn’t already today.

- **Double emails.**  
  Ensure the Streamlit app’s reminder‑sending code is **removed**; UI table only.

---

## Security Notes

- **Never** expose the service role key in client-side code or public repos.
- Keep all SMTP and Supabase credentials in **GitHub Actions secrets**.
- Limit who can edit reminder settings by enforcing `IS_ADMIN` in the Streamlit app.

---

## Change Log (suggested)

- `v1`: Streamlit app sent reminders on load.
- `v2`: Moved to scheduled job; UI shows follow‑ups only.
- `v3`: Added Admin UI for frequency; job reads `reminder_settings`.
- `v4`: Service role key + diagnostics logging + Office365 SMTP guidance.
