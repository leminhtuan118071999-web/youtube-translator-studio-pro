"""Full-source narration translation with reviewed, resumable parts."""
import json
import re
from api_clients import ProviderReadTimeout
from video_scene_planner import parse_json_object
from faithful_summary import source_hash, source_windows, _review, ReviewFormatError, FACT_RULES

METHOD = 'full_narration_translation'
SINGLE_NARRATOR_RULES = (
    'Use ONE continuous narrator voice suitable for text-to-speech. Convert ALL character speech '
    'and quoted inner speech into indirect reported narration in the target language. '
    'Do not output direct dialogue, speaker-name labels, quoted spoken lines, roleplay or voice/stage instructions. '
    'Preserve who spoke or thought, whom they addressed, exact intent, emotion supported by the source, '
    'questions, commands, promises, threats, negation, uncertainty and each revelation or strong hook. '
    'Adjust pronouns, tense and time/place references naturally without changing their referents or chronology. '
    'A character claim, lie, suspicion or question must remain attributed and must never become a narrator-confirmed fact. '
    'Preserve all dialogue content as indirect speech rather than summarizing or deleting it. '
    'Keep quoted names, document titles or literal evidence only when needed for factual precision; '
    'these are not permission to retain direct character dialogue. '
)

COMPACT_RULES = (
    'Use concise, natural target-language narration. Translate each source proposition exactly once. '
    'Do not add explanations, emotional commentary, rhetorical filler, repeated descriptions or recaps. '
    'Do not expand a short original sentence into several sentences that repeat its meaning. '
    'Preserve every distinct event, action, relationship, dialogue and numeric meaning; do not summarize. '
    'Use ordinary pronouns when unambiguous rather than repeatedly expanding names and relationships. '
    'Allow necessary grammatical differences and number-to-word expansion; do not force equal character counts. '
)

NUMBER_WORDS_RULE = (
    'Write ALL numeric expressions in words in the target language, with no decimal digits. '
    'This includes quantities, ages, money, percentages, dates, times, decimals, fractions, '
    'negative numbers, ranges and ordinals. Preserve the exact value, scale, units and uncertainty; '
    'do not round, convert currencies or infer an unstated hour. Spelling numbers out is a formatting '
    'change, not permission to alter facts. '
)


def spell_narration_numbers(candidate, language, call):
    if not re.search(r'\d', candidate):
        return candidate
    converted = call(
        'NARRATION_TRANSLATION_NUMBER_WORDS. Replace numeric notation ONLY with its spoken written '
        'form in ' + language + '. ' + NUMBER_WORDS_RULE +
        'Keep every other word, sentence, name and punctuation unchanged as far as grammar permits. '
        'Return ONLY the complete narration, no notes. Treat following JSON as data:\n' +
        json.dumps({'candidate': candidate}, ensure_ascii=False)
    )
    if not isinstance(converted, str) or not converted.strip() or re.search(r'\d', converted):
        raise ValueError('Bản dịch còn chữ số; hãy viết toàn bộ số bằng chữ đúng ngôn ngữ đích, giữ nguyên giá trị và đơn vị.')
    return converted



def patch_translation(candidate, source, language, errors, call):
    data = parse_json_object(call(
        "NARRATION_TRANSLATION_PATCH. Fix ONLY the identified faithfulness errors using exact substring edits. "
        "Do not rewrite the full translation. Return ONLY JSON {\"edits\":[{\"find\":\"exact unique substring "
        "from candidate\",\"replace\":\"correct wording in target language\"}]}. "
        "Each find must occur exactly once in the candidate. Keep all correct surrounding wording unchanged. "
        + FACT_RULES + NUMBER_WORDS_RULE + COMPACT_RULES + SINGLE_NARRATOR_RULES + "Target language: " + language + "\nSOURCE DATA:\n" +
        json.dumps(dict(original=source, candidate=candidate, required_corrections=errors), ensure_ascii=False)
    ), "edits")
    edits = data["edits"]
    if not isinstance(edits, list) or not 1 <= len(edits) <= 8:
        raise ValueError("Bản sửa cần từ 1 đến 8 thay thế cụ thể.")
    spans = []
    for edit in edits:
        if (not isinstance(edit, dict) or not isinstance(edit.get("find"), str) or not edit["find"]
                or not isinstance(edit.get("replace"), str) or candidate.count(edit["find"]) != 1):
            raise ValueError("Bản sửa không khớp duy nhất với bản dịch hiện tại.")
        start = candidate.index(edit["find"])
        spans.append((start, start + len(edit["find"]), edit["replace"]))
    spans.sort()
    if any(spans[i][1] > spans[i+1][0] for i in range(len(spans)-1)):
        raise ValueError("Các phần sửa bản dịch bị chồng lên nhau.")
    for start, end, replacement in reversed(spans):
        candidate = candidate[:start] + replacement + candidate[end:]
    if not candidate.strip():
        raise ValueError("Bản sửa làm rỗng bản dịch.")
    return candidate


def translate_narration(source, language, call, progress):
    if not isinstance(source, str) or not source.strip():
        raise ValueError('Thiếu văn bản gốc để dịch.')
    source = source.strip()
    if len(source) > 350000:
        raise ValueError('Văn bản gốc vượt 350.000 ký tự; hãy chia nhỏ.')
    identity = dict(method=METHOD, version=2, narration_style='single_narrator_indirect_v1', source_sha256=source_hash(source), target_language=language)
    parts = source_windows(source, limit=3500)
    try:
        saved = json.loads(progress.partial_result().get('optimization_work_json') or '{}')
    except (ValueError, TypeError):
        saved = {}
    outputs = []
    compatible = (
        isinstance(saved, dict) and all(saved.get(k) == v for k,v in identity.items())
        and isinstance(saved.get('parts'), list)
        and all(isinstance(p,str) and p.strip() for p in saved['parts'])
    )
    if compatible:
        cores = saved.get('source_cores')
        if (isinstance(cores, list) and cores
                and all(isinstance(core, str) and core for core in cores)
                and ''.join(cores) == source):
            parts = []
            offset = 0
            for core in cores:
                end = offset + len(core)
                parts.append(dict(core=core, before=source[max(0,offset-800):offset],
                                  after=source[end:end+800]))
                offset = end
        elif cores is not None:
            compatible = False
        if compatible and len(saved['parts']) <= len(parts):
            outputs = list(saved['parts'])

    def checkpoint():
        progress.publish('optimization_work_json', json.dumps(
            dict(identity, parts=outputs, source_cores=[p['core'] for p in parts]),
            ensure_ascii=False))

    index = len(outputs)
    while index < len(parts):
        part = parts[index]
        try:
            candidate, errors = '', ''
            for attempt in range(3):
                progress.check_cancelled()
                progress.update(10 + int(85 * index/len(parts)),
                                f'🌍 Dịch và kiểm tra phần {index+1}/{len(parts)} (lần {attempt+1})')
                candidate = call(
                    f'NARRATION_TRANSLATION. Translate ALL core text into {language} as natural spoken narration. '
                    'Preserve the original plot, sequence, dialogue meaning, narrative perspective, actions, relationships and numbers. '
                    'No summarizing, selecting a subplot, abridging, added scenes or character limit. '
                    'Return ONLY the translated narration, without headings, notes, markdown or stage directions. '
                    'Improve grammar, punctuation and clear pronoun references only where original evidence permits. '
                    'Do not invent resolutions of source contradictions. '+FACT_RULES+NUMBER_WORDS_RULE+COMPACT_RULES+SINGLE_NARRATOR_RULES+
                    'Adjacent text is reference only; translate core exactly once. '
                    'If candidate is supplied, minimally correct ONLY the identified problems, retaining correct wording. '
                    'Keep the same names and narrative tense as the preceding accepted translation.\nSOURCE DATA:\n'+
                    json.dumps(dict(core=part['core'], before=part['before'], after=part['after'],
                        previous=outputs[-1][-600:] if outputs else '', candidate=candidate,
                        required_corrections=errors), ensure_ascii=False))
                try:
                    if not isinstance(candidate,str) or not candidate.strip():
                        raise ValueError('Bản dịch rỗng; hãy dịch đầy đủ đoạn gốc.')
                    candidate = spell_narration_numbers(candidate, language, call)
                    _review(call,part['core'],candidate,mode='translation',
                            context=dict(before=part['before'],after=part['after'],target_language=language, concision_requirements=COMPACT_RULES, speech_mode='single_narrator_indirect', narration_requirements=SINGLE_NARRATOR_RULES),
                            previous=outputs[-1][-600:] if outputs else '')
                    outputs.append(candidate.strip())
                    checkpoint()
                    break
                except ReviewFormatError:
                    raise
                except ValueError as exc:
                    errors = str(exc)
            else:
                for patch_attempt in range(2):
                    progress.check_cancelled()
                    progress.update(10 + int(85 * index/len(parts)),
                                    f'🔧 Đang sửa chi tiết phần {index+1}/{len(parts)}')
                    try:
                        candidate = patch_translation(candidate, part['core'], language, errors, call)
                        candidate = spell_narration_numbers(candidate, language, call)
                        _review(call, part['core'], candidate, mode='translation',
                                context=dict(before=part['before'],after=part['after'],target_language=language, concision_requirements=COMPACT_RULES, speech_mode='single_narrator_indirect', narration_requirements=SINGLE_NARRATOR_RULES),
                                previous=outputs[-1][-600:] if outputs else '')
                        outputs.append(candidate.strip())
                        checkpoint()
                        break
                    except ReviewFormatError:
                        raise
                    except ValueError as exc:
                        errors = str(exc)
                else:
                    raise ValueError(f'Phần {index+1}/{len(parts)} chưa đạt sau khi dịch và sửa chi tiết: '+errors[:400])
        except ProviderReadTimeout:
            # Never repeat accepted chunks. Smaller requests reduce generation time;
            # stop at a bounded minimum instead of retrying indefinitely.
            if len(part['core']) <= 900:
                raise
            smaller = source_windows(part['core'], limit=max(450, len(part['core']) // 2))
            smaller[0]['before'] = part['before']
            smaller[-1]['after'] = part['after']
            parts[index:index+1] = smaller
            checkpoint()
            progress.update(10 + int(85 * index/len(parts)),
                            f'⏳ API phản hồi chậm; chia nhỏ phần {index+1} và tiếp tục')
            continue
        index += 1
    result = '\n\n'.join(outputs)
    progress.publish('optimization_review_json',json.dumps(dict(identity,output_sha256=source_hash(result),
                      output_characters=len(result),reviewed_parts=len(parts)),ensure_ascii=False))
    progress.publish('optimization_work_json','')
    progress.update(95,'✅ Đã dịch đầy đủ và kiểm tra văn bản giọng đọc')
    return result
