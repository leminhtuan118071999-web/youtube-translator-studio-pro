import re
import requests
import streamlit as st
from youtube_transcript_api import YouTubeTranscriptApi

st.set_page_config(page_title="YouTube Translator Studio Pro", page_icon="🎬",layout="wide")
st.title("🎬 YouTube Translator Studio Pro")
st.caption("Phụ đề YouTube • Dịch • Prompt hình ảnh • SEO • Copy • Thumbnail")
if "source" not in st.session_state: st.session_state.source=""
if "translated" not in st.session_state: st.session_state.translated=""
if "prompts" not in st.session_state: st.session_state.prompts=""
if "metadata" not in st.session_state: st.session_state.metadata=""
with st.sidebar:
    key=st.text_input("Gemini API key",type="password")
    model=st.text_input("Gemini model",value="gemini-2.5-flash")
    language=st.selectbox("Ngôn ngữ đích",["Tiếng Ba Lan","Tiếng Việt","Tiếng Anh","Tiếng Nhật","Tiếng Hàn","Tiếng Pháp","Tiếng Đức","Tiếng Tây Ban Nha"])
    st.caption("Cần Gemini API key riêng. Không lưu key vào GitHub.")
def ai(prompt):
    if not key: raise ValueError("Hãy nhập Gemini API key.")
    r=requests.post("https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",headers={"x-goog-api-key":key},json={"contents":[{"parts":[{"text":prompt}]}]},timeout=180)
    r.raise_for_status()
    return "\n".join(x.get("text","") for x in r.json()["candidates"][0]["content"]["parts"])
def output(title,text):
    st.markdown("**"+title+"**")
    if text:
        st.code(text,language=None,wrap_lines=True)
        st.download_button("⬇️ Tải toàn bộ (.txt)",text,file_name="youtube-output.txt",key=str(abs(hash(title))))
    else: st.caption("Chưa có nội dung.")
url=st.text_input("🔗 Dán link video YouTube")
match=re.search(r"(?:v=|youtu.be/|/shorts/|/live/)([\w-]{11})",url)
vid=match.group(1) if match else None
if st.button("📥 Trích xuất phụ đề"):
    if not vid: st.warning("Hãy nhập link YouTube hợp lệ.")
    else:
        try:
            t=YouTubeTranscriptApi().fetch(vid,languages=["vi","en","pl"])
            st.session_state.source=" ".join(item.text for item in t)
            st.success("Đã trích xuất phụ đề.")
        except Exception as e: st.error("Không thể trích xuất: "+str(e))
if vid:
    st.subheader("🖼️ Thumbnail gốc chất lượng cao")
    from PIL import Image
    from io import BytesIO
    for resolution in ["maxresdefault","sddefault","hqdefault","mqdefault"]:
        try:
            image=requests.get("https://i.ytimg.com/vi/"+vid+"/"+resolution+".jpg",timeout=8)
            image.raise_for_status()
            im=Image.open(BytesIO(image.content))
            if im.width>=300:
                st.image(image.content,width=500)
                st.download_button("⬇️ Tải thumbnail",image.content,file_name="thumbnail-"+vid+".jpg",mime="image/jpeg")
                break
        except Exception: continue
file=st.file_uploader("Tải file phụ đề (.txt)",type=["txt"])
if file and st.button("Dùng file này"): st.session_state.source=file.getvalue().decode("utf-8-sig",errors="replace")
st.session_state.source=st.text_area("📄 Phụ đề / văn bản gốc",value=st.session_state.source,height=190)
output("📋 Copy toàn bộ phụ đề gốc",st.session_state.source)
title=st.text_input("🎬 Tiêu đề gốc")
description=st.text_area("📝 Mô tả gốc",height=110)
output("Copy tiêu đề gốc",title)
output("Copy mô tả gốc",description)
a,b,c=st.tabs(["🌍 Bản dịch","🎨 20 prompt ảnh","📝 YouTube SEO"])
with a:
    if st.button("Dịch toàn bộ",type="primary"):
        try:
            if not st.session_state.source: st.warning("Chưa có văn bản.")
            else:
                parts=[st.session_state.source[i:i+7000] for i in range(0,len(st.session_state.source),7000)]
                results=[]
                for part in parts:
                    results.append(ai("Dịch chính xác sang "+language+", giữ nguyên tên, giọng văn tự nhiên, chỉ xuất bản dịch:\n"+part))
                st.session_state.translated="\n\n".join(results)
        except Exception as e: st.error(str(e))
    output("Copy toàn bộ bản dịch",st.session_state.translated)
with b:
    if st.button("Tạo 20 prompt hình ảnh"):
        try:
            base=(st.session_state.translated or st.session_state.source)[:25000]
            if not base: st.warning("Chưa có câu chuyện.")
            else: st.session_state.prompts=ai("Create exactly 20 numbered cinematic image prompts in English following this story in chronological order. Output only prompts:\n"+base)
        except Exception as e: st.error(str(e))
    output("Copy toàn bộ 20 prompt",st.session_state.prompts)
with c:
    if st.button("Tạo tiêu đề, mô tả và SEO"):
        try:
            original="\n".join([title,description,(st.session_state.translated or st.session_state.source)[:16000]])
            st.session_state.metadata=ai("Viết nội dung YouTube bằng "+language+". Bao gồm tiêu đề 🎬, mô tả 📝 có emoji hợp lý và 15 từ khóa SEO. Tự nhiên, sát nghĩa, không ký tự markdown thừa. Trả nội dung với từng mục phân biệt rõ:\n"+original)
        except Exception as e: st.error(str(e))
    output("Copy toàn bộ tiêu đề, mô tả và SEO",st.session_state.metadata)
st.caption("Nút Copy nằm ở góc phải mỗi khung mã. Trích xuất phụ đề có thể bị YouTube hạn chế trên Streamlit Cloud.")
