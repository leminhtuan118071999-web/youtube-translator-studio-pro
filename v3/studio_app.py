"""Browser UI for the local Mac renderer. Bind only to localhost."""
from pathlib import Path
import json
import sys
import os
import subprocess
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
import streamlit as st
from v3 import projects as store
from v3.render import probe, plan
from v3.render_worker import launch, busy, current, delete_all_projects

st.set_page_config(page_title='LMT Video Editor V3',page_icon='🎞️',layout='wide')
st.markdown('''<style>.stApp{background:#0b1320}h1,h2,h3{color:#e4ecfb}.block-container{max-width:1240px;padding-top:2rem}div.stButton>button[kind=primary]{background:#357cef}section[data-testid=stSidebar]{background:#101c2b}</style>''',unsafe_allow_html=True)
st.title('🎞️ LMT Video Editor · V3')
with st.sidebar:
    st.header('Dự án của tôi')
    with st.form('new_project',clear_on_submit=True):
        title=st.text_input('Tên dự án mới',placeholder='Ví dụ: Câu chuyện hôm nay')
        if st.form_submit_button('＋ Tạo dự án',type='primary',disabled=st.session_state.get('delete_all_pending',False)):
            try:
                st.session_state['project_id']=store.create(title)['id'];st.rerun()
            except ValueError as exc:st.error(str(exc))
    rows=store.listing();by_id={p['id']:p for p in rows}
    if st.session_state.get('project_id') not in by_id and rows:st.session_state['project_id']=rows[0]['id']
    @st.fragment(run_every=2)
    def project_queue():
        st.markdown('**Các dự án đã tạo**')
        if st.session_state.get('delete_all_pending'):
            try:
                result=delete_all_projects()
                if result['waiting']:st.info('Đang dừng tác vụ trước khi xóa tất cả phiên…')
                else:
                    st.session_state['delete_all_pending']=False
                    st.session_state.pop('project_id',None)
                    st.rerun()
            except (ValueError,OSError) as exc:
                st.session_state['delete_all_pending']=False;st.error('Chưa xóa được: '+str(exc))
        names={'queued':'Đang chờ','running':'Đang dựng','completed':'Hoàn thành','cancelled':'Đã hủy','failed':'Có lỗi','interrupted':'Đã gián đoạn'}
        for item in store.listing():
            render_status=current(store.project_dir(item['id']))
            asr_status=current(store.project_dir(item['id']),'transcribe')
            cutout_status=current(store.project_dir(item['id']),'cutout')
            status=cutout_status if cutout_status and cutout_status['state'] in ('running','queued') else asr_status if asr_status and asr_status['state'] in ('running','queued') else render_status or asr_status
            if st.button(item['name'],key='open_project_'+item['id'],type='primary' if st.session_state.get('project_id')==item['id'] else 'secondary',disabled=st.session_state.get('delete_all_pending',False),use_container_width=True):
                st.session_state['project_id']=item['id'];st.rerun()
            if status:
                st.progress(status['progress']/100,text=names.get(status['state'],status['state'])+f" · {status['progress']}% · "+status['stage'])
            else:st.caption('Chưa bắt đầu dựng')
    project_queue()
    if rows:
        if st.button('Xóa tất cả phiên',disabled=st.session_state.get('delete_all_pending',False),use_container_width=True):st.session_state['confirm_delete_all']=True
        if st.session_state.get('confirm_delete_all'):
            st.warning('Xóa toàn bộ dự án, nguyên liệu và kết quả nội bộ V3. Tác vụ đang chạy sẽ bị hủy. Các bản đã lưu vào thư mục bạn chọn và khóa Pixabay vẫn được giữ.')
            yes,no=st.columns(2)
            if yes.button('Xác nhận xóa tất cả',type='primary'):
                st.session_state['confirm_delete_all']=False;st.session_state['delete_all_pending']=True;st.rerun()
            if no.button('Giữ lại'):st.session_state['confirm_delete_all']=False;st.rerun()
    if not rows:st.stop()
    pid=st.session_state['project_id']
project=store.read(store.project_dir(pid)/'project.json');folder=store.project_dir(pid)
locked=busy(folder) or st.session_state.get('delete_all_pending',False)
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
    if key not in st.session_state:
        default_folder=''
        if sys.platform=='win32':
            try:default_folder=store.read(store.home()/'windows-preferences.json').get('export_folder','')
            except (OSError,ValueError):pass
        st.session_state[key]=project.get('export_destination') or default_folder
    if st.button('📁 Chọn thư mục lưu',key='pick_'+folder.name,disabled=locked):
        try:
            chosen=store.choose_folder()
            if chosen:st.session_state[key]=chosen
        except ValueError as exc:st.error(str(exc))
    destination=st.text_input('Nơi lưu',key=key,placeholder='Ví dụ: ~/Movies/LMT hoặc /Volumes/Ten-o-dia/LMT',disabled=locked)
    complete=st.checkbox('Lưu cả dự án và nguyên liệu để chỉnh sửa lại',value=project.get('export_include_assets',True) if locked else store.story_defaults()['export_include_assets'],key=('full_'+folder.name if locked else 'export_include_assets_default'),disabled=locked)
    if not locked:st.session_state['full_'+folder.name]=complete
    if not locked and complete != store.story_defaults()['export_include_assets']:
        store.save_story_defaults(dict(store.story_defaults(),export_include_assets=complete))
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
        if sys.platform in ('darwin','win32') and st.button('Mở nơi vừa lưu',key='open_export_'+folder.name):
            if sys.platform=='win32':os.startfile(location)
            else:subprocess.run(['open',location],check=True)

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
            if sys.platform in ('darwin','win32') and st.button('Mở thư mục video',key='finder_'+status['run_id']):
                if sys.platform=='win32':os.startfile(str(output.parent))
                else:subprocess.run(['open',str(output.parent)],check=True)
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
if locked:st.info('Dự án đang xử lý · cấu hình đã khóa.')
story_tab,=st.tabs(['05 · Dựng kiểu video mẫu'])
try:
    export_settings={}
    def output_panel():
        cfg=project['settings'] if locked else store.output_defaults()
        with st.expander('Cấu hình xuất video',expanded=False):
            a,b=st.columns(2)
            with a:
                aspect=st.selectbox('Khung hình',['9:16','16:9','1:1'],index=['9:16','16:9','1:1'].index(cfg['aspect']),disabled=locked)
                resolution=st.selectbox('Độ phân giải',[1080,720],index=[1080,720].index(cfg['resolution']),disabled=locked)
                fit=st.selectbox('Căn hình',['contain','cover'],index=['contain','cover'].index(cfg['fit']),format_func=lambda v:'Giữ toàn bộ · viền đen' if v=='contain' else 'Lấp đầy · cắt phần thừa',disabled=locked)
                transition=st.selectbox('Chuyển cảnh',['cut','fade'],index=['cut','fade'].index(cfg['transition']),format_func=lambda v:'Cắt thẳng' if v=='cut' else 'Mờ qua đen',disabled=locked)
            with b:
                sync=st.checkbox('Tự khớp timeline theo thời lượng giọng đọc',value=cfg['sync_voice'],disabled=locked)
                original=st.slider('Âm lượng gốc trong video (%)',0,100,round(cfg['original_volume']*100),disabled=locked)
                music=st.slider('Âm lượng nhạc nền (%)',0,100,round(cfg['music_volume']*100),disabled=locked)
                voice=st.slider('Âm lượng giọng đọc (%)',0,200,round(cfg['voice_volume']*100),disabled=locked)
                duck=st.checkbox('Tự hạ nhạc khi có lời đọc',value=cfg['duck'],disabled=locked)
                font=st.slider('Cỡ chữ phụ đề',16,64,cfg['font_size'],disabled=locked)
                subtitle_mode=st.selectbox('Cách hiện phụ đề nhận diện',['words','sentence'],index=0 if cfg.get('subtitle_mode','words')=='words' else 1,format_func=lambda value:'Tô sáng từng từ đang đọc' if value=='words' else 'Theo cụm lời · không tô từng từ',disabled=locked)
            current_settings=dict(aspect=aspect,resolution=resolution,fit=fit,transition=transition,sync_voice=sync,original_volume=original/100,music_volume=music/100,voice_volume=voice/100,duck=duck,font_size=font,subtitle_mode=subtitle_mode)
            export_settings.update(current_settings)
            if not locked and current_settings != store.output_defaults():
                store.save_output_defaults(current_settings)
            if st.button('Lưu cấu hình xuất',disabled=locked):
                project['settings']=dict(aspect=aspect,resolution=resolution,fit=fit,transition=transition,sync_voice=sync,original_volume=original/100,music_volume=music/100,voice_volume=voice/100,duck=duck,font_size=font,subtitle_mode=subtitle_mode)
                store.save_output_defaults(project['settings'])
                store.save(project);st.rerun()
    with story_tab:
        from v3.story_ui import panel
        save_inputs=panel(project,folder,locked,output_panel=output_panel)
        st.divider()
        story_mode=project.get('story',{}).get('enabled',False)
        ready=bool(project['scenes'])
        if story_mode:
            from v3.story import voice_duration
            ready=bool(project.get('voice') and project['story'].get('image') and (project['story'].get('backgrounds') or project['story'].get('pixabay_selected')))
            if project.get('voice'):st.metric('Thời lượng mở đầu + giọng chính',f'{voice_duration(project,folder):.1f} giây')

        elif project['scenes']:
            durations=plan(project,folder)
            st.metric('Thời lượng dự kiến',f'{sum(durations):.1f} giây')
        save_completed(folder)
        if st.button('🎬 Bắt đầu dựng MP4',type='primary',disabled=locked):
            if not save_inputs():st.stop()
            project['settings']=dict(export_settings)
            from v3.story import validate_start
            validate_start(project,st.session_state.get('save_folder_'+pid,''))
            project['export_destination']=st.session_state.get('save_folder_'+pid,'').strip()
            project['export_include_assets']=st.session_state.get('full_'+pid,True)
            store.save(project)
            launch(project);st.rerun()
except (ValueError,OSError,RuntimeError,json.JSONDecodeError) as exc:
    st.error(str(exc))
