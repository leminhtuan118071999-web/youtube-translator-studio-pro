"""Separate AI33 workspace inside the same Streamlit app and URL origin.

The AI33 website remains a third-party service: its frame permissions,
authentication, task persistence, and processing are controlled by AI33.
No LMT credentials or session content are passed to the embedded page.
"""
import streamlit as st
import streamlit.components.v1 as components

AI33_URL = "https://ai33.pro/app"

st.set_page_config(
    page_title="AI33 / OpenSpeaker | LMT Studio Pro",
    page_icon="🎙️",
    layout="wide",
)

st.sidebar.markdown("### 🧭 Ứng dụng")
st.sidebar.page_link(
    "streamlit_app.py",
    label="🎬 YouTube Translator",
    icon="🎬",
    use_container_width=True,
)
st.sidebar.markdown("**🎙️ AI33 / OpenSpeaker — đang xem**")

# Existing translation futures are retained in this Streamlit session when
# switching through page navigation. Their threads can progress until the
# Streamlit server goes down; this is NOT durable background execution.
jobs = st.session_state.get("background_jobs", {})
workspaces = st.session_state.get("workspaces", {})
if isinstance(jobs, dict) and jobs:
    st.sidebar.divider()
    st.sidebar.markdown("**⏳ Tiến độ YouTube Translator**")
    for session_id, job in list(jobs.items()):
        if not isinstance(job, dict):
            continue
        try:
            percent, stage = job["progress"].snapshot()
            finished = job["future"].done()
        except (AttributeError, KeyError, TypeError):
            continue
        name = workspaces.get(session_id, {}).get("name", "Phiên dịch")
        if finished:
            st.sidebar.success(f"✅ {name}: đã xử lý xong. Trở về App 1 để nhận kết quả.")
        else:
            st.sidebar.progress(percent, text=f"{name}: {stage}")

st.title("🎙️ App 2 — AI33 / OpenSpeaker")
st.caption("Khu vực AI33 riêng trong cùng website LMT Studio Pro.")
st.info(
    "AI33 chạy trên máy chủ riêng. Nếu website hạn chế nhúng iframe, đăng nhập "
    "hoặc các công cụ có thể không hoạt động trong khung bên dưới. "
    "Khi đó hãy dùng nút mở AI33 trực tiếp."
)

# Does not pass LMT API keys or any workspaces to the third-party origin.
components.iframe(AI33_URL, height=920, scrolling=True)

st.link_button(
    "↗ Mở AI33 trực tiếp nếu khung không hoạt động",
    AI33_URL,
    use_container_width=True,
)
st.caption(
    "Khi chuyển sang App 1, khung AI33 có thể tải lại. "
    "Các tác vụ phía AI33 phụ thuộc vào lịch sử và cơ chế xử lý của AI33; "
    "không thể bảo đảm tiếp tục nếu đóng trang. "
    "Tương tự, tác vụ dịch hiện tại chưa có hàng đợi bền vững để bảo đảm "
    "chạy qua lúc máy chủ khởi động lại."
)
