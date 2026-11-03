"""Browser UI for the local Mac renderer. Bind only to localhost."""
from pathlib import Path
import json
import sys
import subprocess
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import streamlit as st
from v3 import projects as store
from v3.render import probe, plan
from v3.render_worker import launch, busy, current

st.set_page_config(page_title='LMT Video Editor V3',page_icon='🎞️',layout='wide')
st.markdown('''<style>.stApp{background:#0b1320}h1,h2,h3{color:#e4ecfb}.block-container{max-width:1240px;padding-top:2rem}div.stButton>button[kind=primary]{background:#357cef}section[data-testid=stSidebar]{background:#101c2b}</style>''',unsafe_allow_html=True)
st.title('🎞️ LMT Video Editor · V3')
st.caption('Tải nguyên liệu → sắp xếp cảnh → ghép giọng đọc → xuất MP4 trên máy của bạn')
with st.sidebar:
    st.header('Dự án của tôi')
    with st.form('new_project'):
        title=st.text_input('Tên dự án mới',placeholder='Ví dụ: Câu chuyện hôm nay')
        if st.form_submit_button('＋ Tạo dự án',type='primary'):
            st.session_state['project_id']=store.create(title)['id'];st.rerun()
    rows=store.listing();by_id={p['id']:p for p in rows}
    if not rows:
        st.info('Tạo dự án đầu tiên để bắt đầu.');st.stop()
    if st.session_state.get('project_id') not in by_id:st.session_state['project_id']=rows[0]['id']
    pid=st.selectbox('Mở dự án',list(by_id),format_func=lambda key:by_id[key]['name'],key='project_id')
    st.caption('Dự án và nguyên liệu lưu trên máy Mac. Giữ máy mở trong lúc dựng; có thể đóng tab trình duyệt.')
project=store.read(store.project_dir(pid)/'project.json');folder=store.project_dir(pid)
locked=busy(folder)
st.subheader(project['name'])

@st.fragment(run_every=2)
def progress_panel(folder):
    status=current(folder)
    if not status:return
    st.progress(status['progress']/100,text=status['stage'])
    if status.get('error'):st.error(status['error'])
    if status['state'] in ('queued','running'):
        if st.button('Hủy dựng video',key='cancel_'+status['run_id']):
            (status['folder']/'cancel').touch();st.info('Đã gửi yêu cầu hủy.')
    elif status['state']=='completed':
        st.success('Video đã dựng xong. Dự án và file xuất được giữ trên máy.')
        output=status['folder']/'output.mp4'
        if output.exists():
            st.video(str(output))
            # Avoid loading arbitrarily large output into browser download memory.
            if output.stat().st_size<=250*1024*1024:
                with output.open('rb') as f: st.download_button('Tải MP4',f,file_name='lmt-video.mp4',mime='video/mp4',key='mp4_'+status['run_id'])
            st.code(str(output),language=None)
            if sys.platform == 'darwin' and st.button('Mở thư mục video',key='finder_'+status['run_id']):
                subprocess.run(['open',str(output.parent)],check=True)
    else:st.warning(status['stage'])
    if st.button('Làm mới trạng thái và các nút'): st.rerun()
progress_panel(folder)
if locked:st.info('Dự án đang được dựng từ bản đã lưu. Nguyên liệu và cấu hình đang khóa. Sau khi xong, nhấn Làm mới để chỉnh tiếp.')
media_tab,audio_tab,subtitle_tab,output_tab=st.tabs(['01 · Ảnh & video','02 · Âm thanh','03 · Phụ đề','04 · Xuất video'])
try:
    with media_tab:
        with st.form('upload_'+pid,clear_on_submit=True):
            files=st.file_uploader('Thêm ảnh hoặc video',type=sorted(x[1:] for x in store.MEDIA),accept_multiple_files=True,disabled=locked)
            if st.form_submit_button('Lưu nguyên liệu',disabled=locked):
                for file in sorted(files or [],key=lambda f:store.natural(f.name)):
                    name=store.upload(folder,file,store.MEDIA)
                    info=probe(store.asset(folder,name))
                    if not info['video']:raise ValueError('Tệp không có hình ảnh/video hợp lệ.')
                    project['scenes'].append(dict(id=name,file=name,name=Path(file.name).name[:150],duration=8.0 if Path(name).suffix in store.IMAGES else round(max(.1,info['duration']),2)))
                store.save(project);st.rerun()
        if project['scenes']:
            st.caption('Tên tệp được xếp tự nhiên: SC2 trước SC10. Chỉnh cột Thứ tự và Thời lượng rồi lưu timeline. Video ngắn sẽ lặp lại nếu cần kéo dài.')
            edited=st.data_editor([{'ID':s['id'],'Thứ tự':i+1,'Tên tệp':s['name'],'Thời lượng (giây)':s['duration'],'Dùng':True} for i,s in enumerate(project['scenes'])],
                hide_index=True,disabled=locked or ['ID','Tên tệp'],column_config={'ID':None,'Thứ tự':st.column_config.NumberColumn(min_value=1,step=1),'Thời lượng (giây)':st.column_config.NumberColumn(min_value=.1,max_value=3600,step=.1)},key='timeline_'+pid)
            if st.button('Lưu timeline',disabled=locked):
                old={s['id']:s for s in project['scenes']}
                project['scenes']=[dict(old[row['ID']],duration=float(row['Thời lượng (giây)'])) for row in sorted(edited,key=lambda r:r['Thứ tự']) if row['Dùng']]
                store.save(project);st.rerun()
            chosen=st.selectbox('Xem nguyên liệu',[s['file'] for s in project['scenes']],format_func=lambda key:next(s['name'] for s in project['scenes'] if s['file']==key))
            path=store.asset(folder,chosen)
            if path.suffix in store.IMAGES:st.image(str(path),width=360)
            else:st.video(str(path))
        else:st.info('Thêm ảnh hoặc video để tạo timeline.')
    with audio_tab:
        for field,label in [('voice','Giọng đọc'),('music','Nhạc nền')]:
            if project.get(field):st.audio(str(store.asset(folder,project[field])))
            with st.form(field+'_'+pid,clear_on_submit=True):
                uploaded=st.file_uploader(label,type=sorted(x[1:] for x in store.AUDIO),key='file_'+field,disabled=locked)
                if st.form_submit_button('Lưu '+label.lower(),disabled=locked):
                    if uploaded:
                        name=store.upload(folder,uploaded,store.AUDIO)
                        if not probe(store.asset(folder,name))['audio']:raise ValueError('Tệp cần có âm thanh.')
                        project[field]=name;store.save(project);st.rerun()
            if project.get(field) and st.button('Bỏ '+label.lower()+' khỏi timeline',disabled=locked,key='remove_'+field):
                project[field]=None;store.save(project);st.rerun()
    with subtitle_tab:
        st.caption('SRT có mốc thời gian được ưu tiên. Phụ đề tạo từ văn bản chỉ là ước lượng theo độ dài chữ, cần kiểm tra lại trước khi đăng.')
        with st.form('captions_'+pid,clear_on_submit=True):
            srt=st.file_uploader('Phụ đề SRT (UTF-8)',type=['srt'],disabled=locked)
            v2=st.file_uploader('Hoặc lấy lời kể từ file Xuất phiên JSON của V2',type=['json'],disabled=locked)
            text=st.text_area('Văn bản phụ đề / lời kể',value=project.get('subtitle_text',''),height=180,disabled=locked)
            if st.form_submit_button('Lưu phụ đề',disabled=locked):
                if v2:
                    if v2.size > 32*1024*1024: raise ValueError('File phiên V2 vượt 32 MB.')
                    imported=json.load(v2)
                    if not isinstance(imported,dict) or not isinstance(imported.get('data',imported),dict):
                        raise ValueError('File JSON phải là phiên V2 hợp lệ.')
                    text=imported.get('data',imported).get('translated','')
                    if not isinstance(text,str):raise ValueError('File JSON chưa có bản dịch hợp lệ.')
                if len(text)>350000:raise ValueError('Văn bản phụ đề quá dài.')
                project['subtitle_text']=text
                if srt:
                    if srt.size > 4*1024*1024:raise ValueError('File SRT vượt 4 MB.')
                    project['captions']=store.upload(folder,srt,{'.srt'})
                store.save(project);st.rerun()
        if project.get('captions'):
            st.success('Đang dùng file SRT đã lưu.')
            if st.button('Bỏ SRT để dùng văn bản',disabled=locked):project['captions']=None;store.save(project);st.rerun()
    with output_tab:
        cfg=project['settings']
        with st.form('settings_'+pid):
            a,b=st.columns(2)
            with a:
                aspect=st.selectbox('Khung hình',['9:16','16:9','1:1'],index=['9:16','16:9','1:1'].index(cfg['aspect']),disabled=locked)
                resolution=st.selectbox('Độ phân giải',[1080,720],index=[1080,720].index(cfg['resolution']),disabled=locked)
                fit=st.selectbox('Căn hình',['contain','cover'],index=['contain','cover'].index(cfg['fit']),format_func=lambda v:'Giữ toàn bộ · viền đen' if v=='contain' else 'Lấp đầy · cắt phần thừa',disabled=locked)
                transition=st.selectbox('Chuyển cảnh',['cut','fade'],index=['cut','fade'].index(cfg['transition']),format_func=lambda v:'Cắt thẳng' if v=='cut' else 'Mờ qua đen',disabled=locked)
            with b:
                sync=st.checkbox('Tự khớp timeline theo thời lượng giọng đọc',value=cfg['sync_voice'],disabled=locked)
                st.caption('Chia thời lượng cảnh theo tỷ lệ đã nhập; không tự nhận diện nội dung trong clip.')
                original=st.slider('Âm lượng gốc trong video (%)',0,100,round(cfg['original_volume']*100),disabled=locked)
                music=st.slider('Âm lượng nhạc nền (%)',0,100,round(cfg['music_volume']*100),disabled=locked)
                voice=st.slider('Âm lượng giọng đọc (%)',0,200,round(cfg['voice_volume']*100),disabled=locked)
                duck=st.checkbox('Tự hạ nhạc khi có lời đọc',value=cfg['duck'],disabled=locked)
                font=st.slider('Cỡ chữ phụ đề',16,64,cfg['font_size'],disabled=locked)
            if st.form_submit_button('Lưu cấu hình xuất',disabled=locked):
                project['settings']=dict(aspect=aspect,resolution=resolution,fit=fit,transition=transition,sync_voice=sync,original_volume=original/100,music_volume=music/100,voice_volume=voice/100,duck=duck,font_size=font)
                store.save(project);st.rerun()
        st.caption('Lưu timeline và cấu hình trước khi dựng. Dựng từ các giá trị đã lưu, giữ cả các lần xuất trước.')
        if project['scenes']:
            durations=plan(project,folder)
            st.metric('Thời lượng dự kiến',f'{sum(durations):.1f} giây')
            if st.button('🎬 Bắt đầu dựng MP4',type='primary',disabled=locked):
                launch(project);st.rerun()
except (ValueError,OSError,RuntimeError,json.JSONDecodeError) as exc:
    st.error(str(exc))
