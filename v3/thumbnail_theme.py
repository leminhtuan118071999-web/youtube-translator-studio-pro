"""Local CLIP scene suggestions. Only model files are downloaded; images stay local."""
import hashlib
import json
from pathlib import Path
from .projects import home,read,atomic
from .render import Cancelled

MODEL='Xenova/clip-vit-base-patch32'
REVISION='6b7c523703ae26e39be4b03774966f8571c7f523'
VERSION='clip-scenes-v3'
# Visual environments only: no guessing identity, personality or criminal roles.
THEMES=[
 ('Rừng cây','forest sunlight','a green forest with trees and sunlight'),
 ('Biển và bãi biển','ocean beach','the ocean and a sandy beach'),
 ('Núi','mountain landscape','mountains and a scenic landscape'),
 ('Sông suối','river nature','a river flowing through nature'),
 ('Thác nước','waterfall nature','a waterfall in nature'),
 ('Hồ nước','lake landscape','a peaceful lake landscape'),
 ('Vườn hoa','flower garden','a garden full of flowers'),
 ('Đồng quê','countryside','a rural countryside with fields and farms'),
 ('Sa mạc','desert landscape','a dry sandy desert landscape'),
 ('Tuyết','snow winter','a snowy winter landscape'),
 ('Mưa','rain city','a rainy street with wet pavement'),
 ('Hoàng hôn','sunset landscape','a landscape at sunset with warm orange light'),
 ('Bầu trời','clouds sky','a sky full of moving clouds'),
 ('Thành phố ban ngày','city street','a city street in daylight'),
 ('Thành phố ban đêm','city night','a city at night with illuminated buildings'),
 ('Biệt thự','luxury mansion','a luxurious mansion or villa'),
 ('Nội thất sang trọng','luxury interior','an elegant luxurious interior with expensive furniture'),
 ('Phòng khách','living room','a home living room with a sofa'),
 ('Văn phòng','office interior','a modern office interior with desks'),
 ('Nhà bếp','kitchen interior','a home kitchen with cabinets and a counter'),
 ('Nhà hàng','restaurant interior','a restaurant or cafe with dining tables'),
 ('Bệnh viện','hospital','a hospital room or hospital corridor'),
 ('Trường học','school classroom','a school classroom with desks'),
 ('Lâu đài','castle','a historical stone castle'),
 ('Nhà thờ','church','a church with traditional architecture'),
 ('Bữa tiệc','party celebration','a celebration with decorations and party guests'),
 ('Không rõ bối cảnh',None,'a close-up portrait with no clear visible background'),
 ('Cận cảnh đồ vật hoặc thú cưng',None,'a close-up photograph of an object or an animal'),
]


def check_cancel(cancel):
    if cancel is not None and Path(cancel).exists():raise Cancelled()


def pixel_values(image):
    import numpy as np
    from PIL import Image,ImageOps
    # Preserve the complete thumbnail composition, including background at edges.
    rgb=ImageOps.exif_transpose(image).convert('RGBA')
    canvas=Image.new('RGBA',rgb.size,(123,117,104,255));canvas.alpha_composite(rgb)
    resized=ImageOps.pad(canvas.convert('RGB'),(224,224),method=Image.Resampling.BICUBIC,color=(123,117,104))
    value=np.asarray(resized,dtype='float32')/255
    value=(value-np.array([.48145466,.4578275,.40821073],dtype='float32'))/np.array([.26862954,.26130258,.27577711],dtype='float32')
    return value.transpose(2,0,1)[None].astype('float32')


def normalize(values):
    import numpy as np
    values=np.asarray(values,dtype='float32')
    if values.ndim!=2 or not np.isfinite(values).all():raise ValueError('Model nhận diện ảnh trả dữ liệu không hợp lệ.')
    return values/np.maximum(np.linalg.norm(values,axis=-1,keepdims=True),1e-12)


def rank_scene(image_embedding,text_embeddings):
    import numpy as np
    scores=(normalize(image_embedding)@normalize(text_embeddings).T)[0]
    order=np.argsort(scores)[::-1]
    best,second=int(order[0]),int(order[1]);margin=float(scores[best]-scores[second])
    # These are similarity scores, not calibrated probabilities.
    label,query,_=THEMES[best]
    confident=bool(query is not None and scores[best]>=.24 and margin>=.02)
    return dict(label=label,query=query if confident else None,
                similarity=round(float(scores[best]),4),margin=round(margin,4),
                alternatives=[THEMES[int(i)][0] for i in order[:3]],confident=confident)


def model_file(filename,progress,cancel):
    from huggingface_hub import hf_hub_download
    cache=home()/'models'/'thumbnail-clip'
    check_cancel(cancel)
    args=dict(repo_id=MODEL,filename=filename,revision=REVISION,cache_dir=str(cache))
    try:return hf_hub_download(**args,local_files_only=True)
    except OSError:pass
    progress('Đang tải model nhận diện ảnh về máy (chỉ cần lần đầu)…')
    path=hf_hub_download(**args)
    check_cancel(cancel)
    return path


def session(path):
    import onnxruntime as ort
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    return ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])


def text_features(progress,cancel):
    import numpy as np
    from tokenizers import Tokenizer
    filename=home()/'models'/'thumbnail-clip'/'scene-embeddings.json'
    identity=hashlib.sha256(json.dumps([MODEL,REVISION,VERSION,THEMES],ensure_ascii=False).encode()).hexdigest()
    if filename.exists():
        try:
            data=read(filename);values=np.asarray(data['vectors'],dtype='float32')
            if data.get('identity')==identity and values.shape==(len(THEMES),512) and np.isfinite(values).all():return values
        except (ValueError,KeyError,TypeError):pass
    tokenizer=Tokenizer.from_file(model_file('tokenizer.json',progress,cancel))
    tokenizer.enable_truncation(max_length=77)
    tokenizer.enable_padding(length=77,pad_id=49407,pad_token='<|endoftext|>')
    encoded=tokenizer.encode_batch(['A photograph of '+scene+'.' for _,_,scene in THEMES])
    model=session(model_file('onnx/text_model_quantized.onnx',progress,cancel))
    arrays=dict(input_ids=np.array([e.ids for e in encoded],dtype='int64'),
                attention_mask=np.array([e.attention_mask for e in encoded],dtype='int64'))
    feeds={i.name:arrays[i.name] for i in model.get_inputs()}
    check_cancel(cancel)
    vectors=normalize(model.run(['text_embeds'],feeds)[0])
    atomic(filename,dict(identity=identity,vectors=vectors.tolist()))
    return vectors


def suggest(image_path,folder,cancel=None,progress=lambda _:None):
    from PIL import Image,ImageStat
    image_path=Path(image_path);folder=Path(folder)
    check_cancel(cancel)
    with image_path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    cache=folder/'thumbnail-theme.json'
    if cache.exists():
        previous=read(cache)
        if previous.get('image_sha256')==digest and previous.get('version')==VERSION:return previous
    with Image.open(image_path) as image:
        if image.width*image.height>40000000:raise ValueError('Ảnh thumbnail vượt 40 triệu pixel.')
        if max(ImageStat.Stat(image.convert('RGB').resize((64,64))).stddev) < 5:
            result=dict(confident=False,query=None,label='Ảnh chưa đủ chi tiết',similarity=0,margin=0,alternatives=[],
                        version=VERSION,model=MODEL,revision=REVISION,image_sha256=digest,source_image=image_path.name)
            atomic(cache,result);return result
        pixels=pixel_values(image)
    progress('Đang phân tích bố cục thumbnail trên máy…')
    features=text_features(progress,cancel)
    model=session(model_file('onnx/vision_model_quantized.onnx',progress,cancel))
    check_cancel(cancel)
    result=rank_scene(model.run(['image_embeds'],{'pixel_values':pixels})[0],features)
    check_cancel(cancel)
    result.update(version=VERSION,model=MODEL,revision=REVISION,image_sha256=digest,source_image=image_path.name)
    atomic(cache,result)
    return result


def resolve_query(folder,config,cancel=None,progress=lambda _:None):
    """Use a confident suggestion; manual query is the explicit fallback."""
    from .projects import asset
    fallback=config.get('query','forest sunlight').strip()
    if not config.get('auto_theme', False) or not config.get('image'):
        return fallback
    choice=Path(folder)/'thumbnail-theme-choice.json'
    try:
        result=suggest(asset(folder,config['image']),folder,cancel,progress)
        if result.get('confident') and result.get('query'):
            atomic(choice,dict(source_image=config['image'],query=result['query'],automatic=True,label=result['label']))
            return result['query']
        progress('Chủ đề ảnh chưa rõ; dùng từ khóa đã nhập.')
    except Cancelled:raise
    except Exception:
        progress('Chưa nhận diện được ảnh trên máy; dùng từ khóa đã nhập.')
    atomic(choice,dict(source_image=config.get('image'),query=fallback,automatic=False))
    if not fallback:raise ValueError('Chưa nhận diện rõ chủ đề. Hãy nhập từ khóa video nền hoặc thử ảnh thumbnail khác.')
    return fallback

