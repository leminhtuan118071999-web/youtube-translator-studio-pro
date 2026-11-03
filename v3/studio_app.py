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
st.caption('Cấu hình xuất → thêm nguyên liệu và bố cục → chọn nơi lưu → dựng MP4 trên máy của bạn')
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
            cutout_status=current(store.project_dir(item['id']),'cutout')
            status=cutout_status if cutout_status and cutout_status['state'] in ('running','queued') else asr_status if asr_status and asr_status['state'] in ('running','queued') else render_status or asr_status
            st.caption(item['name']+' · '+item['id'][:6])
            if status:
                st.progress(status['progress']/100,text=names.get(status['state'],status['state'])+f" · {status['progress']}% · "+status['stage'])
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


def save_completed(folder):
    status=current(folder)
    st.subheader('Lưu video / dự án vào thư mục của bạn')
    key='save_folder_'+str(folder.name)
    if key not in st.session_state:st.session_state[key]=project.get('export_destination','')
    if st.button('📁 Chọn thư mục lưu trên Mac',key='pick_'+folder.name,disabled=locked):
        try:
            chosen=store.choose_folder()
            if chosen:st.session_state[key]=chosen
        except ValueError as exc:st.error(str(exc))
    destination=st.text_input('Nơi lưu',key=key,placeholder='Ví dụ: ~/Movies/LMT hoặc /Volumes/Ten-o-dia/LMT',disabled=locked)
    complete=st.checkbox('Lưu cả dự án và nguyên liệu để chỉnh sửa lại',value=project.get('export_include_assets',True),key='full_'+folder.name,disabled=locked)
    st.caption('Mỗi lần lưu tạo một thư mục mới. Bản đầy đủ gồm video, cấu hình và nguyên liệu; cần đủ dung lượng cho bản sao.')
    st.caption('Chọn trước khi dựng: hoàn thành sẽ tự lưu vào đây. Để trống nếu chỉ muốn giữ kết quả trong app.')
    if status and status.get('details',{}).get('export_error'):st.warning('Video đã dựng xong nhưng chưa sao chép được: '+status['details']['export_error'])
    if status and status['state']=='completed' and st.button('Lưu vào thư mục đã chọn',type='primary',key='export_'+folder.name,disabled=locked):
        try:
            with st.spinner('Đang sao chép kết quả…'):
                location=store.export_run(status['folder'],destination,complete)
            st.session_state['exported_'+folder.name]=location
        except (ValueError,OSError,KeyError,TypeError) as exc:st.error('Chưa lưu được: '+str(exc))
    location=st.session_state.get('exported_'+folder.name) or (status.get('details',{}).get('export_location') if status else None)
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
if locked:st.info('Dự án đang xử lý từ bản đã lưu. Nguyên liệu và cấu hình đang khóa; tạo hoặc mở dự án khác vẫn được.')
output_tab,story_tab=st.tabs(['04 · Xuất video','05 · Dựng kiểu video mẫu'])
try:
    with output_tab:
        cfg=project['settings']
        with st.container():
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
            if st.button('Lưu cấu hình xuất',disabled=locked):
                project['settings']=dict(aspect=aspect,resolution=resolution,fit=fit,transition=transition,sync_voice=sync,original_volume=original/100,music_volume=music/100,voice_volume=voice/100,duck=duck,font_size=font,subtitle_mode=subtitle_mode)
                store.save(project);st.rerun()
    with story_tab:
        from v3.story_ui import panel
        save_inputs=panel(project,folder,locked)
        st.divider()
        st.caption('Bấm bắt đầu để tự lưu thông tin vừa nhập, tách nền, chuẩn bị video nền, ghép giọng, tạo phụ đề và xuất vào nơi đã chọn.')
        story_mode=project.get('story',{}).get('enabled',False)
        ready=bool(project['scenes'])
        if story_mode:
            from v3.story import voice_duration
            st.info('Đang dùng chế độ ảnh nhân vật + video nền từ mục 05.')
            ready=bool(project.get('voice') and project['story'].get('image') and (project['story'].get('backgrounds') or project['story'].get('pixabay_selected')))
            if project.get('voice'):st.metric('Thời lượng mở đầu + giọng chính',f'{voice_duration(project,folder):.1f} giây')

        elif project['scenes']:
            durations=plan(project,folder)
            st.metric('Thời lượng dự kiến',f'{sum(durations):.1f} giây')
        save_completed(folder)
        if st.button('🎬 Bắt đầu dựng MP4',type='primary',disabled=locked):
            if not save_inputs():st.stop()
            project['settings']=dict(aspect=aspect,resolution=resolution,fit=fit,transition=transition,sync_voice=sync,original_volume=original/100,music_volume=music/100,voice_volume=voice/100,duck=duck,font_size=font,subtitle_mode=subtitle_mode)
            from v3.story import validate_start
            validate_start(project,st.session_state.get('save_folder_'+pid,''))
            project['export_destination']=st.session_state.get('save_folder_'+pid,'').strip()
            project['export_include_assets']=st.session_state.get('full_'+pid,True)
            store.save(project)
            launch(project);st.rerun()
except (ValueError,OSError,RuntimeError,json.JSONDecodeError) as exc:
    st.error(str(exc))
