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

def get_tag_correlations(df):
    # Filter out empty tags
    tag_df = df[df['Tags'] != ""].copy()
    
    # Split tags by comma (since we stored them as "Tag1, Tag2")
    tag_df['Tags'] = tag_df['Tags'].astype(str).str.split(', ')
    
    # Explode the list so each tag gets its own row
    tag_df = tag_df.explode('Tags')
    
    if tag_df.empty: return pd.DataFrame()
    
    # Group by Tag and calculate average score and count
    stats = tag_df.groupby('Tags')['Score'].agg(['mean', 'count']).reset_index()
    
    # Sort by average score (highest stress first)
    return stats.sort_values(by='mean', ascending=False)

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

def get_pattern_insights(df):
    """Generate smart insights based on user's mood patterns"""
    insights = []

    if df.empty or len(df) < 7:
        return insights

    # Add day of week column
    df_copy = df.copy()
    df_copy['DayOfWeek'] = df_copy['Date'].dt.dayofweek
    df_copy['DayName'] = df_copy['Date'].dt.day_name()

    # 1. Day of week patterns
    day_stats = df_copy.groupby('DayName')['Score'].agg(['mean', 'count']).reset_index()
    if len(day_stats) >= 3:  # Need at least 3 different days
        best_day = day_stats.loc[day_stats['mean'].idxmin()]
        worst_day = day_stats.loc[day_stats['mean'].idxmax()]

        if worst_day['mean'] - best_day['mean'] >= 2:
            insights.append({
                'type': 'day_pattern',
                'icon': '📅',
                'text': f"你在 **{worst_day['DayName']}** 時分數通常較高 (平均 {worst_day['mean']:.1f})，而 **{best_day['DayName']}** 時較低 (平均 {best_day['mean']:.1f})。"
            })

    # 2. Recent trend (last 7 days vs previous 7 days)
    if len(df_copy) >= 14:
        recent_7 = df_copy.nlargest(7, 'Date')['Score'].mean()
        prev_7 = df_copy.nlargest(14, 'Date').nsmallest(7, 'Date')['Score'].mean()
        diff = recent_7 - prev_7

        if abs(diff) >= 2:
            if diff > 0:
                insights.append({
                    'type': 'trend',
                    'icon': '📈',
                    'text': f"最近 7 天你的平均分數比前一週高了 {diff:.1f} 分。記得多照顧自己，必要時尋求支持。"
                })
            else:
                insights.append({
                    'type': 'trend',
                    'icon': '📉',
                    'text': f"最近 7 天你的平均分數比前一週降低了 {abs(diff):.1f} 分。做得好！繼續保持讓你感覺更好的習慣。"
                })

    # 3. Consecutive high scores warning
    recent_5 = df_copy.nlargest(5, 'Date').sort_values('Date')
    if len(recent_5) == 5 and recent_5['Score'].mean() >= 12:
        insights.append({
            'type': 'warning',
            'icon': '⚠️',
            'text': f"你最近 5 次記錄的平均分數為 {recent_5['Score'].mean():.1f}（中高程度）。如果持續感到困擾，建議尋求專業協助。"
        })

    # 4. Tag-based insights (if tags exist)
    if 'Tags' in df_copy.columns:
        tag_stats = get_tag_correlations(df_copy)
        if not tag_stats.empty and len(tag_stats) >= 2:
            # Define positive tags (protective factors)
            positive_tags = ["🏃 有運動", "🎮 放鬆/娛樂", "🥰 與朋友聚會"]

            # Find most helpful positive tag
            positive_tag_stats = tag_stats[tag_stats['Tags'].isin(positive_tags)]
            if not positive_tag_stats.empty:
                best_tag = positive_tag_stats.iloc[-1]  # Last one (lowest mean score among positive tags)
                if best_tag['count'] >= 3:  # Need at least 3 occurrences
                    insights.append({
                        'type': 'tag_insight',
                        'icon': '💡',
                        'text': f"「{best_tag['Tags']}」在你記錄中出現了 {int(best_tag['count'])} 次，平均分數為 {best_tag['mean']:.1f}。這是個好習慣！"
                    })

    return insights

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

        # Medication Adherence Tracker
        st.markdown("##### 💊 用藥紀錄 (Medication)")
        med_taken = st.checkbox("✅ 今天有按時服藥", value=True, help="追蹤用藥順從性有助於了解藥物對情緒的影響")

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

        st.divider()

        # Gratitude & Positive Psychology Section
        st.markdown("##### 🌟 今日感恩 & 小確幸 (Gratitude & Wins)")
        st.caption("記錄正向的事物能幫助平衡負面情緒 - 研究證實對憂鬱症有幫助")

        gratitude_1 = st.text_input("1. 今天感謝的一件事", placeholder="例：朋友的一句關心、好吃的一餐、陽光...")
        gratitude_2 = st.text_input("2. 今天做得不錯的事（再小都可以）", placeholder="例：起床了、洗澡了、回了訊息、出門買東西...")
        gratitude_3 = st.text_input("3. 今天讓你微笑的瞬間（可選）", placeholder="例：看到可愛的貓、聽到喜歡的歌...", key="gratitude_3")

        if st.button("💾 儲存紀錄 (Save Entry)", type="primary", use_container_width=True):
            if not user_email:
                st.error("請先登入")
            else:
                # Combine gratitude entries with separator
                gratitude_entries = " | ".join([g for g in [gratitude_1, gratitude_2, gratitude_3] if g.strip()])
                # Convert medication boolean to string for storage
                med_status = "Yes" if med_taken else "No"
                sheet.append_row([user_email, str(date_val), score, ", ".join(tags), note, gratitude_entries, med_status])
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
            # Convert raw data to DataFrame
            df = analyze_user_data(pd.DataFrame(raw), user_email)

            if not df.empty:
                # 0. Smart Pattern Insights (NEW!)
                st.subheader("🧠 智能洞察 (Pattern Insights)")
                st.caption("基於你的紀錄自動分析出的模式")

                insights = get_pattern_insights(df)

                if insights:
                    for insight in insights:
                        if insight['type'] == 'warning':
                            st.warning(f"{insight['icon']} {insight['text']}")
                        elif insight['type'] == 'trend' and '降低' in insight['text']:
                            st.success(f"{insight['icon']} {insight['text']}")
                        else:
                            st.info(f"{insight['icon']} {insight['text']}")
                else:
                    st.info("繼續記錄幾天後，這裡會顯示個人化的洞察分析！")

                st.divider()

                # 1. Trend Chart (Existing)
                st.subheader("📈 Mood Trend")
                fig_trend = px.line(df, x="Date", y="Score", markers=True, title="Mood Score Over Time")
                fig_trend.update_layout(yaxis_range=[0, 21])
                st.plotly_chart(fig_trend, use_container_width=True)

                # Day of Week Pattern (if enough data)
                if len(df) >= 7:
                    df_temp = df.copy()
                    df_temp['DayOfWeek'] = df_temp['Date'].dt.day_name()
                    # Order days correctly
                    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    day_stats = df_temp.groupby('DayOfWeek')['Score'].mean().reindex(day_order).dropna()

                    if len(day_stats) >= 3:
                        with st.expander("📅 查看星期分布"):
                            fig_dow = px.bar(
                                x=day_stats.index,
                                y=day_stats.values,
                                labels={'x': 'Day of Week', 'y': 'Avg Score'},
                                title="Average Score by Day of Week",
                                color=day_stats.values,
                                color_continuous_scale="RdYlGn_r"
                            )
                            fig_dow.update_layout(showlegend=False)
                            st.plotly_chart(fig_dow, use_container_width=True)

                st.divider()

                # 2. Tag Correlation Analysis - Enhanced with Protective Factors
                st.subheader("🔍 What affects your mood?")

                # Calculate stats
                tag_stats = get_tag_correlations(df)

                if not tag_stats.empty:
                    # Define which tags are inherently positive (protective) vs negative (stressors)
                    positive_tags = ["🏃 有運動", "🎮 放鬆/娛樂", "🥰 與朋友聚會"]
                    negative_tags = ["🩸 生理期/經前", "😴 沒睡好", "💊 忘記吃藥",
                                   "🤕 身體不舒服", "🤯 工作壓力", "👥 人際衝突",
                                   "🌧️ 天氣不好", "😰 莫名焦慮", "😶 無動力/空虛"]

                    # Calculate overall average score for comparison
                    overall_avg = df['Score'].mean()

                    # Separate based on tag category AND score comparison
                    stressors = tag_stats[tag_stats['Tags'].isin(negative_tags)].sort_values(by='mean', ascending=False)
                    protective = tag_stats[tag_stats['Tags'].isin(positive_tags)].sort_values(by='mean', ascending=True)

                    # Display insights
                    col_stress, col_protect = st.columns(2)

                    with col_stress:
                        st.metric("Overall Avg Score", f"{overall_avg:.1f}", help="Your average mood score across all entries")

                    with col_protect:
                        if not protective.empty:
                            best_factor = protective.iloc[0]['Tags']
                            best_score = protective.iloc[0]['mean']
                            improvement = overall_avg - best_score
                            st.metric("Best Helper", f"{best_factor}", f"-{improvement:.1f}", delta_color="inverse", help="Tag with lowest avg score")

                    # Show stressors
                    if not stressors.empty:
                        st.markdown("#### ⚠️ 壓力因素 (Stressors)")
                        st.caption(f"這些標籤出現時，你的分數通常較高（平均 > {overall_avg:.1f}）")

                        fig_stress = px.bar(
                            stressors,
                            x="mean",
                            y="Tags",
                            orientation='h',
                            labels={"mean": "Avg Score", "Tags": ""},
                            text="mean",
                            color="mean",
                            color_continuous_scale="Reds"
                        )
                        fig_stress.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                        fig_stress.update_layout(
                            yaxis={'categoryorder':'total ascending'},
                            showlegend=False,
                            height=max(200, len(stressors) * 40)
                        )
                        st.plotly_chart(fig_stress, use_container_width=True)

                    # Show protective factors
                    if not protective.empty:
                        st.markdown("#### 💚 保護因素 (Protective Factors)")
                        st.caption(f"這些標籤出現時，你的分數通常較低（平均 ≤ {overall_avg:.1f}）")

                        fig_protect = px.bar(
                            protective,
                            x="mean",
                            y="Tags",
                            orientation='h',
                            labels={"mean": "Avg Score", "Tags": ""},
                            text="mean",
                            color="mean",
                            color_continuous_scale="Greens_r"  # Reverse so darker = better
                        )
                        fig_protect.update_traces(texttemplate='%{text:.1f}', textposition='outside')
                        fig_protect.update_layout(
                            yaxis={'categoryorder':'total descending'},
                            showlegend=False,
                            height=max(200, len(protective) * 40)
                        )
                        st.plotly_chart(fig_protect, use_container_width=True)

                        # Actionable insight
                        st.success(f"💡 **洞察**: 試著增加「{protective.iloc[0]['Tags']}」的頻率，這通常能幫助你感覺更好！")

                    # Show detail table (optional)
                    with st.expander("See detailed statistics"):
                        st.dataframe(tag_stats.rename(columns={"mean": "Avg Score", "count": "Frequency"}), use_container_width=True)
                else:
                    st.info("No tags recorded yet. Try adding tags to your entries!")

                st.divider()

                # 3. Medication Adherence Analysis
                st.subheader("💊 用藥順從性分析 (Medication Adherence)")

                # Check if Medication column exists
                if 'Medication' in df.columns:
                    # Filter last 30 days
                    med_df = df[df['Date'] > (datetime.now() - timedelta(days=30))].copy()

                    if not med_df.empty:
                        # Calculate adherence rate
                        total_days = len(med_df)
                        days_taken = len(med_df[med_df['Medication'] == 'Yes'])
                        adherence_rate = (days_taken / total_days * 100) if total_days > 0 else 0

                        # Display metrics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("30天服藥率", f"{adherence_rate:.0f}%")
                        with col2:
                            st.metric("已服藥天數", f"{days_taken}/{total_days}")
                        with col3:
                            missed_days = total_days - days_taken
                            st.metric("漏服天數", f"{missed_days}")

                        # Adherence color coding
                        if adherence_rate >= 80:
                            st.success("✅ 服藥順從性良好！持續保持。")
                        elif adherence_rate >= 50:
                            st.warning("⚠️ 服藥順從性中等。試著設定提醒來提高服藥率。")
                        else:
                            st.error("🚨 服藥順從性偏低。建議與醫師討論是否需要調整用藥計畫。")

                        # Correlation: Medication vs Mood Score
                        if len(med_df[med_df['Medication'] == 'Yes']) > 0 and len(med_df[med_df['Medication'] == 'No']) > 0:
                            avg_score_taken = med_df[med_df['Medication'] == 'Yes']['Score'].mean()
                            avg_score_missed = med_df[med_df['Medication'] == 'No']['Score'].mean()
                            score_diff = avg_score_missed - avg_score_taken

                            st.markdown("#### 用藥對情緒的影響")
                            col_a, col_b = st.columns(2)
                            with col_a:
                                st.metric("有服藥時平均分數", f"{avg_score_taken:.1f}")
                            with col_b:
                                st.metric("漏服藥時平均分數", f"{avg_score_missed:.1f}", f"+{score_diff:.1f}" if score_diff > 0 else f"{score_diff:.1f}")

                            if score_diff > 1:
                                st.info(f"💡 **洞察**: 漏服藥時，你的分數平均高 {score_diff:.1f} 分。規律服藥似乎對你的情緒有幫助。")
                            elif score_diff < -1:
                                st.info(f"💡 **洞察**: 有服藥時，你的分數平均高 {abs(score_diff):.1f} 分。建議與醫師討論藥物是否適合。")
                            else:
                                st.info("💡 用藥與情緒分數的關聯性不明顯，可能需要更多數據來分析。")
                    else:
                        st.info("最近 30 天沒有用藥紀錄。")
                else:
                    st.info("用藥追蹤功能已新增！下次記錄時就可以使用了。")

                st.divider()

                # 4. Gratitude Review Section
                st.subheader("🌟 回顧感恩時刻 (Gratitude Journal)")

                # Check if Gratitude column exists
                if 'Gratitude' in df.columns:
                    gratitude_df = df[df['Gratitude'].notna() & (df['Gratitude'] != "")].copy()

                    if not gratitude_df.empty:
                        # Show recent gratitude entries
                        st.caption(f"過去 30 天的感恩紀錄 ({len(gratitude_df)} 則)")

                        # Filter last 30 days
                        recent_gratitude = gratitude_df[gratitude_df['Date'] > (datetime.now() - timedelta(days=30))].sort_values(by='Date', ascending=False)

                        if not recent_gratitude.empty:
                            for _, row in recent_gratitude.head(10).iterrows():
                                date_str = row['Date'].strftime('%Y-%m-%d')
                                gratitude_text = row['Gratitude']

                                # Display each gratitude entry as a card
                                st.markdown(f"**{date_str}**")

                                # Split by separator and show each item
                                items = gratitude_text.split(' | ')
                                for item in items:
                                    if item.strip():
                                        st.markdown(f"- {item}")
                                st.markdown("")  # Add spacing
                        else:
                            st.info("最近 30 天沒有感恩紀錄，試著記錄一些正向的事物吧！")
                    else:
                        st.info("還沒有感恩紀錄。在「Check-in」頁面開始記錄吧！")
                else:
                    st.info("感恩功能已新增！下次記錄時就可以使用了。")

            else:
                st.info("No data available for this user.")
        else:
            st.info("Database is empty.")

if __name__ == "__main__":
    main()