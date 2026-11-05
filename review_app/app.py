import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json, uuid
import streamlit as st
from api_clients import generate_text
from transcript_sources import fetch_with_fallback
from review_app.engine import review, youtube_id, render

st.set_page_config(page_title='LMT Review Studio',layout='wide')
st.title('LMT Review Studio')
st.caption('App riêng • Kịch bản review và dựng video theo giọng đọc')
home=Path.home()/'.lmt-review-studio'; home.mkdir(exist_ok=True)
with st.sidebar:
    st.subheader('Cấu hình AI')
    base=st.text_input('API URL',value='https://api.voidd.dev/v1')
    model=st.text_input('Model ID')
    key=st.text_input('API key',type='password')
    st.caption('Khóa chỉ giữ trong phiên hiện tại.')
    st.subheader('Dự án đã lưu')
    for p in sorted(home.glob('*/review.txt'),reverse=True):
        st.download_button(p.parent.name,p.read_text(),file_name=p.parent.name+'.txt',key=str(p))

def call(prompt):
    return generate_text('API bên thứ ba (tùy chỉnh)',base,model,key,prompt,api_format='chat',auth_mode='bearer')

script_tab,video_tab=st.tabs(['1 · Tạo kịch bản','2 · Dựng theo giọng đọc'])
with script_tab:
    name=st.text_input('Tên dự án',value='Review phim')
    language=st.selectbox('Ngôn ngữ đích',['Tiếng Việt','English','Italiano','Español','Français','Deutsch','Português','日本語','한국어','中文','ภาษาไทย','Bahasa Indonesia'])
    minutes=st.slider('Thời lượng lời đọc dự kiến (phút)',5,40,20)
    url=st.text_input('Link YouTube (nếu không dán kịch bản)')
    source=st.text_area('Kịch bản / phụ đề nguồn',height=220,max_chars=350000)
    st.info('Hiện phân tích toàn bộ văn bản nguồn. Chưa nhận diện hình ảnh hoặc những cảnh không có lời thoại. Thời lượng kịch bản là ước tính.')
    if st.button('Bắt đầu phân tích và viết review',type='primary',disabled=not(key and model and (source.strip() or url.strip()))):
        folder=home/(uuid.uuid4().hex[:8]); folder.mkdir()
        cp={}; bar=st.progress(0.0); label=st.empty()
        def progress(value,message):
            bar.progress(value); label.write(message)
            (folder/'checkpoint.json').write_text(json.dumps(cp,ensure_ascii=False))
        try:
            origin='Văn bản đã dán'
            if not source.strip(): source,lang,origin=fetch_with_fallback(youtube_id(url))
            (folder/'source.txt').write_text(source)
            (folder/'provenance.json').write_text(json.dumps({'name':name,'origin':origin,'characters':len(source),'visual_analysis':False,'target_language':language,'desired_minutes':minutes},ensure_ascii=False,indent=2))
            result=review(source,language,minutes,call,cp,progress)
            (folder/'review.txt').write_text(result)
            st.success(f'Đã lưu dự án {folder.name}. Đã phân tích {len(source):,} ký tự từ {origin}.')
            st.text_area('Lời review',result,height=400)
            st.download_button('Tải lời review',result,file_name='review.txt')
        except Exception as exc:
            progress(0.0,'Đã dừng; bản phân tích từng phần được giữ lại.')
            st.error(str(exc))
with video_tab:
    st.write('Ghép cảnh theo ý nghĩa phụ đề nguồn và mốc thời gian phụ đề giọng đọc. Cần kiểm tra bản xem trước trước khi sử dụng.')
    video=st.text_input('Đường dẫn video gốc trên máy')
    audio=st.text_input('Đường dẫn file giọng đọc trên máy')
    source_file=st.file_uploader('Phụ đề video gốc có mốc thời gian',type=['srt'])
    voice_file=st.file_uploader('Phụ đề khớp file giọng đọc',type=['srt'])
    destination=st.text_input('Thư mục lưu kết quả',value=str(home/'exports'/uuid.uuid4().hex[:8]))
    st.caption('Bản đầu cần SRT giọng đọc có sẵn; chưa tự tạo giọng đọc hoặc tự nhận diện âm thanh. Giữ ứng dụng chạy trong lúc xử lý.')
    if st.button('Bắt đầu dựng MP4',disabled=not(key and model and video and audio and source_file and voice_file)):
        try:
            for path in (video,audio):
                if not Path(path).is_file(): raise ValueError('Không tìm thấy file: '+path)
            bar=st.progress(0.0); status=st.empty()
            def report(value,message): bar.progress(value); status.write(message)
            result=render(video,audio,source_file.getvalue().decode('utf-8-sig'),voice_file.getvalue().decode('utf-8-sig'),call,destination,report)
            st.success('Đã lưu: '+str(result)); st.video(str(result))
        except Exception as exc: st.error(str(exc))
