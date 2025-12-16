import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# --- Configuration ---
SHEET_NAME = "MoodTrackerDB"
# BSRS-5 Score Interpretation
# 0-5: Normal / 6-9: Mild / 10-14: Moderate / 15+: Severe

# --- 1. Database Connection ---
@st.cache_resource
def get_worksheet():
    """
    Connects to Google Sheets using Streamlit Secrets (Cloud) 
    or local credentials.json (Local Testing).
    """
    try:
        if "gcp_service_account" in st.secrets:
            creds_dict = st.secrets["gcp_service_account"]
            gc = gspread.service_account_from_dict(creds_dict)
        else:
            gc = gspread.service_account(filename="credentials.json")
        return gc.open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"DB Connection Error: {e}")
        return None

# --- 2. Analytics Functions ---
def analyze_data(df):
    """Prepares dataframe for analysis."""
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by='Date')
    return df

def get_weekly_comparison(df):
    """
    Calculates average scores for the current week (last 7 days)
    and the previous week.
    """
    today = datetime.now()
    current_week_start = today - timedelta(days=7)
    last_week_start = today - timedelta(days=14)

    # Filter data
    curr_df = df[(df['Date'] > current_week_start) & (df['Date'] <= today)]
    last_df = df[(df['Date'] > last_week_start) & (df['Date'] <= current_week_start)]

    # Calculate means
    curr_avg = curr_df['Score'].mean()
    last_avg = last_df['Score'].mean()
    
    return curr_avg, last_avg

def get_tag_correlations(df):
    """
    Analyzes which tags are associated with HIGHER scores (worse mood).
    Returns a dataframe sorted by mean score descending.
    """
    # Filter out empty tags and copy
    tag_df = df[df['Tags'] != ""].copy()
    
    # Split comma-separated tags into individual rows
    tag_df['Tags'] = tag_df['Tags'].astype(str).str.split(', ')
    tag_df = tag_df.explode('Tags')
    
    if tag_df.empty:
        return pd.DataFrame()
        
    # Group by Tag
    stats = tag_df.groupby('Tags')['Score'].agg(['mean', 'count']).reset_index()
    # Sort: Higher mean score = Worse impact (for BSRS-5)
    stats = stats.sort_values(by='mean', ascending=False)
    return stats

# --- 3. Main Application ---
def main():
    # Page setup
    st.set_page_config(page_title="Mood Tracker", page_icon="🧠", layout="centered")
    
    # CSS to hide Streamlit UI elements for a cleaner "App-like" experience
    hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .stApp {padding-top: 10px;} 
            </style>
            """
    st.markdown(hide_st_style, unsafe_allow_html=True)

    st.title("🌱 Mood Tracker")

    # Connect DB
    sheet = get_worksheet()
    if not sheet:
        st.stop()

    # --- UI: Tabs Layout ---
    tab1, tab2 = st.tabs(["📝 Check-in", "📊 Insights"])

    # === TAB 1: Data Entry ===
    with tab1:
        with st.form("bsrs5_form"):
            st.caption("How have you been feeling in the past week (including today)?")
            date_val = st.date_input("Date", datetime.now())
            
            st.divider()
            
            # Define BSRS-5 Options (Text -> Score)
            options_map = {
                "0: None": 0,
                "1: Mild": 1,
                "2: Moderate": 2,
                "3: Severe": 3,
                "4: Very Severe": 4
            }
            opts = list(options_map.keys())

            # BSRS-5 Questions
            st.markdown("##### 1. Trouble falling asleep / staying asleep")
            a1 = st.select_slider("Sleep", options=opts, label_visibility="collapsed")
            
            st.markdown("##### 2. Feeling tense or keyed up")
            a2 = st.select_slider("Tension", options=opts, label_visibility="collapsed")
            
            st.markdown("##### 3. Easily annoyed or irritated")
            a3 = st.select_slider("Irritation", options=opts, label_visibility="collapsed")
            
            st.markdown("##### 4. Feeling blue or sad")
            a4 = st.select_slider("Depression", options=opts, label_visibility="collapsed")
            
            st.markdown("##### 5. Feeling inferior to others")
            a5 = st.select_slider("Inferiority", options=opts, label_visibility="collapsed")

            # Calculate total score
            total_score = (options_map[a1] + options_map[a2] + options_map[a3] + 
                           options_map[a4] + options_map[a5])

            # Immediate Feedback based on score
            st.markdown(f"**Today's Score: {total_score} / 20**")
            
            if total_score >= 15:
                st.error("Status: Severe. Please consider professional help. 🌧️")
            elif total_score >= 10:
                st.warning("Status: Moderate. Be gentle with yourself. ☁️")
            elif total_score >= 6:
                st.info("Status: Mild. Try to relax. 🌱")
            else:
                st.success("Status: Good. Keep it up! ☀️")

            st.divider()

            # Tags & Note
            tags_list = [
                "🩸 Period/PMS", "😴 Poor Sleep", "💊 Missed Meds", 
                "🤕 Sick/Pain", "🤯 Work Stress", "👥 Conflict", 
                "🌧️ Bad Weather", "😰 Anxiety", "😶 Apathy",
                "🏃 Exercise", "🎮 Relax/Gaming", "🥰 Socializing"
            ]
            selected_tags = st.multiselect("Context / Tags", tags_list)
            note = st.text_area("Daily Note (Optional)", height=80)

            submitted = st.form_submit_button("💾 Save Entry", use_container_width=True)

        # Handling Submission
        if submitted:
            try:
                data = [str(date_val), total_score, ", ".join(selected_tags), note]
                sheet.append_row(data)
                st.success("Entry saved successfully.")
                st.cache_data.clear() # Clear cache to refresh charts
            except Exception as e:
                st.error(f"Error saving data: {e}")

        # === Instant Trend Feedback (Pre-warning) ===
        # This runs every time the app reloads to show current status
        raw_data = sheet.get_all_records()
        if raw_data:
            df = analyze_data(pd.DataFrame(raw_data))
            curr_avg, last_avg = get_weekly_comparison(df)
            
            if pd.notna(curr_avg) and pd.notna(last_avg):
                delta = curr_avg - last_avg
                
                st.divider()
                st.caption("Weekly Trend (Lower score is better)")
                col1, col2 = st.columns(2)
                
                with col1:
                    # delta_color="inverse": Red if score increases (worse), Green if decreases (better)
                    st.metric(
                        label="This Week Avg", 
                        value=f"{curr_avg:.1f}", 
                        delta=f"{delta:.1f}",
                        delta_color="inverse" 
                    )
                
                with col2:
                    # Alert Logic: If Avg increases AND Avg > 5 (Filtering out minor fluctuations)
                    if curr_avg > last_avg and curr_avg > 5:
                        st.error("📉 Stress Rising")
                    elif curr_avg <= last_avg:
                        st.success("📈 Stable/Improving")

    # === TAB 2: Analysis & Insights ===
    with tab2:
        if raw_data:
            df = analyze_data(pd.DataFrame(raw_data))
            
            st.subheader("Mood Trend")
            # Interactive Chart
            fig = px.line(df, x="Date", y="Score", markers=True, 
                          hover_data=["Tags", "Note"], title="BSRS-5 Score Over Time")
            fig.update_traces(line_color='#FF6C6C') # Reddish color for alerts
            # Y-axis 0-21 (since max score is 20)
            fig.update_layout(yaxis_range=[0, 21]) 
            st.plotly_chart(fig, use_container_width=True)

            st.divider()

            # Correlation Analysis
            st.subheader("⚠️ Top Triggers")
            st.caption("Tags associated with higher scores (worse mood)")
            
            tag_stats = get_tag_correlations(df)
            
            if not tag_stats.empty:
                st.dataframe(
                    tag_stats.head(5).style.format({"mean": "{:.1f}"}),
                    column_config={
                        "Tags": "Trigger",
                        "mean": "Avg Score",
                        "count": "Freq"
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Not enough tag data yet.")
        else:
            st.info("No data available yet. Go to 'Check-in' to add your first entry!")

if __name__ == "__main__":
    main()