import json
import re
import uuid
from io import BytesIO

import requests
import streamlit as st
from PIL import Image
from youtube_transcript_api import YouTubeTranscriptApi
from api_clients import PROVIDERS, generate_text, list_models, validate_base_url

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
FIELDS = ("url", "source", "title", "description", "translated", "prompts", "metadata", "language", "new_title", "new_description", "seo_tags")
FORM_FIELDS = ("url", "language")


def blank_session(name):
    return {
        "name": name, "url": "", "source": "", "title": "", "description": "",
        "translated": "", "prompts": "", "metadata": "", "language": "Tiếng Ba Lan",
        "saved": False, "processed": False, "saved_order": 0,
        "new_title": "", "new_description": "", "seo_tags": "",
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
    st.subheader("🔑 Cấu hình API đa nền tảng")
    provider = st.selectbox(
        "CHỌN NỀN TẢNG AI",
        list(PROVIDERS),
        key="api_provider",
        help="Hỗ trợ các nhà cung cấp API dùng Chat Completions và Anthropic Messages.",
    )
    preset = PROVIDERS[provider]
    provider_id = provider
    secret_name = preset["secret"]
    try:
        stored_key = str(st.secrets.get(secret_name, "") or "") if secret_name else ""
    except Exception:
        stored_key = ""
    entered_key = st.text_input(
        "🔐 API Key",
        key=f"api_key_{provider_id}",
        type="password",
        placeholder="Nhập API key riêng của nền tảng đã chọn",
        help="Chỉ dùng cho phiên hiện tại; có thể cấu hình bằng Streamlit Secrets.",
    )
    key = entered_key.strip() or stored_key.strip()

    base_url = st.text_input(
        "🌐 Base URL",
        value=preset["base_url"],
        key=f"api_base_{provider_id}",
        placeholder="https://your-provider.com/v1",
        help="Nhập gốc của API, ví dụ https://api.groq.com/openai/v1. Không thêm /chat/completions.",
    ).strip()

    model_widget_key = f"api_model_id_{provider_id}"
    pending = st.session_state.pop(f"pending_model_{provider_id}", None)
    if pending:
        st.session_state[model_widget_key] = pending
    model = st.text_input(
        "🤖 Model ID",
        value=preset["model"],
        key=model_widget_key,
        placeholder="Ví dụ: openai/gpt-oss-120b",
        help="Điền đúng model ID mà key của bạn được phép sử dụng.",
    ).strip()

    if st.button("🔎 Quét Model từ API", use_container_width=True, key=f"scan_{provider_id}"):
        try:
            with st.spinner("Đang lấy danh sách Model..."):
                available = list_models(provider, base_url, key)
            st.session_state[f"models_found_{provider_id}"] = available
            if not available:
                st.warning("API không trả về danh sách Model. Bạn vẫn có thể nhập Model ID thủ công.")
        except Exception as exc:
            st.error(str(exc))

    discovered = st.session_state.get(f"models_found_{provider_id}", [])
    if discovered:
        scan_choice = st.selectbox(
            f"Model khả dụng ({len(discovered)})",
            discovered,
            key=f"model_picker_{provider_id}",
        )
        if st.button("📌 Dùng Model đã chọn", key=f"set_model_{provider_id}", use_container_width=True):
            st.session_state[f"pending_model_{provider_id}"] = scan_choice
            st.rerun()

    if key:
        st.caption("✅ Đã nhập API key" + (" (Secrets)" if not entered_key else ""))
    else:
        st.caption("⚠️ Chưa nhập API key.")
    st.caption(
        "Các API tương thích OpenAI dùng endpoint /chat/completions; "
        "Claude dùng /messages. Chỉ nhập Base URL HTTPS công khai, đáng tin cậy."
    )
    test_api = st.button("🧪 Kiểm tra kết nối API", use_container_width=True)
    st.caption("API key không được ghi vào GitHub hoặc dữ liệu phiên. Dịch vụ API có thể tính phí.")


def ai(prompt):
    """Dispatch every translation / prompt / SEO request using the selected provider."""
    return generate_text(provider, base_url, model, key, prompt)


def fetch_best_transcript(video_id):
    """Retrieve a real available subtitle track, including auto-generated captions."""
    tracks = list(YouTubeTranscriptApi().list(video_id))
    if not tracks:
        raise ValueError("Video không có phụ đề để trích xuất.")
    preferred = {"vi": 0, "en": 1, "pl": 2}
    tracks.sort(key=lambda t: (bool(t.is_generated), preferred.get(t.language_code, 10)))
    for track in tracks:
        try:
            segments = track.fetch()
            content = " ".join(
                str(segment.text).strip()
                for segment in segments if getattr(segment, "text", "").strip()
            ).strip()
            if content:
                return content, track.language
        except Exception:
            continue
    raise ValueError("Không đọc được phụ đề. Video có thể đang bị YouTube hạn chế.")


def split_script(text, size=5500):
    """Keep every character, splitting near a sentence/space when possible."""
    pieces = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            split_at = max(text.rfind("\n", start + size // 2, end),
                           text.rfind(". ", start + size // 2, end))
            if split_at > start:
                end = split_at + 1
        pieces.append(text[start:end])
        start = end
    return pieces


def translate_full_script(source_text, target_language, report=None):
    if not source_text.strip():
        raise ValueError("Không có phụ đề hoặc văn bản đầu vào.")
    if len(source_text) > 350000:
        raise ValueError("Văn bản quá dài (trên 350.000 ký tự). Hãy chia thành nhiều video.")
    pieces = split_script(source_text)
    translated_parts = []
    for idx, part in enumerate(pieces, start=1):
        if report:
            report(idx, len(pieces))
        request = (
            f"Dịch chính xác toàn bộ đoạn {idx}/{len(pieces)} sang {target_language}. "
            "Giữ tên nhân vật, mạch truyện, lời thoại, dấu câu và các đoạn xuống dòng. "
            "Viết tự nhiên như người bản xứ, không bỏ câu, không thêm tình tiết. "
            "CHỈ xuất bản dịch, không ghi tiêu đề hay chú thích.\n\n" + part
        )
        translated_parts.append(ai(request))
    return "\n\n".join(translated_parts)


def story_overview(text):
    """Represent the WHOLE long story for generation instead of truncating its ending."""
    if len(text) <= 24000:
        return text
    blocks = split_script(text, 15000)
    summaries = []
    for index, part in enumerate(blocks, start=1):
        summaries.append(ai(
            "Summarize the specific characters, locations, chronological events and "
            "visual details of this part in 180-280 words. Do not invent facts. "
            f"Part {index}/{len(blocks)}:\n" + part
        ))
    return "\n".join(f"Phần {i}: {part}" for i, part in enumerate(summaries, 1))


def load_json_answer(raw, expected):
    left, right = raw.find("{"), raw.rfind("}")
    if left < 0 or right < left:
        raise ValueError("AI không trả về JSON đúng định dạng; hãy chạy lại mục này.")
    try:
        obj = json.loads(raw[left:right + 1])
    except (ValueError, TypeError) as exc:
        raise ValueError("AI trả JSON chưa hợp lệ. Hãy thử tạo lại mục này.") from exc
    if not isinstance(obj, dict) or expected not in obj:
        raise ValueError("Kết quả AI thiếu dữ liệu cần thiết; hãy thử lại.")
    return obj


def create_20_prompts(script, target_language):
    brief = story_overview(script)
    result = ai(
        f"Hãy tạo CHÍNH XÁC 20 mô tả cảnh (image prompts) bằng {target_language}. "
        "Mỗi cảnh bám đúng diễn biến câu chuyện từ đầu đến cuối, mô tả nhân vật nhất quán, "
        "bối cảnh, ánh sáng, góc máy, cảm xúc, phong cách điện ảnh. "
        "Không thêm chữ lên hình. Không bịa sự kiện. "
        'CHỈ xuất một JSON object theo mẫu {"prompts":["cảnh 1",...,"cảnh 20"]}, '
        "không thêm markdown hay lời dẫn.\nCâu chuyện:\n" + brief
    )
    data = load_json_answer(result, "prompts")
    items = data["prompts"]
    if not isinstance(items, list):
        raise ValueError("AI trả về danh sách cảnh không hợp lệ.")
    items = [str(value).strip() for value in items]
    if len(items) != 20 or any(not value for value in items):
        raise ValueError(f"AI mới trả về {len(items)}/20 cảnh hợp lệ. Hãy thử tạo lại.")
    return items


def create_target_metadata(script, original_title, original_description, target_language):
    brief = story_overview(script)
    result = ai(
        f"Soạn nội dung YouTube chính xác và tự nhiên hoàn toàn bằng {target_language}. "
        "Tiêu đề: nếu có tiêu đề gốc hãy dịch sát và diễn đạt hấp dẫn, không thêm tình tiết. "
        "Mô tả: giữ đúng nhân vật, sự kiện, không bịa; dùng icon/emoji phù hợp vừa phải. "
        "SEO: tạo 15 từ khóa thật liên quan bằng ngôn ngữ đích. "
        'Chỉ trả JSON: {"title":"...", "description":"...", "tags":["...", "..."]}, '
        "không markdown.\n"
        f"Tiêu đề gốc: {original_title}\nMô tả gốc: {original_description}\n"
        f"Nội dung video:\n{brief}"
    )
    data = load_json_answer(result, "title")
    title = str(data.get("title", "")).strip()
    description = str(data.get("description", "")).strip()
    tags = data.get("tags", [])
    tags = ", ".join(str(item).strip() for item in tags) if isinstance(tags, list) else str(tags).strip()
    if not title or not description or not tags:
        raise ValueError("AI trả về thiếu tiêu đề, mô tả hoặc từ khóa SEO.")
    return title, description, tags


def parse_saved_prompts(raw_text):
    if not raw_text:
        return []
    try:
        data = json.loads(raw_text)
        if isinstance(data, list):
            return [str(item).strip() for item in data if str(item).strip()]
    except (ValueError, TypeError):
        pass
    old_items = re.split(r"(?m)^\s*\d{1,2}[.)]\s+", raw_text)
    parsed = [part.strip() for part in old_items if part.strip()]
    return parsed if len(parsed) > 1 else [raw_text.strip()]


def render_prompt_blocks(prompts):
    for i, prompt in enumerate(prompts, start=1):
        with st.expander(f"🎞️ Cảnh {i:02d} — 📋 Copy riêng", expanded=(i == 1)):
            st.code(prompt, language=None, wrap_lines=True)



if test_api:
    try:
        with st.sidebar:
            with st.spinner("Đang kiểm tra Base URL, API Key và Model..."):
                answer = ai("Hãy trả lời duy nhất từ OK.")
            st.success(f"✅ Kết nối {provider} thành công với Model {model}.")
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

if st.button("🚀 BẮT ĐẦU TẠO TOÀN BỘ", type="primary",
             use_container_width=True, key=f"run_all_{sid}"):
    if not key.strip():
        st.error("Hãy nhập API key hợp lệ và chọn model trước khi bắt đầu.")
    elif not vid and not session["source"].strip():
        st.warning("Hãy dán link video YouTube hợp lệ trước khi bắt đầu.")
    else:
        progress = st.progress(0, text="Khởi tạo quy trình...")
        try:
            if vid:
                progress.progress(5, text="📥 Đang lấy phụ đề hiện có từ YouTube...")
                source_text, caption_language = fetch_best_transcript(vid)
                session["source"] = source_text
                st.caption(f"Phụ đề được trích xuất từ bản {caption_language}.")
                # YouTube oEmbed may provide a title, but it doesn't return descriptions.
                if not session.get("title", "").strip():
                    try:
                        meta_response = requests.get(
                            "https://www.youtube.com/oembed",
                            params={"url": f"https://www.youtube.com/watch?v={vid}",
                                    "format": "json"},
                            timeout=8,
                        )
                        if meta_response.ok:
                            original_title = str(meta_response.json().get("title", "")).strip()
                            if original_title:
                                session["title"] = original_title
                    except (requests.RequestException, ValueError):
                        pass
            else:
                source_text = session["source"]
                session["source"] = source_text

            if not source_text.strip():
                raise ValueError("Không có phụ đề hoặc văn bản để dịch.")
            mark_session_processed(session)
            # Clear only previously GENERATED fields; never delete original input.
            for field in ("translated", "prompts", "metadata",
                          "new_title", "new_description", "seo_tags"):
                session[field] = ""
            progress.progress(15, text=f"🌍 Đang dịch toàn bộ sang {language}...")

            def report_part(idx, count):
                progress.progress(
                    min(65, 15 + int(50 * idx / count)),
                    text=f"🌍 Dịch phần {idx}/{count} sang {language}...",
                )
            session["translated"] = translate_full_script(
                source_text, language, report=report_part
            )
            progress.progress(70, text=f"🎨 Tạo 20 prompt hình ảnh bằng {language}...")
            prompt_items = create_20_prompts(session["translated"], language)
            session["prompts"] = json.dumps(prompt_items, ensure_ascii=False)
            progress.progress(85, text=f"📝 Tạo tiêu đề, mô tả và SEO bằng {language}...")
            (
                session["new_title"], session["new_description"], session["seo_tags"]
            ) = create_target_metadata(
                session["translated"], session.get("title", ""),
                session.get("description", ""), language
            )
            session["metadata"] = "\n\n".join([
                session["new_title"], session["new_description"], session["seo_tags"]
            ])
            progress.progress(100, text="✅ Đã tạo xong tất cả các phần!")
            st.session_state["_session_flash"] = (
                f"✅ Hoàn tất phiên {session['name']}: phụ đề, bản dịch, "
                f"20 prompt, tiêu đề, mô tả và SEO ({language})."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Quy trình dừng trước khi hoàn tất: {exc}")
            st.info(
                "Các bước đã thành công vẫn được giữ lại trong phiên. "
                "Bạn có thể tạo lại riêng từng mục bằng các nút bên dưới."
            )

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

# Original transcript, title and description are retained internally for processing,
# but only target-language results are shown to the user.

tab_translate, tab_visual, tab_seo = st.tabs(
    ["🌍 Bản dịch", "🎨 20 prompt hình ảnh", "📝 Tiêu đề • Mô tả • SEO"]
)
with tab_translate:
    if st.button("🌍 Dịch lại toàn bộ", key=f"translate_{sid}"):
        if not session["source"].strip():
            st.warning("Hãy trích xuất phụ đề hoặc nhập văn bản trước.")
        else:
            try:
                with st.spinner(f"Đang dịch sang {language}..."):
                    session["translated"] = translate_full_script(session["source"], language)
                mark_session_processed(session)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    st.subheader(f"🌍 Bản dịch hoàn chỉnh ({language})")
    st.caption("📋 Nhấn biểu tượng sao chép góc phải khung bên dưới để Copy toàn bộ.")
    output("📋 Copy toàn bộ bản dịch", session["translated"])

with tab_visual:
    if st.button("🎨 Tạo lại 20 prompt", key=f"prompts_{sid}"):
        base = session["translated"] or session["source"]
        if not base.strip():
            st.warning("Chưa có nội dung câu chuyện.")
        else:
            try:
                with st.spinner(f"Đang tạo 20 prompt bằng {language}..."):
                    generated = create_20_prompts(base, language)
                session["prompts"] = json.dumps(generated, ensure_ascii=False)
                mark_session_processed(session)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    prompt_items = parse_saved_prompts(session.get("prompts", ""))
    if prompt_items:
        st.subheader(f"🎬 {len(prompt_items)} prompt theo cảnh ({language})")
        st.caption("Mở từng cảnh để dùng nút Copy riêng của cảnh đó.")
        render_prompt_blocks(prompt_items)
        all_prompts = "\n\n".join(
            f"Cảnh {index:02d}\n{description}"
            for index, description in enumerate(prompt_items, start=1)
        )
        output("📋 Copy toàn bộ các prompt", all_prompts)
    else:
        st.caption("Chưa có prompt. Hãy nhấn Bắt đầu tạo toàn bộ hoặc Tạo lại 20 prompt.")

with tab_seo:
    if st.button("📝 Tạo lại tiêu đề • mô tả • SEO", key=f"seo_{sid}"):
        base = session["translated"] or session["source"]
        if not base.strip():
            st.warning("Chưa có bản dịch hoặc phụ đề.")
        else:
            try:
                with st.spinner(f"Đang tạo nội dung YouTube bằng {language}..."):
                    (
                        session["new_title"], session["new_description"], session["seo_tags"]
                    ) = create_target_metadata(
                        base, session["title"], session["description"], language
                    )
                session["metadata"] = "\n\n".join([
                    session["new_title"], session["new_description"], session["seo_tags"]
                ])
                mark_session_processed(session)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.subheader(f"🎬 Tiêu đề đã dịch ({language})")
    output("📋 Copy riêng tiêu đề", session.get("new_title", ""))
    st.subheader(f"📝 Mô tả đã dịch ({language})")
    output("📋 Copy riêng mô tả", session.get("new_description", ""))
    st.subheader(f"🔎 Từ khóa SEO ({language})")
    output("📋 Copy riêng từ khóa SEO", session.get("seo_tags", ""))
    if session.get("new_title") or session.get("new_description") or session.get("seo_tags"):
        bundle = "\n\n".join(filter(None, [
            session.get("new_title", ""),
            session.get("new_description", ""),
            session.get("seo_tags", ""),
        ]))
        output("📋 Copy toàn bộ tiêu đề • mô tả • SEO", bundle)
    elif session.get("metadata", "").strip():
        st.caption("Nội dung SEO từ bản cũ (chưa được tách các mục):")
        output("📋 Copy nội dung SEO phiên cũ", session["metadata"])

st.caption("Nút Copy nằm ở góc phải khung nội dung. Các phiên không chia sẻ dữ liệu với nhau trong phiên truy cập hiện tại.")
