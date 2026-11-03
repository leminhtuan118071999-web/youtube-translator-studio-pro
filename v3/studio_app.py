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
    with st.form('new_project',clear_on_submit=True):
        title=st.text_input('Tên dự án mới',placeholder='Ví dụ: Câu chuyện hôm nay')
        if st.form_submit_button('＋ Tạo dự án',type='primary'):
            try:
                st.session_state['project_id']=store.create(title)['id'];st.rerun()
            except ValueError as exc:st.error(str(exc))
    with st.expander('Nhập dự án từ thư mục'):
        import_path=st.text_input('Thư mục dự án đã lưu',key='import_path',placeholder='~/Movies/LMT/Tên-dự-án')
        if st.button('Chọn thư mục dự án'):
            try:
                chosen=store.choose_folder()
                if chosen:st.session_state['import_chosen']=chosen
            except ValueError as exc:st.error(str(exc))
        if st.session_state.get('import_chosen'):st.caption(st.session_state['import_chosen'])
        if st.button('Nhập bản dự án'):
            try:
                imported=store.import_bundle(import_path.strip() or st.session_state.get('import_chosen',''))
                st.session_state['project_id']=imported['id'];st.rerun()
            except (ValueError,OSError,KeyError,TypeError) as exc:st.error('Chưa nhập được dự án: '+str(exc))
    rows=store.listing();by_id={p['id']:p for p in rows}
    if not rows:
        st.info('Tạo dự án đầu tiên để bắt đầu.');st.stop()
    if st.session_state.get('project_id') not in by_id:st.session_state['project_id']=rows[0]['id']
    pid=st.selectbox('Mở dự án',list(by_id),format_func=lambda key:by_id[key]['name']+' · '+key[:6],key='project_id')
    @st.fragment(run_every=2)
    def project_queue():
        st.markdown('**Tiến trình từng dự án**')
        names={'queued':'Đang chờ','running':'Đang dựng','completed':'Hoàn thành','cancelled':'Đã hủy','failed':'Có lỗi','interrupted':'Đã gián đoạn'}
        for item in store.listing():
            render_status=current(store.project_dir(item['id']))
            asr_status=current(store.project_dir(item['id']),'transcribe')
            status=asr_status if asr_status and asr_status['state'] in ('running','queued') else render_status or asr_status
            st.caption(item['name']+' · '+item['id'][:6])
            if status:
                st.progress(status['progress']/100,text=names.get(status['state'],status['state'])+f" · {status['progress']}%")
            else:st.caption('Chưa bắt đầu dựng')
    project_queue()
    st.caption('Tạo hoặc mở dự án khác không dừng video đang dựng. Nếu bấm dựng thêm dự án, dự án đó sẽ chờ đến lượt để tránh quá tải máy.')
    st.caption('Dự án và nguyên liệu lưu trên máy Mac. Giữ máy mở trong lúc dựng; có thể đóng tab trình duyệt.')
project=store.read(store.project_dir(pid)/'project.json');folder=store.project_dir(pid)
locked=busy(folder)
st.subheader(project['name'])

with st.expander('Tên và thông tin dự án'):
    st.caption('Mã dự án: '+pid)
    with st.form('rename_'+pid):
        new_name=st.text_input('Tên riêng của dự án',value=project['name'],max_chars=120,disabled=locked)
        if st.form_submit_button('Lưu tên dự án',disabled=locked):
            try:
                store.rename(pid,new_name);st.rerun()
            except ValueError as exc:st.error(str(exc))


@st.fragment
def save_completed(folder):
    status=current(folder)
    if not status or status['state']!='completed':return
    st.subheader('Lưu video / dự án vào thư mục của bạn')
    key='save_folder_'+str(folder.name)
    if st.button('📁 Chọn thư mục lưu trên Mac',key='pick_'+folder.name):
        try:
            chosen=store.choose_folder()
            if chosen:st.session_state[key]=chosen
        except ValueError as exc:st.error(str(exc))
    destination=st.text_input('Nơi lưu',key=key,placeholder='Ví dụ: ~/Movies/LMT hoặc /Volumes/Ten-o-dia/LMT')
    complete=st.checkbox('Lưu cả dự án và nguyên liệu để chỉnh sửa lại',value=True,key='full_'+folder.name)
    st.caption('Mỗi lần lưu tạo một thư mục mới. Bản đầy đủ gồm video, cấu hình và nguyên liệu; cần đủ dung lượng cho bản sao.')
    if st.button('Lưu vào thư mục đã chọn',type='primary',key='export_'+folder.name):
        try:
            with st.spinner('Đang sao chép kết quả…'):
                location=store.export_run(status['folder'],destination,complete)
            st.session_state['exported_'+folder.name]=location
        except (ValueError,OSError,KeyError,TypeError) as exc:st.error('Chưa lưu được: '+str(exc))
    location=st.session_state.get('exported_'+folder.name)
    if location:
        st.success('Đã lưu thành công.')
        st.code(location,language=None)
        if sys.platform=='darwin' and st.button('Mở nơi vừa lưu',key='open_export_'+folder.name):
            subprocess.run(['open',location],check=True)

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
        completion_key='completed_seen_'+status['run_id']
        if not st.session_state.get(completion_key):
            st.session_state[completion_key]=True
            st.rerun()
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
@st.fragment(run_every=2)
def speech_progress(folder):
    status=current(folder,'transcribe')
    if not status:return
    st.progress(status['progress']/100,text='Phụ đề: '+status['stage'])
    if status.get('error'):st.error(status['error'])
    if status['state'] in ('queued','running'):
        if st.button('Hủy nhận diện giọng đọc',key='cancel_asr_'+status['run_id']):
            (status['folder']/'cancel').touch()
    elif status['state']=='completed':
        key='asr_seen_'+status['run_id']
        if not st.session_state.get(key):st.session_state[key]=True;st.rerun()
        st.success('Đã lưu phụ đề cùng ngôn ngữ với giọng đọc. Kiểm tra tên riêng và những đoạn đọc không rõ trước khi xuất.')
    elif st.button('Làm mới sau khi nhận diện',key='refresh_asr_'+status['run_id']):st.rerun()

progress_panel(folder)
speech_progress(folder)
save_completed(folder)
if locked:st.info('Dự án đang xử lý từ bản đã lưu. Nguyên liệu và cấu hình đang khóa; tạo hoặc mở dự án khác vẫn được.')
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
                        if field=='voice' and name!=project.get('voice') and project.get('captions_origin')=='asr':
                            for key in ('captions','caption_words','caption_source_voice','caption_language','captions_origin'):project.pop(key,None)
                        project[field]=name;store.save(project);st.rerun()
            if project.get(field) and st.button('Bỏ '+label.lower()+' khỏi timeline',disabled=locked,key='remove_'+field):
                project[field]=None
                if field=='voice' and project.get('captions_origin')=='asr':
                    for key in ('captions','caption_words','caption_source_voice','caption_language','captions_origin'):project.pop(key,None)
                store.save(project);st.rerun()
    with subtitle_tab:
        st.markdown('### Tự tạo phụ đề từ file giọng đọc')
        st.caption('Nhận diện ngay trên máy, tự phát hiện ngôn ngữ và mốc từng từ; không dịch sang ngôn ngữ khác. Lần đầu cần Internet để tải model. Sau đó có thể nhận diện offline với model đã lưu.')
        asr_model=st.selectbox('Model nhận diện',['small','base','tiny'],format_func=lambda x:{'small':'Small — ưu tiên độ chính xác','base':'Base — cân bằng','tiny':'Tiny — thử nhanh, độ chính xác thấp hơn'}[x],disabled=locked,key='asr_model_'+pid)
        if not project.get('voice'):st.info('Tải và lưu file giọng đọc ở mục Âm thanh trước.')
        if st.button('🎙️ Nghe giọng đọc và tạo phụ đề',type='primary',disabled=locked or not project.get('voice')):
            launch(dict(project,asr_model=asr_model),'transcribe');st.rerun()
        if project.get('captions_origin')=='asr':
            st.success('Đã nhận diện ngôn ngữ: '+project.get('caption_language',''))
        st.divider()
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
                    for key in ('caption_words','caption_source_voice','caption_language','captions_origin'):project.pop(key,None)
                store.save(project);st.rerun()
        if project.get('captions'):
            st.success('Đang dùng file SRT đã lưu.')
            if st.button('Bỏ SRT để dùng văn bản',disabled=locked):
                for key in ('captions','caption_words','caption_source_voice','caption_language','captions_origin'):project.pop(key,None)
                store.save(project);st.rerun()
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
                subtitle_mode=st.selectbox('Cách hiện phụ đề nhận diện',['words','sentence'],index=0 if cfg.get('subtitle_mode','words')=='words' else 1,format_func=lambda value:'Tô sáng từng từ đang đọc' if value=='words' else 'Theo cụm lời · không tô từng từ',disabled=locked)
            if st.form_submit_button('Lưu cấu hình xuất',disabled=locked):
                project['settings']=dict(aspect=aspect,resolution=resolution,fit=fit,transition=transition,sync_voice=sync,original_volume=original/100,music_volume=music/100,voice_volume=voice/100,duck=duck,font_size=font,subtitle_mode=subtitle_mode)
                store.save(project);st.rerun()
        st.caption('Lưu timeline và cấu hình trước khi dựng. Dựng từ các giá trị đã lưu, giữ cả các lần xuất trước.')
        if project['scenes']:
            durations=plan(project,folder)
            st.metric('Thời lượng dự kiến',f'{sum(durations):.1f} giây')
            if st.button('🎬 Bắt đầu dựng MP4',type='primary',disabled=locked):
                launch(project);st.rerun()
except (ValueError,OSError,RuntimeError,json.JSONDecodeError) as exc:
    st.error(str(exc))
