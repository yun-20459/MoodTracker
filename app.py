import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta

# --- Configuration ---
SHEET_NAME = "MoodTrackerDB"
CREDENTIALS_FILE = "credentials.json"

# --- 1. Database Connection (Cached for performance) ---
# --- 1. Database Connection (Cloud Compatible) ---
@st.cache_resource
def get_worksheet():
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            gc = gspread.service_account_from_dict(creds_dict)
        else:
            gc = gspread.service_account(filename=CREDENTIALS_FILE)
            
        sh = gc.open(SHEET_NAME)
        return sh.sheet1
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

# --- 2. Logic: Alert System ---
def check_depression_alert(df):
    """
    Calculates weekly averages and returns a warning message if 
    current week's mood is lower than last week's.
    """
    if df.empty:
        return None

    # Convert 'Date' to datetime objects
    df['Date'] = pd.to_datetime(df['Date'])
    today = datetime.now()
    
    # Define time ranges
    current_week_start = today - timedelta(days=7)
    last_week_start = today - timedelta(days=14)

    # Filter data
    current_week_data = df[(df['Date'] > current_week_start) & (df['Date'] <= today)]
    last_week_data = df[(df['Date'] > last_week_start) & (df['Date'] <= current_week_start)]

    # Calculate averages
    curr_avg = current_week_data['Score'].mean()
    last_avg = last_week_data['Score'].mean()

    # Check logic (only if we have data for both periods)
    if pd.notna(curr_avg) and pd.notna(last_avg):
        if curr_avg < last_avg:
            return (
                f"⚠️ **Alert:** Your average score this week ({curr_avg:.1f}) "
                f"is lower than last week ({last_avg:.1f}). "
                "Please consider reaching out to someone or taking a break."
            )
    return None

# --- 3. UI & Main App ---
def main():
    st.set_page_config(page_title="Mood Tracker", page_icon="🧠")
    st.title("🌱 Mood Tracker")

    # Connect to DB
    sheet = get_worksheet()
    if not sheet:
        st.stop()

    # --- Input Form ---
    with st.form("entry_form"):
        date_val = st.date_input("Date", datetime.now())
        
        # Slider is easier for mobile touch
        score = st.slider("Mood Score (1-10)", min_value=1, max_value=10, value=5)
        
        tags_list = [
            "🩸 生理期/經前",   # Period / PMS
            "😴 沒睡好",       # Poor sleep
            "💊 忘記吃藥",     # Missed meds
            "🤕 身體不舒服",   # Physical discomfort
            "🤯 工作壓力",     # Work stress
            "👥 人際衝突",     # Interpersonal conflict
            "🌧️ 天氣不好",     # Bad weather
            "😰 莫名焦慮",     # Unexplained anxiety
            "😶 無動力/空虛"   # Apathy / Empty
        ]
        
        selected_tags = st.multiselect("Triggers / Tags", tags_list)
        note = st.text_area("One small thing (optional)", height=80)

        submitted = st.form_submit_button("💾 Save Entry")

    # --- Submission Handling ---
    if submitted:
        try:
            # Prepare data
            data = [
                str(date_val), 
                score, 
                ", ".join(selected_tags), 
                note
            ]
            
            # Save to Google Sheet
            sheet.append_row(data)
            st.success("✅ Saved! You're doing great.")
            
            # --- Alert Logic Trigger ---
            # Read all data back to analyze trends
            all_records = sheet.get_all_records()
            df = pd.DataFrame(all_records)
            
            # Show alert if necessary
            alert_msg = check_depression_alert(df)
            if alert_msg:
                st.error(alert_msg)
            
            # Optional: Show simple chart
            st.divider()
            st.caption("Recent Trend")
            if not df.empty:
                st.line_chart(df.set_index("Date")["Score"].tail(30))

        except Exception as e:
            st.error(f"Error saving data: {e}")

if __name__ == "__main__":
    main()