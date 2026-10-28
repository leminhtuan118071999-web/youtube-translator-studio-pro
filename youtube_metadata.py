"""Shared target-language YouTube metadata generation and review."""
import json
import unicodedata
from video_scene_planner import parse_json_object


def validate_metadata(data):
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in ('title','description')):
        raise ValueError('Thiếu tiêu đề hoặc mô tả.')
    title = unicodedata.normalize('NFC', ' '.join(data['title'].split()))
    description = data['description'].strip()
    tags = data.get('tags')
    if len(title) >= 100:
        raise ValueError(f'Tiêu đề có {len(title)} ký tự; hãy viết lại tối đa 99 ký tự, không cắt cụt câu.')
    if '<' in title or '>' in title:
        raise ValueError('Tiêu đề không được chứa dấu < hoặc >.')
    if len(description) > 5000:
        raise ValueError('Mô tả vượt 5000 ký tự; hãy viết gọn lại, giữ thông tin và đường dẫn cần thiết.')
    if not isinstance(tags, list) or not tags or any(not isinstance(t,str) or not t.strip() for t in tags):
        raise ValueError('Danh sách thẻ tag không hợp lệ.')
    unique=[]; seen=set()
    for tag in tags:
        tag=unicodedata.normalize('NFC',' '.join(tag.strip().lstrip('#').split()))
        if tag and tag.casefold() not in seen:
            unique.append(tag);seen.add(tag.casefold())
    if not unique or sum(len(t)+(2 if ' ' in t else 0) for t in unique)+len(unique)-1 > 500:
        raise ValueError('Tổng thẻ tag vượt 500 ký tự; rút gọn và ưu tiên thẻ liên quan nhất.')
    return title, description, ', '.join(unique)


def generate_youtube_metadata(script, original_title, original_description, language, call):
    inputs=dict(original_title=original_title,original_description=original_description,story_context=script)
    errors='';candidate=None
    for attempt in range(3):
        try:
            candidate=parse_json_object(call(
                f'TARGET_METADATA. Write ALL title, description and tags naturally in {language}. '
                'Preserve proper names. Adapt the original title into a stronger YouTube headline, not a literal '
                'translation: foreground a real central conflict, emotional stake or intriguing event from the story. '
                'Use natural local phrasing and a relevant keyword; keep it concise and strictly UNDER 100 characters '
                '(maximum 99 including spaces and punctuation). No invented twists, false promises, exaggerated facts, '
                'keyword stuffing or unnecessary ALL CAPS. Do not truncate an overlong title; rewrite it coherently. '
                'Description: translate the meaningful original information accurately, improve flow for local viewers, '
                'start with a compelling factual introduction and relevant topic keywords. Preserve supplied links, '
                'credits and factual numbers; never invent links, timestamps or channel names. Maximum 5000 characters. '
                'Tags: around 15 distinct relevant target-language search phrases ordered by relevance; mix topic and '
                'specific story phrases, no irrelevant trending tags, no hashtag prefix, combined YouTube tag budget '
                'under 500 characters including commas and quotes around phrases with spaces. '
                'All metadata must match the actual story. If originals are missing, derive them from story context. '
                'Return ONLY JSON {"title":"...","description":"...","tags":["..."]}. '
                'Previous validation errors: '+errors+'\nSOURCE DATA:\n'+json.dumps({**inputs,'candidate':candidate},ensure_ascii=False)
            ),'title')
            result=validate_metadata(candidate)
            verdict=parse_json_object(call(
                f'TARGET_METADATA_REVIEW. Check every field is natural {language}, except proper names and links. '
                'Check title is attractive but grounded in the actual story and original meaning, no invented hooks, '
                'wrong actors, relationships, numbers or misleading claims. Description must preserve factual '
                'information and supplied links/credits; tags must be relevant, localized and non-spammy. '
                'Return ONLY JSON {"ok":true,"issues":[]}.\nSOURCE DATA:\n'+
                json.dumps({**inputs,'candidate':dict(title=result[0],description=result[1],tags=result[2])},ensure_ascii=False)
            ),'ok')
            if verdict.get('ok') is not True or verdict.get('issues') != []:
                raise ValueError('Metadata chưa đạt ngôn ngữ/độ chính xác: '+str(verdict.get('issues','Thiếu kết quả kiểm tra'))[:1000])
            return result
        except ValueError as exc:
            errors=str(exc)
    raise ValueError('Chưa tối ưu được tiêu đề, mô tả và tag: '+errors)
