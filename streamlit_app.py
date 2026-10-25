import copy
import json
import re
import uuid
from io import BytesIO

import requests
import streamlit as st
from PIL import Image
from youtube_transcript_api import YouTubeTranscriptApi

st.set_page_config(page_title="YouTube Translator Studio Pro", page_icon="🎬", layout="wide")
st.title("🎬 YouTube Translator Studio Pro")
st.caption("Phụ đề YouTube • Dịch đa ngôn ngữ • Prompt hình ảnh • SEO • Thumbnail • Quản lý phiên")

LANGUAGES = ["Tiếng Ba Lan", "Tiếng Việt", "Tiếng Anh", "Tiếng Nhật", "Tiếng Hàn",
             "Tiếng Pháp", "Tiếng Đức", "Tiếng Tây Ban Nha"]
FIELDS = ("url", "source", "title", "description", "translated", "prompts", "metadata", "language")
FORM_FIELDS = ("url", "source", "title", "description", "language")


def blank_session(name):
    return {
        "name": name, "url": "", "source": "", "title": "", "description": "",
        "translated": "", "prompts": "", "metadata": "", "language": "Tiếng Ba Lan",
    }


def unique_name(requested):
    existing = {p["name"].casefold() for p in st.session_state.workspaces.values()}
    base = (requested or "Phiên mới").strip()[:80] or "Phiên mới"
    name = base
    i = 2
    while name.casefold() in existing:
        name = f"{base} ({i})"
        i += 1
    return name


def sync_form(sid):
    """Read current widget values before creating, downloading or switching a session."""
    record = st.session_state.workspaces[sid]
    for field in FORM_FIELDS:
        widget_key = f"field_{sid}_{field}"
        if widget_key in st.session_state:
            record[field] = st.session_state[widget_key]


def export_data(session_ids):
    sync_form(st.session_state.selected_session)
    sessions = []
    for sid in session_ids:
        item = st.session_state.workspaces[sid]
        sessions.append({"name": item["name"], **{f: item.get(f, "") for f in FIELDS}})
    return json.dumps({"format": "youtube-translator-studio-pro", "version": 1,
                       "sessions": sessions}, ensure_ascii=False, indent=2)


def import_data(payload):
    if not isinstance(payload, dict) or payload.get("format") != "youtube-translator-studio-pro":
        raise ValueError("Đây không phải file sao lưu của YouTube Translator Studio Pro.")
    items = payload.get("sessions")
    if not isinstance(items, list) or not items or len(items) > 100:
        raise ValueError("File sao lưu không có phiên hợp lệ hoặc có quá nhiều phiên.")
    imported = []
    for incoming in items:
        if not isinstance(incoming, dict):
            raise ValueError("Dữ liệu phiên không hợp lệ.")
        record = blank_session(unique_name(str(incoming.get("name") or "Phiên khôi phục")))
        for field in FIELDS:
            val = incoming.get(field, record[field])
            if not isinstance(val, str) or len(val) > 500000:
                raise ValueError(f"Dữ liệu '{field}' không hợp lệ hoặc quá lớn.")
            record[field] = val
        if record["language"] not in LANGUAGES:
            record["language"] = LANGUAGES[0]
        sid = uuid.uuid4().hex
        st.session_state.workspaces[sid] = record
        imported.append(sid)
    return imported


# Data belong to this browser's current Streamlit session, never a shared server file.
if "workspaces" not in st.session_state:
    first = uuid.uuid4().hex
    record = blank_session("Phiên 1")
    # Preserve data in an existing browser session after a hot-reload from an older app.
    for field in ("source", "translated", "prompts", "metadata"):
        value = st.session_state.get(field, "")
        if isinstance(value, str):
            record[field] = value
    st.session_state.workspaces = {first: record}
    st.session_state.selected_session = first

# A new selection must be set BEFORE the selectbox is instantiated.
if "_open_session_next" in st.session_state:
    st.session_state["session_picker"] = st.session_state.pop("_open_session_next")

with st.sidebar:
    st.header("📁 Quản lý phiên làm việc")
    names = list(st.session_state.workspaces)
    sid = st.selectbox(
        "Chọn phiên", names,
        index=names.index(st.session_state.selected_session)
        if st.session_state.selected_session in names else 0,
        format_func=lambda x: st.session_state.workspaces[x]["name"],
        key="session_picker",
    )
    st.session_state.selected_session = sid
    session = st.session_state.workspaces[sid]
    st.caption(f"Đang làm việc: {session['name']}")

    new_title = st.text_input("Tên phiên mới", placeholder="Ví dụ: Video 01 - Tiếng Ba Lan")
    if st.button("➕ Tạo phiên mới", use_container_width=True):
        sync_form(sid)
        newid = uuid.uuid4().hex
        st.session_state.workspaces[newid] = blank_session(unique_name(new_title))
        st.session_state["_open_session_next"] = newid
        st.rerun()

    renamed = st.text_input("Đổi tên phiên hiện tại", value=session["name"], key=f"rename_{sid}")
    cols = st.columns(2)
    if cols[0].button("✏️ Đổi tên", use_container_width=True):
        proposed = renamed.strip()[:80]
        if not proposed:
            st.warning("Hãy nhập tên phiên.")
        elif any(p["name"].casefold() == proposed.casefold() and k != sid
                 for k, p in st.session_state.workspaces.items()):
            st.warning("Tên phiên này đã tồn tại.")
        else:
            session["name"] = proposed
            st.rerun()
    if cols[1].button("📑 Nhân bản", use_container_width=True):
        sync_form(sid)
        newid = uuid.uuid4().hex
        duplicate = copy.deepcopy(session)
        duplicate["name"] = unique_name(session["name"] + " - Bản sao")
        st.session_state.workspaces[newid] = duplicate
        st.session_state["_open_session_next"] = newid
        st.rerun()

    if len(st.session_state.workspaces) > 1:
        confirmed = st.checkbox("Xác nhận xóa phiên hiện tại", key=f"confirm_delete_{sid}")
        if st.button("🗑️ Xóa phiên", disabled=not confirmed, use_container_width=True):
            del st.session_state.workspaces[sid]
            st.session_state["_open_session_next"] = next(iter(st.session_state.workspaces))
            st.rerun()

    st.divider()
    st.markdown("**💾 Lưu và khôi phục phiên**")
    st.download_button(
        "💾 Lưu phiên hiện tại (.json)",
        data=export_data([sid]),
        file_name=f"youtube-phien-{sid[:8]}.json",
        mime="application/json",
        use_container_width=True,
    )
    st.download_button(
        "📦 Sao lưu tất cả phiên (.json)",
        data=export_data(list(st.session_state.workspaces)),
        file_name="youtube-tat-ca-phien.json",
        mime="application/json",
        use_container_width=True,
    )
    file_backup = st.file_uploader("📂 Chọn file JSON đã lưu", type=["json"], key="restore_sessions")
    if st.button("♻️ Khôi phục phiên từ file", use_container_width=True):
        if file_backup is None:
            st.warning("Hãy chọn file JSON trước.")
        elif file_backup.size > 8 * 1024 * 1024:
            st.error("File sao lưu vượt quá 8 MB.")
        else:
            try:
                payload = json.loads(file_backup.getvalue().decode("utf-8-sig"))
                new_ids = import_data(payload)
                st.session_state["_open_session_next"] = new_ids[0]
                st.rerun()
            except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as e:
                st.error(f"Không khôi phục được: {e}")
    st.caption("Các phiên được giữ riêng khi đang mở app. Để giữ lại sau khi đóng trình duyệt, hãy tải file JSON và khôi phục khi quay lại. Không lưu API key vào file.")

    st.divider()
    st.subheader("🔑 Cấu hình AI Gemini")
    key = st.text_input("Gemini API key", type="password")
    model = st.text_input("Gemini model", value="gemini-3.8-flash")
    language = st.selectbox(
        "Ngôn ngữ đích", LANGUAGES,
        index=LANGUAGES.index(session.get("language", LANGUAGES[0]))
        if session.get("language") in LANGUAGES else 0,
        key=f"field_{sid}_language",
    )
    session["language"] = language
    st.caption("Cần Gemini API key riêng. Không đưa API key vào GitHub.")


def ai(prompt):
    if not key.strip():
        raise ValueError("Hãy nhập Gemini API key ở thanh bên trái.")
    model_name = model.strip()
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", model_name):
        raise ValueError("Tên model Gemini không hợp lệ.")
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    try:
        response = requests.post(
            endpoint, headers={"x-goog-api-key": key.strip()},
            json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=180
        )
    except requests.RequestException as e:
        raise RuntimeError("Không kết nối được Gemini API. Hãy kiểm tra mạng.") from e
    if not response.ok:
        try:
            error = response.json().get("error", {})
            detail = str(error.get("message", response.text[:400]))
        except (ValueError, AttributeError):
            detail = response.text[:400]
        detail = detail.replace(key.strip(), "[API KEY ĐÃ ẨN]")[:750]
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {detail}")
    try:
        chunks = response.json()["candidates"][0]["content"]["parts"]
        result = "\n".join(p.get("text", "") for p in chunks).strip()
        if not result:
            raise ValueError("Gemini không trả văn bản.")
        return result
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise RuntimeError("Không nhận được nội dung từ Gemini. Hãy thử lại.") from e


if st.sidebar.button("🧪 Kiểm tra kết nối Gemini"):
    try:
        st.sidebar.success("Kết nối OK: " + ai("Chỉ trả lời: OK")[:80])
    except Exception as e:
        st.sidebar.error(str(e))


def output(title, text):
    st.markdown("**" + title + "**")
    if not text:
        st.caption("Chưa có nội dung.")
        return
    # The code widget has a copy icon for copying its full, untruncated text.
    st.code(text, language=None, wrap_lines=True)
    st.download_button(
        "⬇️ Tải nội dung (.txt)", text, file_name="youtube-output.txt",
        mime="text/plain", key=f"save_{sid}_{re.sub('[^a-z0-9]', '', title.lower())[:24]}"
    )


st.info(f"📂 **Phiên đang mở:** {session['name']} — mọi kết quả chỉ thuộc phiên này.")
session["url"] = st.text_input(
    "🔗 Dán link video YouTube",
    value=session["url"], key=f"field_{sid}_url",
)
match = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/)([\w-]{11})", session["url"])
vid = match.group(1) if match else None
if st.button("📥 Trích xuất phụ đề", key=f"extract_{sid}"):
    if not vid:
        st.warning("Hãy nhập link YouTube hợp lệ.")
    else:
        try:
            items = YouTubeTranscriptApi().fetch(vid, languages=["vi", "en", "pl"])
            text = " ".join(item.text for item in items)
            session["source"] = text
            st.session_state[f"field_{sid}_source"] = text
            st.success("Đã trích xuất phụ đề.")
        except Exception as e:
            st.error("Không thể trích xuất phụ đề: " + str(e))

if vid:
    st.subheader("🖼️ Thumbnail gốc chất lượng cao")
    for quality in ["maxresdefault", "sddefault", "hqdefault", "mqdefault"]:
        try:
            r = requests.get(f"https://i.ytimg.com/vi/{vid}/{quality}.jpg", timeout=8)
            r.raise_for_status()
            image = Image.open(BytesIO(r.content))
            if image.width >= 300:
                st.image(r.content, width=500)
                st.download_button("⬇️ Tải thumbnail", r.content, file_name=f"thumbnail-{vid}.jpg",
                                   mime="image/jpeg", key=f"thumb_{sid}_{vid}")
                break
        except Exception:
            continue

upload = st.file_uploader("📄 Hoặc chọn file phụ đề .txt", type=["txt"], key=f"upload_{sid}")
if upload and st.button("Dùng file phụ đề này", key=f"use_upload_{sid}"):
    if upload.size > 4 * 1024 * 1024:
        st.error("File phụ đề vượt giới hạn 4 MB.")
    else:
        session["source"] = upload.getvalue().decode("utf-8-sig", errors="replace")
        st.session_state[f"field_{sid}_source"] = session["source"]

session["source"] = st.text_area(
    "📄 Phụ đề / văn bản gốc",
    value=session["source"], height=190, key=f"field_{sid}_source"
)
session["title"] = st.text_input("🎬 Tiêu đề gốc", value=session["title"], key=f"field_{sid}_title")
session["description"] = st.text_area(
    "📝 Mô tả gốc", value=session["description"], height=110,
    key=f"field_{sid}_description"
)
# The original subtitle copy section is deliberately omitted at the user's request.
output("Copy tiêu đề gốc", session["title"])
output("Copy mô tả gốc", session["description"])

tab_translate, tab_visual, tab_seo = st.tabs(
    ["🌍 Bản dịch", "🎨 20 prompt ảnh", "📝 YouTube SEO"]
)
with tab_translate:
    if st.button("Dịch toàn bộ", type="primary", key=f"translate_{sid}"):
        if not session["source"].strip():
            st.warning("Chưa có phụ đề hoặc văn bản gốc.")
        else:
            try:
                pieces = [session["source"][i:i+7000] for i in range(0, len(session["source"]), 7000)]
                result = []
                with st.spinner("Đang dịch..."):
                    for piece in pieces:
                        result.append(ai("Dịch chính xác sang " + language
                                         + ", giữ nguyên tên nhân vật, tự nhiên, chỉ xuất bản dịch:\n" + piece))
                session["translated"] = "\n\n".join(result)
                st.success("Đã dịch xong trong phiên hiện tại.")
            except Exception as e:
                st.error(str(e))
    output("Copy toàn bộ bản dịch", session["translated"])

with tab_visual:
    if st.button("Tạo 20 prompt hình ảnh", key=f"prompts_{sid}"):
        base = (session["translated"] or session["source"])[:25000]
        if not base:
            st.warning("Chưa có câu chuyện.")
        else:
            try:
                with st.spinner("Đang tạo prompt..."):
                    session["prompts"] = ai(
                        "Create exactly 20 numbered cinematic image prompts in English, "
                        "following the story chronologically. Output only prompts:\n" + base)
            except Exception as e:
                st.error(str(e))
    output("Copy toàn bộ 20 prompt hình ảnh", session["prompts"])

with tab_seo:
    if st.button("Tạo tiêu đề, mô tả và SEO", key=f"seo_{sid}"):
        original = "\n".join([
            session["title"], session["description"],
            (session["translated"] or session["source"])[:16000],
        ])
        if not original.strip():
            st.warning("Chưa có nội dung để tạo SEO.")
        else:
            try:
                with st.spinner("Đang tạo nội dung SEO..."):
                    session["metadata"] = ai(
                        "Viết nội dung YouTube bằng " + language
                        + ". Bao gồm tiêu đề 🎬, mô tả 📝 có emoji phù hợp và 15 từ khóa SEO. "
                        "Sát nghĩa, tự nhiên, không có ký tự markdown thừa:\n" + original)
            except Exception as e:
                st.error(str(e))
    output("Copy toàn bộ tiêu đề, mô tả và SEO", session["metadata"])

st.caption("Nút Copy nằm ở góc phải khung nội dung. Các phiên không chia sẻ dữ liệu với nhau; hãy sao lưu JSON để sử dụng lại sau khi đóng app.")
