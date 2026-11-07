"""Storytelling inputs and preview, separate from the manual timeline editor."""
import json
from pathlib import Path
import streamlit as st
import pandas as pd
from . import projects as store
from .render import probe, validate_srt
from .render_worker import launch,current
from . import pixabay


def panel(project,folder,locked,output_panel=None):
    pid=project['id'];cfg=project.get('story',{})
    prefs=dict(store.STORY_DEFAULTS, **cfg) if locked else store.story_defaults()
    st.subheader('Ảnh nhân vật trên video nền · như video mẫu')
    with st.expander('**Cấu hình Pixabay** · chỉ lưu khóa trên máy này'):
        st.link_button('Lấy khóa API trên Pixabay','https://pixabay.com/api/docs/')
        st.caption('Đã lưu khóa trên máy.' if pixabay.api_key() else 'Chưa lưu khóa.')
        with st.form('pixabay_key_'+pid,clear_on_submit=True):
            key=st.text_input('Khóa Pixabay API',type='password')
            if st.form_submit_button('Lưu khóa Pixabay'):
                try:pixabay.save_key(key);st.success('Đã lưu khóa trên máy; không đưa vào bản xuất dự án.')
                except ValueError as exc:st.error(str(exc))
    pending='theme_query_pending_'+pid
    if pending in st.session_state:st.session_state['pixabay_query_'+pid]=st.session_state.pop(pending)
    auto_theme=st.checkbox('Tự chọn chủ đề video nền theo ảnh thumbnail',value=prefs['auto_theme'],disabled=locked)
    query=st.text_input('Từ khóa tìm video nền Pixabay',value=cfg.get('query','forest sunlight'),max_chars=100,key='pixabay_query_'+pid,disabled=locked)
    theme_cache=folder/'thumbnail-theme.json'
    if theme_cache.exists():
        detected=store.read(theme_cache)
        if detected.get('source_image')==cfg.get('image') and detected.get('query'):
            st.caption('Chủ đề gợi ý: '+detected['label']+' · '+detected['query'])
    choice_cache=folder/'thumbnail-theme-choice.json'
    if auto_theme and choice_cache.exists():
        choice=store.read(choice_cache)
        if choice.get('source_image')==cfg.get('image') and not choice.get('automatic'):
            st.warning('Chưa nhận diện rõ chủ đề; đang dùng từ khóa: '+choice.get('query',''))
    if st.button('Tìm video trên Pixabay',disabled=locked,key='pixabay_search_'+pid):
        try:
            with st.spinner('Đang tìm video trên Pixabay…'):st.session_state['pixabay_hits_'+pid]=pixabay.search(query)
        except (ValueError,OSError,json.JSONDecodeError) as exc:st.error(str(exc))
    hits={str(h['id']):h for h in cfg.get('pixabay_selected',[])}
    hits.update({str(h['id']):h for h in st.session_state.get('pixabay_hits_'+pid,[])})
    records=store.read(folder/'pixabay-downloads.json') if (folder/'pixabay-downloads.json').exists() else cfg.get('downloaded',{})
    st.caption(f'Đã tải {len(records)}/15 video Pixabay.')
    selection_key='pixabay_selection_'+pid
    if st.session_state.pop('restore_story_selection_'+pid,False):
        st.session_state[selection_key]=[str(h['id']) for h in cfg.get('pixabay_selected',[])]
    if selection_key not in st.session_state:st.session_state[selection_key]=[str(h['id']) for h in cfg.get('pixabay_selected',[])]
    if hits and st.button('Tự chọn tối đa 15 video từ kết quả',disabled=locked,key='pixabay_auto_'+pid):
        chosen=[];new_count=0
        for key in hits:
            if len(chosen)>=15:break
            if key in records:chosen.append(key)
            elif len(records)+new_count<15:chosen.append(key);new_count+=1
        st.session_state[selection_key]=chosen
    for hit in list(hits.values())[:6]:
        # Explicit source attribution, no autoplay/hotlink downloads.
        st.markdown(f"[Pixabay · video {hit['id']}]({hit['pageURL']}) · {hit['width']}×{hit['height']} · {hit['duration']} giây")
    with st.container():
        enabled=st.checkbox('Dựng video nền + giọng đọc',value=prefs['enabled'],disabled=locked)
        a,b=st.columns(2)
        with a:
            photo=st.file_uploader('01 · Ảnh nhân vật (tùy chọn)',type=['png','jpg','jpeg','webp'],disabled=locked,key='story_photo_'+pid)
            voice_files = st.file_uploader(
                '02 · Giọng đọc chính và phụ đề SRT',
                type=sorted({ext[1:] for ext in store.AUDIO} | {'srt'}),
                accept_multiple_files=True, disabled=locked,
                key=f"story_voice_{pid}_{cfg.get('main_srt', '')}",
                help='Chọn một file giọng đọc. Nếu có SRT đi kèm, chọn cả hai file cùng lúc.',
            )
            if cfg.get('main_srt'):
                st.caption('Đã lưu phụ đề SRT đi kèm giọng chính.')
                remove_srt = st.checkbox('Bỏ phụ đề SRT đã lưu', disabled=locked, key='remove_story_srt_'+pid)
            else:
                remove_srt = False
            intro=st.file_uploader('03 · File giọng đọc mở đầu (tùy chọn)',type=sorted(x[1:] for x in store.AUDIO),disabled=locked,key='story_intro_'+pid)
            no_intro=st.checkbox('Không dùng giọng mở đầu',value=prefs['no_intro'],disabled=locked)
            subscribe_corner = st.checkbox(
                'Hiệu ứng',
                value=prefs['subscribe_corner'], disabled=locked,
            )
            subtitles=st.checkbox('Tạo phụ đề',value=prefs['auto_subtitles'],disabled=locked)
            st.caption('Đã có giọng chính.' if project.get('voice') else 'Chưa có giọng chính.')
            if cfg.get('intro'):st.caption('Đã có giọng mở đầu.')
        with b:
            videos=st.file_uploader('04 · Thêm nhiều video nền trên máy',type=['mp4','mov','mkv','webm'],accept_multiple_files=True,disabled=locked,key='story_backgrounds_'+pid)
            existing=list(dict.fromkeys(cfg.get('backgrounds',[])+[r['file'] for r in records.values()]))
            kept=st.multiselect('Video nền đã lưu muốn dùng',existing,default=cfg.get('backgrounds',[]),format_func=lambda n:cfg.get('background_names',{}).get(n,'Video đã tải · '+n[:8]),disabled=locked)
            selected=st.multiselect('Chọn video Pixabay để tải khi dựng (tối đa 15)',list(hits),key=selection_key,format_func=lambda i:f"Pixabay {i} · {hits[i]['tags']} · {hits[i]['duration']} giây",max_selections=15,disabled=locked)
        if output_panel is not None:output_panel()
        with st.expander('**Cài đặt tùy chỉnh**',expanded=False):
            remove=st.checkbox('Tự động xóa nền ảnh',value=prefs['remove_background'],disabled=locked)
            restore_missing=st.checkbox('Tự khôi phục phần nhân vật bị xóa nhầm',value=prefs['restore_missing'],disabled=locked or not remove)
            keep_attached_objects=st.checkbox('Giữ đồ vật nhân vật đang cầm, đeo hoặc ôm',value=prefs['keep_attached_objects'],disabled=locked or not remove)
            with st.container():
                st.markdown('**Khôi phục vùng nhân vật hoặc chi tiết bị thiếu**')
                boxes=st.data_editor(pd.DataFrame(cfg.get('keep_boxes',[]),columns=['Trái','Trên','Phải','Dưới']),num_rows='dynamic',disabled=locked,key='story_boxes_'+pid).to_dict('records')
            c,d,e=st.columns(3)
            width=c.slider('Chiều rộng nhân vật (% khung)',10,100,int(prefs['width']),disabled=locked)
            x=d.slider('Vị trí ngang · trái → phải',0,100,int(prefs['x']),disabled=locked)
            y=e.slider('Vị trí dọc · trên → dưới',0,100,int(prefs['y']),disabled=locked)
            model=st.selectbox('Model nhận diện cho video kể chuyện',['small','base','tiny'],index=['small','base','tiny'].index(prefs['asr_model']),disabled=locked)
            auto_pixabay=st.checkbox('Tự tải 15 video Pixabay 16:9 mới · phối nhiều chủ đề liên quan · tránh trùng dự án trước',value=prefs['auto_pixabay'],disabled=locked)
            preferences=dict(prefs,auto_theme=auto_theme,enabled=enabled,no_intro=no_intro,remove_background=remove,restore_missing=restore_missing,keep_attached_objects=keep_attached_objects,
                             width=width,x=x,y=y,auto_subtitles=subtitles,asr_model=model,auto_pixabay=auto_pixabay,subscribe_corner=subscribe_corner)
            if not locked and preferences != store.story_defaults():
                store.save_story_defaults(preferences)
            def save_inputs():
                try:
                    audio_files = []
                    srt_files = []
                    for uploaded in voice_files:
                        if Path(uploaded.name).suffix.lower() == '.srt':
                            srt_files.append(uploaded)
                        else:
                            audio_files.append(uploaded)
                    if len(audio_files) > 1 or len(srt_files) > 1:
                        raise ValueError('Ô giọng đọc chính chỉ nhận một file âm thanh và một file SRT.')
                    voice = next(iter(audio_files), None)
                    main_srt = next(iter(srt_files), None)
                    new=dict(cfg,auto_theme=auto_theme,no_intro=no_intro,enabled=enabled,auto_pixabay=auto_pixabay,query=query,backgrounds=kept,pixabay_selected=[hits[i] for i in selected],remove_background=remove,restore_missing=restore_missing,keep_attached_objects=keep_attached_objects,
                             width=width,x=x,y=y,auto_subtitles=subtitles,asr_model=model,subscribe_corner=subscribe_corner,
                             keep_boxes=[[float(row[k]) for k in ('Trái','Trên','Phải','Dưới')] for row in boxes])
                    if len(set(records)|set(selected))>15:raise ValueError('Tổng số video Pixabay khác nhau của dự án vượt 15. Chọn lại video đã tải.')
                    if photo:
                        stamp=store.signature_upload(photo)
                        if stamp!=cfg.get('image_upload'):
                            new['image']=store.upload(folder,photo,store.IMAGES);new['image_upload']=stamp;new.pop('cutout',None)
                    for uploaded,field in ((voice,'voice'),(intro,'intro')):
                        if uploaded:
                            stamp=store.signature_upload(uploaded)
                            if stamp!=cfg.get(field+'_upload'):
                                name=store.upload(folder,uploaded,store.AUDIO)
                                if not probe(store.asset(folder,name))['audio']:raise ValueError('File giọng đọc cần có âm thanh.')
                                if field=='voice':project['voice']=name
                                else:new['intro']=name
                                new[field+'_upload']=stamp
                    if (remove_srt and not main_srt) or new.get('main_srt_voice') != project.get('voice'):
                        for key in ('main_srt', 'main_srt_voice', 'main_srt_upload'):
                            new.pop(key, None)
                    if main_srt:
                        if not project.get('voice'):
                            raise ValueError('Hãy tải giọng chính đi kèm file SRT.')
                        stamp = store.signature_upload(main_srt)
                        if stamp != new.get('main_srt_upload'):
                            duration = probe(store.asset(folder, project['voice']))['duration']
                            validate_srt(main_srt.getvalue().decode('utf-8-sig').replace('\r\n', '\n'), duration)
                            new.update(main_srt=store.upload(folder, main_srt, {'.srt'}),
                                       main_srt_voice=project['voice'], main_srt_upload=stamp)
                    if no_intro:new.pop('intro',None);new.pop('intro_upload',None)
                    names=dict(cfg.get('background_names',{}));uploads=dict(cfg.get('background_uploads',{}))
                    for video in videos:
                        stamp=store.signature_upload(video)
                        name=uploads.get(stamp)
                        if not name:
                            name=store.upload(folder,video,store.MEDIA- store.IMAGES);uploads[stamp]=name
                        if name not in new['backgrounds'] and stamp not in cfg.get('background_uploads',{}):new['backgrounds'].append(name)
                        names[name]=video.name
                    new.update(background_names=names,background_uploads=uploads)
                    if not enabled and project.get('voice_track'):
                        for derived in ('voice_track','overlay_image','captions','caption_words','captions_origin'):project.pop(derived,None)
                    project['story']=new;store.save(project);return True
                except (ValueError,OSError,TypeError,KeyError) as exc:st.error(str(exc));return False
            if st.button('Gợi ý chủ đề từ ảnh trên máy',disabled=locked):
                if save_inputs():
                    try:
                        from .thumbnail_theme import suggest
                        if not project['story'].get('image'):raise ValueError('Hãy thêm ảnh thumbnail trước.')
                        with st.spinner('Đang nhận diện ảnh trên máy…'):
                            result=suggest(store.asset(folder,project['story']['image']),folder)
                        if result.get('query'):
                            st.session_state[pending]=result['query'];st.rerun()
                        else:st.warning('Chủ đề chưa rõ. Hãy nhập từ khóa video nền phù hợp.')
                    except (ValueError,OSError,RuntimeError):st.error('Chưa tải hoặc chạy được model nhận diện ảnh. Kiểm tra mạng hoặc nhập từ khóa thủ công.')
            if st.button('Lưu nguyên liệu và bố cục kể chuyện',disabled=locked):
                if save_inputs():st.rerun()
    if cfg.get('image'):
        if st.button('Tách nền để xem trước',disabled=locked,key='story_cutout_'+pid):
            if save_inputs():launch(project,'cutout');st.rerun()
    @st.fragment(run_every=2)
    def preview_status():
        status=current(folder,'cutout')
        if status:
            st.progress(status['progress']/100,text=status['stage'])
            if status.get('error'):st.error(status['error'])
            if status['state'] in ('queued','running'):
                if st.button('Hủy tách nền',key='cancel_cutout_'+status['run_id']):(status['folder']/'cancel').touch()
            elif status['state']=='completed' and not st.session_state.get('cutout_seen_'+status['run_id']):
                st.session_state['cutout_seen_'+status['run_id']]=True;st.rerun()
    preview_status()
    if cfg.get('cutout'):
        st.image(str(store.asset(folder,cfg['cutout'])),caption='Ảnh đã tách nền',width=350)
        if st.button('Xem thử bố cục trên nền',disabled=locked,key='story_preview_'+pid):
            try:
                from .story import layout_preview
                st.image(layout_preview(project,folder),caption='Xem trước bố cục')
            except (ValueError,OSError,RuntimeError) as exc:st.error(str(exc))
    return save_inputs

