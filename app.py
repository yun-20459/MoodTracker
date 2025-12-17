import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from streamlit_oauth import OAuth2Component # New: OAuth library
import os

# --- Configuration ---
SHEET_NAME = "MoodTrackerDB"
# Google OAuth Settings
AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_TOKEN_URL = "https://oauth2.googleapis.com/revoke"
USER_INFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
SCOPE = "openid email profile"

# --- 1. Database Connection ---
@st.cache_resource
def get_worksheet():
    """Connect to Google Sheets."""
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

# --- 2. Analytics Functions (Updated for User Filter) ---
def analyze_user_data(df, user_email):
    """Filter data for the specific user and sort."""
    # Filter by Email
    df = df[df['User_Email'] == user_email].copy()
    
    if df.empty:
        return df
        
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(by='Date')
    return df

def get_weekly_comparison(df):
    """Calculates weekly stats (unchanged logic)."""
    if df.empty:
        return None, None
        
    today = datetime.now()
    current_week_start = today - timedelta(days=7)
    last_week_start = today - timedelta(days=14)

    curr_df = df[(df['Date'] > current_week_start) & (df['Date'] <= today)]
    last_df = df[(df['Date'] > last_week_start) & (df['Date'] <= current_week_start)]

    curr_avg = curr_df['Score'].mean()
    last_avg = last_df['Score'].mean()
    
    return curr_avg, last_avg

# ... (get_tag_correlations function keeps same logic, just pass filtered df) ...
def get_tag_correlations(df):
    """Analyzes tags."""
    tag_df = df[df['Tags'] != ""].copy()
    tag_df['Tags'] = tag_df['Tags'].astype(str).str.split(', ')
    tag_df = tag_df.explode('Tags')
    if tag_df.empty: return pd.DataFrame()
    stats = tag_df.groupby('Tags')['Score'].agg(['mean', 'count']).reset_index()
    stats = stats.sort_values(by='mean', ascending=False)
    return stats

# --- 3. Main Application ---
def main():
    st.set_page_config(page_title="Mood Tracker", page_icon="🧠", layout="centered")
    
    # Simple CSS
    st.markdown("""<style>
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        .stApp {padding-top: 20px;} 
    </style>""", unsafe_allow_html=True)

    st.title("🌱 Mood Tracker")

    # --- AUTHENTICATION FLOW (Final Clean Version) ---
    if "oauth" not in st.secrets:
        st.error("Missing OAuth secrets in .streamlit/secrets.toml")
        st.stop()

    client_id = st.secrets["oauth"]["client_id"]
    client_secret = st.secrets["oauth"]["client_secret"]
    redirect_uri = st.secrets["oauth"]["redirect_uri"]

    # Initialize OAuth Component
    oauth2 = OAuth2Component(client_id, client_secret, AUTHORIZATION_URL, TOKEN_URL, TOKEN_URL, REVOKE_TOKEN_URL)

    # Check if user is logged in
    if "token" not in st.session_state:
        # Show Login Button
        result = oauth2.authorize_button("Continue with Google", redirect_uri, SCOPE)
        
        if result and "token" in result:
            st.session_state.token = result.get("token")
            st.rerun()
        else:
            st.info("Please log in to track your mood privately.")
            st.stop()

    # If logged in, get user email
    if "token" in st.session_state:
        try:
            if "user_info" not in st.session_state:
                headers = {"Authorization": f"Bearer {st.session_state.token['access_token']}"}
                r = oauth2.get(USER_INFO_URL, headers=headers)
                st.session_state.user_info = r.json()
            
            user_email = st.session_state.user_info.get("email")
            st.success(f"👋 Welcome back, {user_email}!")
            
            # Logout Button
            if st.button("Logout"):
                del st.session_state.token
                if "user_info" in st.session_state:
                    del st.session_state.user_info
                st.rerun()
                
        except Exception as e:
            st.error("Login session expired. Please reload.")
            del st.session_state.token
            st.rerun()

    # --- APP LOGIC (Only runs after login) ---
    sheet = get_worksheet()
    if not sheet: st.stop()

    tab1, tab2 = st.tabs(["📝 Check-in", "📊 Insights"])

    with tab1:
        with st.form("bsrs5_form"):
            st.caption("How have you been feeling?")
            date_val = st.date_input("Date", datetime.now())
            st.divider()
            
            # BSRS-5 Logic (Same as before)
            options_map = {"0: None": 0, "1: Mild": 1, "2: Moderate": 2, "3: Severe": 3, "4: Very Severe": 4}
            opts = list(options_map.keys())
            
            a1 = st.select_slider("1. Sleep trouble", options=opts, label_visibility="collapsed")
            a2 = st.select_slider("2. Feeling tense", options=opts, label_visibility="collapsed")
            a3 = st.select_slider("3. Irritated", options=opts, label_visibility="collapsed")
            a4 = st.select_slider("4. Feeling blue", options=opts, label_visibility="collapsed")
            a5 = st.select_slider("5. Inferiority", options=opts, label_visibility="collapsed")
            
            total_score = (options_map[a1] + options_map[a2] + options_map[a3] + options_map[a4] + options_map[a5])
            st.markdown(f"**Score: {total_score} / 20**")

            st.divider()
            tags_list = ["🩸 Period/PMS", "😴 Poor Sleep", "💊 Missed Meds", "🤕 Sick/Pain", "🤯 Work Stress", "👥 Conflict", "🌧️ Bad Weather", "😰 Anxiety", "😶 Apathy", "🏃 Exercise", "🎮 Relax/Gaming", "🥰 Socializing"]
            selected_tags = st.multiselect("Tags", tags_list)
            note = st.text_area("Note", height=80)

            submitted = st.form_submit_button("💾 Save Entry", use_container_width=True)

        if submitted:
            # SAVE LOGIC UPDATE: Include user_email
            data = [user_email, str(date_val), total_score, ", ".join(selected_tags), note]
            sheet.append_row(data)
            st.success("Saved!")
            st.cache_data.clear()

        # FETCH & FILTER DATA
        raw_data = sheet.get_all_records()
        if raw_data:
            df = pd.DataFrame(raw_data)
            # CRITICAL: Filter data for THIS user only
            user_df = analyze_user_data(df, user_email)
            
            if not user_df.empty:
                curr_avg, last_avg = get_weekly_comparison(user_df)
                if pd.notna(curr_avg) and pd.notna(last_avg):
                    delta = curr_avg - last_avg
                    st.divider()
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("This Week", f"{curr_avg:.1f}", f"{delta:.1f}", delta_color="inverse")
                    with col2:
                        if curr_avg > last_avg and curr_avg > 5:
                            st.error("📉 Stress Rising")

    with tab2:
        if raw_data:
            df = pd.DataFrame(raw_data)
            user_df = analyze_user_data(df, user_email)
            
            if not user_df.empty:
                fig = px.line(user_df, x="Date", y="Score", markers=True, hover_data=["Tags", "Note"], title="Your Mood Trend")
                fig.update_traces(line_color='#FF6C6C')
                fig.update_layout(yaxis_range=[0, 21])
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("⚠️ Your Triggers")
                tag_stats = get_tag_correlations(user_df)
                if not tag_stats.empty:
                    st.dataframe(tag_stats.head(5), use_container_width=True, hide_index=True)
            else:
                st.info("No data found for this account yet.")

if __name__ == "__main__":
    main()