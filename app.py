import streamlit as st
import gspread
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime, timedelta
from google_auth_oauthlib.flow import Flow # 使用官方 Google 套件

# --- Configuration ---
SHEET_NAME = "MoodTrackerDB"

# --- 1. Database Connection ---
@st.cache_resource
def get_worksheet():
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
def analyze_user_data(df, user_email):
    df = df[df['User_Email'] == user_email].copy()
    if df.empty: return df
    df['Date'] = pd.to_datetime(df['Date'])
    return df.sort_values(by='Date')

def get_weekly_comparison(df):
    if df.empty: return None, None
    today = datetime.now()
    curr_df = df[(df['Date'] > (today - timedelta(days=7))) & (df['Date'] <= today)]
    last_df = df[(df['Date'] > (today - timedelta(days=14))) & (df['Date'] <= (today - timedelta(days=7)))]
    return curr_df['Score'].mean(), last_df['Score'].mean()

def get_tag_correlations(df):
    tag_df = df[df['Tags'] != ""].copy()
    tag_df['Tags'] = tag_df['Tags'].astype(str).str.split(', ')
    tag_df = tag_df.explode('Tags')
    if tag_df.empty: return pd.DataFrame()
    return tag_df.groupby('Tags')['Score'].agg(['mean', 'count']).reset_index().sort_values(by='mean', ascending=False)

# --- 3. Main Application ---
def main():
    st.set_page_config(page_title="Mood Tracker", page_icon="🧠", layout="centered")
    
    # Hide Streamlit UI
    st.markdown("""<style>
        #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
        .stApp {padding-top: 20px;} 
    </style>""", unsafe_allow_html=True)

    st.title("🌱 Mood Tracker")

    # --- 🛠️ MANUAL AUTH FLOW (The Robust Way) ---
    if "user_email" not in st.session_state:
        
        client_config = {
            "web": {
                "client_id": st.secrets["oauth"]["client_id"],
                "client_secret": st.secrets["oauth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        
        redirect_uri = "https://moodtracker-123.streamlit.app"


        flow = Flow.from_client_config(
            client_config,
            scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
            redirect_uri=redirect_uri
        )

        if "code" in st.query_params:
            try:
                code = st.query_params["code"]

                flow.fetch_token(code=code)
                credentials = flow.credentials

                user_info_service = requests.get(
                    "https://www.googleapis.com/oauth2/v1/userinfo",
                    headers={"Authorization": f"Bearer {credentials.token}"}
                )
                user_email = user_info_service.json().get("email")
                
                st.session_state.user_email = user_email
                
                st.query_params.clear()
                st.rerun()
                
            except Exception as e:
                st.error(f"Login failed: {e}")
                st.stop()

        else:
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.markdown(f'''
                <a href="{auth_url}" target="_blank">
                    <button style="
                        background-color: white; color: #333; border: 1px solid #ccc; 
                        padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 16px;
                        display: flex; align-items: center; gap: 10px;">
                        <img src="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg" width="20"/>
                        Sign in with Google
                    </button>
                </a>
                <p style="font-size: 12px; color: grey; margin-top: 5px;">
                    (基於安全性考量，登入將會開啟新視窗)
                </p>
                ''', unsafe_allow_html=True)
            st.info("🔒 Please log in to access your private journal.")
            st.stop()

    user_email = st.session_state.user_email
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.success(f"👋 Hi, {user_email}")
    with col2:
        if st.button("Logout"):
            del st.session_state.user_email
            st.rerun()

    # --- APP LOGIC STARTS HERE ---
    sheet = get_worksheet()
    if not sheet: st.stop()

    tab1, tab2 = st.tabs(["📝 Check-in", "📊 Insights"])

    with tab1:
        st.subheader("📝 今日心情檢核")
        st.caption("請回想最近一週（包含今天）的身心狀況：")
        
        col_date, _ = st.columns([2, 1])
        with col_date:
            date_val = st.date_input("日期", datetime.now())
        
        st.divider()
        
        opts_map = {
            "0: 完全沒有": 0, 
            "1: 輕微": 1, 
            "2: 中等": 2, 
            "3: 厲害": 3, 
            "4: 非常厲害": 4
        }
        opts = list(opts_map.keys())
        
        st.markdown("##### 1. 睡眠困難 (難入睡/易醒/早醒)")
        q1 = st.select_slider("Sleep", opts, label_visibility="collapsed")
        
        st.markdown("##### 2. 感覺緊張不安")
        q2 = st.select_slider("Tense", opts, label_visibility="collapsed")
        
        st.markdown("##### 3. 覺得容易苦惱或動怒")
        q3 = st.select_slider("Irritated", opts, label_visibility="collapsed")
        
        st.markdown("##### 4. 感覺憂鬱、心情低落")
        q4 = st.select_slider("Blue", opts, label_visibility="collapsed")
        
        st.markdown("##### 5. 覺得比不上別人")
        q5 = st.select_slider("Inferior", opts, label_visibility="collapsed")
        
        score = sum([opts_map[q] for q in [q1, q2, q3, q4, q5]])
        
        if score < 6:
            st.success(f"😊 當前總分：{score} / 20 (狀況不錯)")
        elif score < 10:
            st.info(f"😐 當前總分：{score} / 20 (輕度困擾)")
        elif score < 15:
            st.warning(f"😟 當前總分：{score} / 20 (中度困擾)")
        else:
            st.error(f"🚨 當前總分：{score} / 20 (嚴重困擾，請多保重)")

        st.divider()
        
        tags = st.multiselect("影響心情的因素 (Tags)", 
            ["🩸 生理期/經前", "😴 沒睡好", "💊 忘記吃藥", 
                "🤕 身體不舒服", "🤯 工作壓力", "👥 人際衝突", 
                "🌧️ 天氣不好", "😰 莫名焦慮", "😶 無動力/空虛",
                "🏃 有運動", "🎮 放鬆/娛樂", "🥰 與朋友聚會"])
        
        note = st.text_area("一句話日記 (Note)", placeholder="今天發生了什麼小事？")
        
        if st.button("💾 儲存紀錄 (Save Entry)", type="primary", use_container_width=True):
            if not user_email:
                st.error("請先登入")
            else:
                sheet.append_row([user_email, str(date_val), score, ", ".join(tags), note])
                st.toast("✅ 紀錄已儲存！", icon="🎉")
                st.cache_data.clear()
                import time
                time.sleep(1)
                st.rerun()

        # Instant Stats
        raw = sheet.get_all_records()
        if raw:
            df = analyze_user_data(pd.DataFrame(raw), user_email)
            if not df.empty:
                curr, last = get_weekly_comparison(df)
                if curr is not None and last is not None:
                    delta = curr - last
                    st.divider()
                    st.metric("Week Avg", f"{curr:.1f}", f"{delta:.1f}", delta_color="inverse")

    with tab2:
        if raw:
            df = analyze_user_data(pd.DataFrame(raw), user_email)
            if not df.empty:
                fig = px.line(df, x="Date", y="Score", markers=True, title="Mood Trend")
                fig.update_layout(yaxis_range=[0, 21]) 
                st.plotly_chart(fig)
            else:
                st.info("No data yet.")

if __name__ == "__main__":
    main()