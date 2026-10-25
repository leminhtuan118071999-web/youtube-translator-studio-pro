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

LANGUAGES = [
    "Tiếng Ba Lan", "Tiếng Anh", "Tiếng Pháp", "Tiếng Đức", "Tiếng Tây Ban Nha",
    "Tiếng Ý", "Tiếng Bồ Đào Nha", "Tiếng Hà Lan", "Tiếng Thụy Điển",
    "Tiếng Na Uy", "Tiếng Đan Mạch", "Tiếng Phần Lan", "Tiếng Iceland",
    "Tiếng Séc", "Tiếng Slovakia", "Tiếng Hungary", "Tiếng Romania",
    "Tiếng Bulgaria", "Tiếng Hy Lạp", "Tiếng Croatia", "Tiếng Serbia",
    "Tiếng Slovenia", "Tiếng Bosnia", "Tiếng Albania", "Tiếng Lithuania",
    "Tiếng Latvia", "Tiếng Estonia", "Tiếng Ukraine", "Tiếng Nga",
    "Tiếng Belarus", "Tiếng Thổ Nhĩ Kỳ", "Tiếng Ireland", "Tiếng Malta",
    "Tiếng Catalan", "Tiếng Basque", "Tiếng Wales", "Tiếng Luxembourg",
    "Tiếng Macedonia", "Tiếng Việt", "Tiếng Nhật", "Tiếng Hàn",
]
FIELDS = ("url", "source", "title", "description", "translated", "prompts", "metadata", "language")
FORM_FIELDS = ("url", "source", "title", "description", "language")


def blank_session(name):
    return {
        "name": name, "url": "", "source": "", "title": "", "description": "",
        "translated": "", "prompts": "", "metadata": "", "language": "Tiếng Ba Lan",
        "saved": False, "processed": False, "saved_order": 0,
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

# Existing workspaces may come from older versions; only completed work is saved.
if "saved_session_order" not in st.session_state:
    st.session_state.saved_session_order = 0
for _id, _rec in st.session_state.workspaces.items():
    old_order = _rec.get("saved_order", 0)
    if isinstance(old_order, int) and old_order > 0:
        st.session_state.saved_session_order = max(st.session_state.saved_session_order, old_order)
    if "processed" not in _rec:
        _rec["processed"] = any(
            isinstance(_rec.get(field), str) and _rec[field].strip()
            for field in ("source", "translated", "prompts", "metadata")
        )
    _rec["saved"] = bool(_rec["processed"])
for _id, _rec in st.session_state.workspaces.items():
    if not isinstance(_rec.get("saved_order"), int) or _rec["saved_order"] <= 0:
        st.session_state.saved_session_order += 1
        _rec["saved_order"] = st.session_state.saved_session_order


def mark_session_processed(record):
    """Only successful subtitle extraction, file import, translation, prompts or SEO is saved."""
    record["processed"] = True
    record["saved"] = True
    if not isinstance(record.get("saved_order"), int) or record["saved_order"] <= 0:
        st.session_state.saved_session_order += 1
        record["saved_order"] = st.session_state.saved_session_order
    st.session_state["_session_flash"] = "✅ Đã đưa phiên xử lý thành công vào danh sách."


def rename_saved_session(saved_id):
    """Persist a changed name immediately when the inline text field is edited."""
    if saved_id not in st.session_state.workspaces:
        return
    item = st.session_state.workspaces[saved_id]
    widget_key = f"inline_session_name_{saved_id}"
    new_name = st.session_state.get(widget_key, "").strip()[:80]
    if not new_name:
        st.session_state[widget_key] = item["name"]
        st.session_state["session_name_message"] = "Tên phiên không được để trống."
        return
    if any(
        other_id != saved_id and other["name"].casefold() == new_name.casefold()
        for other_id, other in st.session_state.workspaces.items()
    ):
        st.session_state[widget_key] = item["name"]
        st.session_state["session_name_message"] = "Tên phiên đã tồn tại. Hãy chọn tên khác."
        return
    item["name"] = new_name
    st.session_state["editing_session_id"] = None


# On a rerun after creating or opening a session, set the active session directly.
# The saved-session buttons are the only navigation controls; no top dropdown.
if "_open_session_next" in st.session_state:
    st.session_state.selected_session = st.session_state.pop("_open_session_next")

with st.sidebar:
    # Set the language for the currently selected session at the VERY TOP.
    sid = st.session_state.selected_session
    if sid not in st.session_state.workspaces:
        sid = next(iter(st.session_state.workspaces))
        st.session_state.selected_session = sid
    session = st.session_state.workspaces[sid]
    lang_value = session.get("language", "Tiếng Ba Lan")
    language = st.selectbox(
        "🌍 Ngôn ngữ đích",
        LANGUAGES,
        index=LANGUAGES.index(lang_value) if lang_value in LANGUAGES else 0,
        key=f"field_{sid}_language",
        help="Chọn ngôn ngữ cho phiên đang mở; có thêm nhiều ngôn ngữ châu Âu.",
    )
    session["language"] = language
    st.divider()

    st.header("📁 Quản lý phiên làm việc")

    if st.button("➕ Tạo phiên mới", use_container_width=True):
        sync_form(sid)
        newid = uuid.uuid4().hex
        st.session_state.saved_session_order += 1
        new_session = blank_session(unique_name(f"Phiên {st.session_state.saved_session_order}"))
        new_session["saved_order"] = st.session_state.saved_session_order
        st.session_state.workspaces[newid] = new_session
        st.session_state["_open_session_next"] = newid
        st.rerun()

    if st.session_state.pop("_reset_delete_confirm_next", False):
        st.session_state["confirm_delete_all_sessions"] = False
    confirm_all = st.checkbox(
        "Tôi xác nhận xóa tất cả phiên",
        key="confirm_delete_all_sessions",
    )
    if st.button(
        "🗑️ Xóa tất cả phiên đã lưu",
        type="secondary",
        disabled=not confirm_all,
        use_container_width=True,
    ):
        new_id = uuid.uuid4().hex
        new_session = blank_session("Phiên 1")
        new_session["saved_order"] = 1
        st.session_state.saved_session_order = 1
        st.session_state.workspaces = {new_id: new_session}
        st.session_state["editing_session_id"] = None
        st.session_state["_open_session_next"] = new_id
        st.session_state["_reset_delete_confirm_next"] = True
        st.rerun()

    st.divider()
    st.markdown("**📚 Danh sách phiên đã chạy**")
    st.caption("Nhấn vào tên để xem lại; nhấn ✏️ để đổi tên.")
    name_message = st.session_state.pop("session_name_message", None)
    if name_message:
        st.warning(name_message)

    saved_sessions = sorted(
        (
            (saved_id, saved_record)
            for saved_id, saved_record in st.session_state.workspaces.items()
            if saved_record.get("processed", False)
        ),
        key=lambda pair: pair[1].get("saved_order", 0),
        reverse=True,
    )
    if not saved_sessions:
        st.caption("Chưa có phiên nào xử lý thành công.")
    for saved_id, saved_record in saved_sessions:
        name_col, edit_col = st.columns([5, 1], gap="small")
        with name_col:
            label = f"📄 {saved_record['name']}" + (" ✓" if saved_id == sid else "")
            if st.button(
                label,
                key=f"open_saved_session_{saved_id}",
                use_container_width=True,
                type="primary" if saved_id == sid else "secondary",
                help="Nhấn tên phiên để mở lại nội dung",
            ):
                if saved_id != sid:
                    sync_form(sid)
                    st.session_state["_open_session_next"] = saved_id
                    st.rerun()
        with edit_col:
            if st.button(
                "✏️",
                key=f"edit_session_{saved_id}",
                use_container_width=True,
                help="Đổi tên phiên",
            ):
                st.session_state["editing_session_id"] = (
                    None if st.session_state.get("editing_session_id") == saved_id else saved_id
                )
                st.rerun()
        if st.session_state.get("editing_session_id") == saved_id:
            st.text_input(
                "Tên mới (nhấn Enter để lưu)",
                value=saved_record["name"],
                key=f"inline_session_name_{saved_id}",
                on_change=rename_saved_session,
                args=(saved_id,),
            )
    st.caption(
        f"{len(saved_sessions)} phiên đã chạy. "
        "Các phiên chỉ được giữ trong kết nối Streamlit hiện tại."
    )

    st.divider()
    st.subheader("🔑 Cấu hình API")
    provider = st.radio(
        "Nhà cung cấp AI", ["Google Gemini", "OpenAI"],
        horizontal=True, key="api_provider",
    )
    provider_id = "gemini" if provider == "Google Gemini" else "openai"
    secret_name = "GEMINI_API_KEY" if provider_id == "gemini" else "OPENAI_API_KEY"
    try:
        stored_key = str(st.secrets.get(secret_name, "") or "")
    except (FileNotFoundError, KeyError):
        stored_key = ""
    except Exception:
        stored_key = ""
    entered_key = st.text_input(
        f"API key ({'Gemini' if provider_id == 'gemini' else 'OpenAI'})",
        type="password",
        key=f"api_key_{provider_id}",
        placeholder="Nhập API key của bạn",
        help="Bạn có thể nhập riêng trong phiên này hoặc cấu hình tại Streamlit Cloud → App settings → Secrets.",
    )
    key = entered_key.strip() or stored_key.strip()
    if key:
        st.caption("✅ Đã có API key" + (" từ Secrets" if not entered_key else " trong phiên này"))
    else:
        st.caption("⚠️ Chưa có API key. Hãy nhập key để sử dụng chức năng AI.")

    model_choices = (
        ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-flash-lite", "Tự nhập model"]
        if provider_id == "gemini"
        else ["gpt-6-luna", "gpt-6.1-sol", "gpt-5.6-sol", "Tự nhập model"]
    )
    selected_model = st.selectbox(
        "🤖 Model", model_choices, key=f"api_model_{provider_id}",
        help="Model cần được hỗ trợ trong tài khoản API của bạn.",
    )
    if selected_model == "Tự nhập model":
        model = st.text_input(
            "Tên model API", key=f"custom_model_{provider_id}",
            placeholder="Nhập tên model chính xác",
        ).strip()
    else:
        model = selected_model
    if provider_id == "gemini":
        st.markdown("[🔗 Lấy Gemini API key](https://aistudio.google.com/apikey)")
    else:
        st.markdown("[🔗 Lấy OpenAI API key](https://platform.openai.com/api-keys)")
    test_api = st.button("🧪 Kiểm tra kết nối API", use_container_width=True)
    st.caption("Key được che và không ghi vào GitHub hay file phiên. ChatGPT Plus không bao gồm phí sử dụng API.")



def describe_api_error(response, token):
    try:
        payload = response.json()
        item = payload.get("error", {}) if isinstance(payload, dict) else {}
        detail = item.get("message", "") if isinstance(item, dict) else ""
    except ValueError:
        detail = ""
    if not detail:
        detail = response.text[:400]
    detail = str(detail).replace(token, "[API KEY ĐÃ ẨN]")[:650]
    guidance = {
        400: "Kiểm tra tên model, định dạng yêu cầu và quyền truy cập model.",
        401: "API key không hợp lệ hoặc đã hết hiệu lực.",
        403: "Key hoặc dự án không được cấp quyền sử dụng API/model này.",
        404: "Model không tồn tại hoặc chưa có quyền truy cập. Hãy đổi model.",
        429: "Đã vượt hạn mức hoặc tốc độ yêu cầu; kiểm tra quota/billing.",
        500: "Máy chủ AI gặp lỗi tạm thời, hãy thử lại.",
        503: "Dịch vụ AI đang quá tải, hãy thử lại.",
    }.get(response.status_code, "Kiểm tra key, model và cấu hình API.")
    return f"HTTP {response.status_code}: {detail}. {guidance}"


def ai(prompt):
    token = key.strip()
    if not token:
        raise ValueError("Bạn chưa nhập API key. Mở mục Cấu hình API bên trái.")
    name = model.strip()
    if not name or not re.fullmatch(r"[A-Za-z0-9._:-]+", name):
        raise ValueError("Tên model không hợp lệ. Hãy chọn model có sẵn hoặc nhập chính xác.")
    if provider_id == "gemini":
        endpoint = "https://generativelanguage.googleapis.com/v1beta/models/" + name + ":generateContent"
        headers = {"x-goog-api-key": token}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
    else:
        endpoint = "https://api.openai.com/v1/responses"
        headers = {"Authorization": "Bearer " + token}
        data = {"model": name, "input": prompt}
    try:
        response = requests.post(
            endpoint, headers=headers, json=data, timeout=180
        )
    except requests.RequestException as exc:
        raise RuntimeError("Không thể kết nối máy chủ AI. Kiểm tra mạng và thử lại.") from exc
    if not response.ok:
        raise RuntimeError(describe_api_error(response, token))
    try:
        payload = response.json()
        if provider_id == "gemini":
            parts = payload["candidates"][0]["content"]["parts"]
            result = "\n".join(str(part.get("text", "")) for part in parts).strip()
        else:
            chunks = []
            for item in payload.get("output", []):
                if item.get("type") != "message":
                    continue
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        chunks.append(content.get("text", ""))
            result = "\n".join(chunks).strip()
        if not result:
            raise ValueError("Không có nội dung văn bản trong phản hồi.")
        return result
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("AI đã phản hồi nhưng chưa trả về văn bản. Thử đổi model hoặc thử lại.") from exc


if test_api:
    try:
        with st.sidebar:
            with st.spinner("Đang kiểm tra API..."):
                answer = ai("Chỉ trả lời đúng một từ: OK")
            st.success(f"✅ Kết nối {provider} thành công với model {model}.")
    except Exception as exc:
        st.sidebar.error(str(exc))


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


flash = st.session_state.pop("_session_flash", None)
if flash:
    st.success(flash)
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
            if text.strip():
                mark_session_processed(session)
                st.rerun()
            else:
                st.warning("Không tìm thấy nội dung phụ đề.")
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
        if session["source"].strip():
            mark_session_processed(session)
            st.rerun()

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
                if session["translated"].strip():
                    mark_session_processed(session)
                    st.rerun()
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
                    if session["prompts"].strip():
                        mark_session_processed(session)
                        st.rerun()
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
                    if session["metadata"].strip():
                        mark_session_processed(session)
                        st.rerun()
            except Exception as e:
                st.error(str(e))
    output("Copy toàn bộ tiêu đề, mô tả và SEO", session["metadata"])

st.caption("Nút Copy nằm ở góc phải khung nội dung. Các phiên không chia sẻ dữ liệu với nhau trong phiên truy cập hiện tại.")
