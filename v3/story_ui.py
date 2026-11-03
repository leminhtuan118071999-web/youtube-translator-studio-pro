"""Storytelling inputs and preview, separate from the manual timeline editor."""
import json
from pathlib import Path
import streamlit as st
import pandas as pd
from . import projects as store
from .render import probe
from .render_worker import launch,current
from . import pixabay


def panel(project,folder,locked):
    pid=project['id'];cfg=project.get('story',{})
    st.subheader('Ảnh nhân vật trên video nền · như video mẫu')
    st.caption('Giọng mở đầu phát trước, tiếp theo giọng chính. Nền nối tiếp rồi lặp cả danh sách đến hết lời đọc; ảnh nhân vật nằm phía trước. Âm thanh gốc của video nền được tắt.')
    with st.expander('Cấu hình Pixabay · chỉ lưu khóa trên máy này'):
        st.link_button('Lấy khóa API trên Pixabay','https://pixabay.com/api/docs/')
        st.caption('Đã lưu khóa trên máy.' if pixabay.api_key() else 'Chưa có khóa. Có thể dùng video nền tải lên mà không cần khóa.')
        with st.form('pixabay_key_'+pid,clear_on_submit=True):
            key=st.text_input('Khóa Pixabay API',type='password')
            if st.form_submit_button('Lưu khóa Pixabay'):
                try:pixabay.save_key(key);st.success('Đã lưu khóa trên máy; không đưa vào bản xuất dự án.')
                except ValueError as exc:st.error(str(exc))
    query=st.text_input('Từ khóa tìm video nền Pixabay',value=cfg.get('query','forest sunlight'),max_chars=100,key='pixabay_query_'+pid,disabled=locked)
    if st.button('Tìm video trên Pixabay',disabled=locked,key='pixabay_search_'+pid):
        try:
            with st.spinner('Đang tìm video trên Pixabay…'):st.session_state['pixabay_hits_'+pid]=pixabay.search(query)
        except (ValueError,OSError,json.JSONDecodeError) as exc:st.error(str(exc))
    hits={str(h['id']):h for h in cfg.get('pixabay_selected',[])}
    hits.update({str(h['id']):h for h in st.session_state.get('pixabay_hits_'+pid,[])})
    records=store.read(folder/'pixabay-downloads.json') if (folder/'pixabay-downloads.json').exists() else cfg.get('downloaded',{})
    st.caption(f'Đã tải {len(records)}/15 video Pixabay khác nhau cho dự án này. Đổi từ khóa không đặt lại giới hạn; dựng lại dùng tệp đã tải.')
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
    with st.form('story_inputs_'+pid,clear_on_submit=True):
        enabled=st.checkbox('Dựng theo kiểu ảnh nhân vật + video nền',value=cfg.get('enabled',True),disabled=locked)
        a,b=st.columns(2)
        with a:
            photo=st.file_uploader('01 · Ảnh nhân vật',type=['png','jpg','jpeg','webp'],disabled=locked,key='story_photo_'+pid)
            voice=st.file_uploader('02 · File giọng đọc chính',type=sorted(x[1:] for x in store.AUDIO),disabled=locked,key='story_voice_'+pid)
            intro=st.file_uploader('03 · File giọng đọc mở đầu (tùy chọn)',type=sorted(x[1:] for x in store.AUDIO),disabled=locked,key='story_intro_'+pid)
            no_intro=st.checkbox('Không dùng giọng mở đầu',value=False,disabled=locked)
            st.caption('Đã có giọng chính.' if project.get('voice') else 'Chưa có giọng chính.')
            if cfg.get('intro'):st.caption('Đã có giọng mở đầu.')
        with b:
            videos=st.file_uploader('04 · Thêm nhiều video nền trên máy',type=['mp4','mov','mkv','webm'],accept_multiple_files=True,disabled=locked,key='story_backgrounds_'+pid)
            existing=list(dict.fromkeys(cfg.get('backgrounds',[])+[r['file'] for r in records.values()]))
            kept=st.multiselect('Video nền đã lưu muốn dùng',existing,default=cfg.get('backgrounds',[]),format_func=lambda n:cfg.get('background_names',{}).get(n,'Video đã tải · '+n[:8]),disabled=locked)
            selected=st.multiselect('Chọn video Pixabay để tải khi dựng (tối đa 15)',list(hits),key=selection_key,format_func=lambda i:f"Pixabay {i} · {hits[i]['tags']} · {hits[i]['duration']} giây",max_selections=15,disabled=locked)
        remove=st.checkbox('Tự động xóa nền ảnh',value=cfg.get('remove_background',True),disabled=locked)
        st.caption('Bỏ chọn nếu đã dùng PNG trong suốt. Tách nền giữ ảnh gốc, không vẽ lại nhân vật; tóc/vật thể nhỏ cần xem trước.')
        with st.expander('Giữ thêm chi tiết ngoài nhân vật'):
            st.caption('Thêm vùng chữ nhật theo % ảnh gốc: trái, trên, phải, dưới (0–100). Vùng này giữ cả chi tiết và nền bên trong vùng; dùng PNG đã chỉnh sẵn nếu cần đường viền chính xác.')
            boxes=st.data_editor(pd.DataFrame(cfg.get('keep_boxes',[]),columns=['Trái','Trên','Phải','Dưới']),num_rows='dynamic',disabled=locked,key='story_boxes_'+pid).to_dict('records')
        c,d,e=st.columns(3)
        width=c.slider('Chiều rộng nhân vật (% khung)',10,100,int(cfg.get('width',75)),disabled=locked)
        x=d.slider('Vị trí ngang · trái → phải',0,100,int(cfg.get('x',50)),disabled=locked)
        y=e.slider('Vị trí dọc · trên → dưới',0,100,int(cfg.get('y',100)),disabled=locked)
        subtitles=st.checkbox('Tự tạo phụ đề cho cả mở đầu và giọng chính',value=cfg.get('auto_subtitles',True),disabled=locked)
        model=st.selectbox('Model nhận diện cho video kể chuyện',['small','base','tiny'],index=['small','base','tiny'].index(cfg.get('asr_model','small')),disabled=locked)
        if st.form_submit_button('Lưu nguyên liệu và bố cục kể chuyện',disabled=locked):
            try:
                new=dict(cfg,enabled=enabled,query=query,backgrounds=kept,pixabay_selected=[hits[i] for i in selected],remove_background=remove,
                         width=width,x=x,y=y,auto_subtitles=subtitles,asr_model=model,
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
                if no_intro:new.pop('intro',None);new.pop('intro_upload',None)
                names=dict(cfg.get('background_names',{}));uploads=dict(cfg.get('background_uploads',{}))
                for video in videos:
                    stamp=store.signature_upload(video)
                    name=uploads.get(stamp)
                    if not name:
                        name=store.upload(folder,video,store.MEDIA- store.IMAGES);uploads[stamp]=name
                    if name not in new['backgrounds']:new['backgrounds'].append(name)
                    names[name]=video.name
                new.update(background_names=names,background_uploads=uploads)
                if not enabled and project.get('voice_track'):
                    for derived in ('voice_track','overlay_image','captions','caption_words','captions_origin'):project.pop(derived,None)
                project['story']=new;store.save(project);st.session_state['restore_story_selection_'+pid]=True;st.rerun()
            except (ValueError,OSError,TypeError,KeyError) as exc:st.error(str(exc))
    if cfg.get('image'):
        if st.button('Tách nền để xem trước',disabled=locked,key='story_cutout_'+pid):launch(project,'cutout');st.rerun()
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
        st.image(str(store.asset(folder,cfg['cutout'])),caption='Ảnh đã tách nền lần gần nhất · nếu đổi ảnh/vùng giữ, bấm tách nền lại',width=350)
        if st.button('Xem thử bố cục trên nền',disabled=locked,key='story_preview_'+pid):
            try:
                from .story import layout_preview
                st.image(layout_preview(project,folder),caption='Xem thử một khung hình · dùng bố cục đã lưu')
            except (ValueError,OSError,RuntimeError) as exc:st.error(str(exc))
    st.caption('Chỉnh cấu hình ở mục 04, lưu nguyên liệu tại đây, rồi chọn nơi lưu và bắt đầu dựng ở cuối mục 05.')
