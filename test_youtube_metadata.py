import json
import unittest
from youtube_metadata import validate_metadata, generate_youtube_metadata

class MetadataTests(unittest.TestCase):
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
