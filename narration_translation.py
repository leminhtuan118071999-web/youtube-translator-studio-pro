"""Full-source narration translation with reviewed, resumable parts."""
import json
from faithful_summary import source_hash, source_windows, _review, ReviewFormatError, FACT_RULES

METHOD = 'full_narration_translation'


def translate_narration(source, language, call, progress):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Thiếu văn bản gốc để dịch.')
    source = source.strip()
    if len(source) > 350000:
        raise ValueError('Văn bản gốc vượt 350.000 ký tự; hãy chia nhỏ.')
    identity = dict(method=METHOD, version=1, source_sha256=source_hash(source), target_language=language)
    parts = source_windows(source, limit=3500)
    try:
        saved = json.loads(progress.partial_result().get('optimization_work_json') or '{}')
    except (ValueError, TypeError):
        saved = {}
    outputs = []
    if (isinstance(saved, dict) and all(saved.get(k) == v for k,v in identity.items())
            and isinstance(saved.get('parts'), list) and len(saved['parts']) <= len(parts)
            and all(isinstance(p,str) and p.strip() for p in saved['parts'])):
        outputs = list(saved['parts'])
    for index, part in enumerate(parts):
        if index < len(outputs):
            continue
        candidate, errors = '', ''
        for attempt in range(3):
            progress.check_cancelled()
            progress.update(10 + int(85 * index/len(parts)),
                            f'🌍 Dịch và kiểm tra phần {index+1}/{len(parts)} (lần {attempt+1})')
            candidate = call(
                f'NARRATION_TRANSLATION. Translate ALL core text into {language} as natural spoken narration. '
                'Preserve the original plot, sequence, dialogue, voice, actions, relationships and numbers. '
                'No summarizing, selecting a subplot, abridging, added scenes or character limit. '
                'Return ONLY the translated narration, without headings, notes, markdown or stage directions. '
                'Improve grammar, punctuation and clear pronoun references only where original evidence permits. '
                'Do not invent resolutions of source contradictions. '+FACT_RULES+
                'Adjacent text is reference only; translate core exactly once. '
                'If candidate is supplied, minimally correct ONLY the identified problems, retaining correct wording. '
                'Keep the same names and narrative tense as the preceding accepted translation.\nSOURCE DATA:\n'+
                json.dumps(dict(core=part['core'], before=part['before'], after=part['after'],
                    previous=outputs[-1][-600:] if outputs else '', candidate=candidate,
                    required_corrections=errors), ensure_ascii=False))
            try:
                if not isinstance(candidate,str) or not candidate.strip():
                    raise ValueError('Bản dịch rỗng; hãy dịch đầy đủ đoạn gốc.')
                _review(call,part['core'],candidate,mode='translation',
                        context=dict(before=part['before'],after=part['after'],target_language=language),
                        previous=outputs[-1][-600:] if outputs else '')
                outputs.append(candidate.strip())
                progress.publish('optimization_work_json', json.dumps(dict(identity,parts=outputs),ensure_ascii=False))
                break
            except ReviewFormatError:
                raise
            except ValueError as exc:
                errors = str(exc)
        else:
            raise ValueError(f'Phần {index+1}/{len(parts)} chưa đạt sau 3 lần dịch/sửa: '+errors[:400])
    result = '\n\n'.join(outputs)
    progress.publish('optimization_review_json',json.dumps(dict(identity,output_sha256=source_hash(result),
                      output_characters=len(result),reviewed_parts=len(parts)),ensure_ascii=False))
    progress.publish('optimization_work_json','')
    progress.update(95,'✅ Đã dịch đầy đủ và kiểm tra văn bản giọng đọc')
    return result
