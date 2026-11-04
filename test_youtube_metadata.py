import json
import unittest
from youtube_metadata import validate_metadata, generate_youtube_metadata

class MetadataTests(unittest.TestCase):
    def test_nested_metadata_and_review_are_recovered(self):
        def call(prompt):
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return '```json\n{"result":{"ok":true,"issues":[]}}\n```'
            return '{"metadata":{"title":"Titolo","description":"Storia fedele.","tags":["storia"]}}'
        self.assertEqual(generate_youtube_metadata('Story', '', '', 'Italian', call)[0], 'Titolo')

    def test_missing_field_is_retried_with_precise_seo_feedback(self):
        prompts = []
        def call(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return '{"description":"Incomplete"}'
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return '{"ok":true,"issues":[]}'
            self.assertIn('trường JSON "title"', prompt)
            return '{"title":"Titolo","description":"Storia.","tags":["storia"]}'
        self.assertEqual(generate_youtube_metadata('Story', '', '', 'Italian', call)[0], 'Titolo')
        self.assertEqual(len(prompts), 3)

    def test_missing_review_never_bypasses_fidelity_check(self):
        def call(prompt):
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return '{"issues":[]}'
            return '{"title":"Titolo","description":"Storia.","tags":["storia"]}'
        with self.assertRaisesRegex(ValueError, 'chưa trả kết luận'):
            generate_youtube_metadata('Story', '', '', 'Italian', call)

    def test_translated_json_keys_are_repaired_without_retranslating_story(self):
        prompts = []
        def call(prompt):
            prompts.append(prompt)
            if prompt.startswith('TARGET_METADATA_FORMAT_REPAIR'):
                self.assertIn('titolo', prompt)
                self.assertIn('do not invent missing content', prompt)
                return '{"title":"La famiglia","description":"Una storia di famiglia.","tags":["famiglia"]}'
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return '{"ok":true,"issues":[]}'
            return '{"titolo":"La famiglia","descrizione":"Una storia di famiglia.","tag":["famiglia"]}'
        result = generate_youtube_metadata('Story', '', '', 'Italian', call)
        self.assertEqual(result[0], 'La famiglia')
        self.assertEqual(len(prompts), 3)

    def test_review_format_retries_same_candidate_with_full_source(self):
        calls = []
        def call(prompt):
            calls.append(prompt)
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                if 'REVIEW FORMAT RETRY' not in prompt:
                    return '{"approvato":true,"problemi":[]}'
                self.assertIn('Original title', prompt)
                self.assertIn('Original description', prompt)
                self.assertIn('La famiglia', prompt)
                return '{"ok":true,"issues":[]}'
            return '{"title":"La famiglia","description":"Storia.","tags":["famiglia"]}'
        self.assertEqual(generate_youtube_metadata('Story', 'Original title', 'Original description', 'Italian', call)[0], 'La famiglia')
        self.assertEqual(len(calls), 3)

    def test_ambiguous_review_cannot_approve_or_regenerate_valid_candidate(self):
        calls = []
        def call(prompt):
            calls.append(prompt)
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return '{"ok":"true","issues":[]}'
            return '{"title":"Titolo","description":"Storia.","tags":["storia"]}'
        with self.assertRaises(ValueError):
            generate_youtube_metadata('Story', '', '', 'Italian', call)
        self.assertEqual(len(calls), 4)
        self.assertEqual(sum(p.startswith('TARGET_METADATA.') for p in calls), 1)

    def test_text_verdict_recovers_json_failure(self):
        def call(prompt):
            if prompt.startswith('TARGET_METADATA_TEXT_REVIEW'):
                self.assertIn('Original title', prompt)
                self.assertNotIn('Return ONLY JSON', prompt)
                return 'LMT_SEO_PASS'
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return 'Formato non disponibile'
            return '{"title":"Titolo","description":"Storia.","tags":["storia"]}'
        self.assertEqual(generate_youtube_metadata('Story', 'Original title', '', 'Italian', call)[0], 'Titolo')

    def test_negative_text_verdict_never_approves(self):
        def call(prompt):
            if prompt.startswith('TARGET_METADATA_TEXT_REVIEW'):
                return 'LMT_SEO_FAIL: wrong actor'
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return 'No JSON'
            return '{"title":"Titolo","description":"Storia.","tags":["storia"]}'
        with self.assertRaisesRegex(ValueError, 'wrong actor'):
            generate_youtube_metadata('Story', '', '', 'Italian', call)

    def test_resume_reviews_saved_candidate_without_generating_again(self):
        from background_jobs import metadata_for_job, JobProgress
        progress = JobProgress()
        candidate = '{"title":"Titolo","description":"Storia.","tags":["storia"]}'
        def broken(prompt):
            return 'No verdict' if 'REVIEW' in prompt else candidate
        with self.assertRaises(ValueError):
            metadata_for_job('Story', '', '', 'Italian', broken, progress)
        self.assertTrue(progress.partial_result()['seo_work_json'])
        prompts = []
        def recovered(prompt):
            prompts.append(prompt)
            return '{"ok":true,"issues":[]}'
        self.assertEqual(metadata_for_job('Story', '', '', 'Italian', recovered, progress)[0], 'Titolo')
        self.assertEqual(len(prompts), 1)
        self.assertTrue(prompts[0].startswith('TARGET_METADATA_REVIEW'))
        self.assertEqual(progress.partial_result()['seo_work_json'], '')

    def test_strict_99_character_title(self):
        base={'description':'Nội dung','tags':['gia đình']}
        self.assertEqual(len(validate_metadata(dict(base,title='a'*99))[0]),99)
        with self.assertRaises(ValueError):validate_metadata(dict(base,title='a'*100))

    def test_overlong_title_rewritten_and_reviewed(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            if prompt.startswith('TARGET_METADATA_REVIEW'):return '{"ok":true,"issues":[]}'
            return json.dumps({'title':'a'*100 if len(calls)==1 else 'Bà bật khóc trước món quà của cháu gái','description':'Câu chuyện hai bà cháu.','tags':['gia đình','tình bà cháu']})
        result=generate_youtube_metadata('Cháu tặng tranh khiến bà khóc.','Gift','Desc','Vietnamese',call)
        self.assertLess(len(result[0]),100)
        self.assertIn('99',calls[1])
        self.assertEqual(len(calls),3)

    def test_wrong_language_or_invented_hook_rejected(self):
        calls=[]
        def call(prompt):
            calls.append(prompt)
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                return '{"ok":false,"issues":["Wrong language and invented twist"]}'
            return '{"title":"Wrong hook","description":"Wrong description","tags":["irrelevant"]}'
        with self.assertRaises(ValueError):generate_youtube_metadata('Story','','','Italian',call)
        self.assertEqual(len(calls),6)

    def test_tags_deduplication_and_limit(self):
        result=validate_metadata({'title':'Title','description':'Desc','tags':['#family','Family','family story']})
        self.assertEqual(result[2],'family, family story')
        with self.assertRaises(ValueError):validate_metadata({'title':'Title','description':'Desc','tags':['x'*501]})

    def test_faithful_review_retries_creative_rewrite_against_full_originals(self):
        original_title = 'A grandmother receives a painting'
        original_description = 'A gift from her granddaughter.\n\nCredits: Anna\nhttps://example.com/source'
        calls = []
        generations = []
        def call(prompt):
            calls.append(prompt)
            source = json.loads(prompt.split('SOURCE DATA:\n', 1)[1])
            self.assertEqual(source['original_title'], original_title)
            self.assertEqual(source['original_description'], original_description)
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                self.assertIn('faithful translations, not creative', prompt)
                if len(generations) == 1:
                    return json.dumps({'ok': False, 'issues': ['Added emotional hook absent from original title']})
                return '{"ok":true,"issues":[]}'
            self.assertIn('as faithfully as possible', prompt)
            if generations:
                self.assertIn('Added emotional hook', prompt)
            generations.append(source)
            return json.dumps({'title': 'Bà bật khóc vì bí mật của cháu' if len(generations) == 1 else 'Một người bà nhận được bức tranh',
                               'description': 'Món quà từ cháu gái.\n\nCredits: Anna\nhttps://example.com/source',
                               'tags': ['bà và cháu']})
        result = generate_youtube_metadata('Some additional emotional story context', original_title, original_description, 'Tiếng Việt', call)
        self.assertEqual(result[0], 'Một người bà nhận được bức tranh')
        self.assertIn('\n\nCredits: Anna\nhttps://example.com/source', result[1])
        self.assertEqual(len(calls), 4)

    def test_missing_description_uses_translated_narration_and_allows_relevant_emoji(self):
        calls = []
        description = '🎨 Người cháu tặng bà một bức tranh.\n\n💛 Một món quà thể hiện tình cảm gia đình.'
        def call(prompt):
            calls.append(prompt)
            data = json.loads(prompt.split('SOURCE DATA:\n', 1)[1])
            self.assertEqual(data['story_context'], 'Người cháu tặng bà một bức tranh.')
            self.assertEqual(data['original_title'], 'A painting for grandma')
            if prompt.startswith('TARGET_METADATA_REVIEW'):
                self.assertIn('accept a newly written description', prompt)
                self.assertEqual(data['candidate']['description'], description)
                return '{"ok":true,"issues":[]}'
            self.assertIn('original description is absent', prompt)
            self.assertIn('few relevant emoji', prompt)
            self.assertNotIn('Do not add an introduction', prompt)
            return json.dumps({'title':'Bức tranh dành cho bà','description':description,'tags':['tình cảm gia đình']})
        result = generate_youtube_metadata('Người cháu tặng bà một bức tranh.', 'A painting for grandma', '  ', 'Tiếng Việt', call)
        self.assertEqual(result[1], description)
        self.assertEqual(len(calls), 2)
