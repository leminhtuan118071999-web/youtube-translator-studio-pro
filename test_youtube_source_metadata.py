import json
import unittest
from unittest.mock import patch,MagicMock
from youtube_source_metadata import parse_player_metadata,fetch_source_metadata,MAX_PAGE_BYTES

VIDEO='S491shgHrLo'
class SourceMetadataTests(unittest.TestCase):
    def page(self,**details):return 'var ytInitialPlayerResponse = '+json.dumps(dict(videoDetails=dict(videoId=VIDEO,**details)))+';'
    def test_exact_original_description_links_and_tags(self):
        description='First line\n00:30 Details https://example.test?a=1&b=2'
        data=parse_player_metadata(self.page(title='A title',shortDescription=description,keywords=['tag one','tag, two']),VIDEO)
        self.assertEqual(data['description'],description);self.assertEqual(data['tags'],['tag one','tag, two'])
        self.assertEqual(set(data['status'].values()),{'fetched'})
    def test_missing_is_not_reported_as_explicitly_empty(self):
        data=parse_player_metadata(self.page(title='Title',shortDescription='',keywords=[]),VIDEO)
        self.assertEqual(data['status']['tags'],'empty');self.assertEqual(data['status']['description'],'empty')
        data=parse_player_metadata(self.page(title='Title'),VIDEO)
        self.assertEqual(data['status']['tags'],'unavailable');self.assertEqual(data['status']['description'],'unavailable')
    def test_wrong_video_or_invalid_json_cannot_supply_metadata(self):
        for page in [self.page(title='Wrong').replace(VIDEO,'abcdefghijk'),'var ytInitialPlayerResponse = {broken']:
            self.assertEqual(set(parse_player_metadata(page,VIDEO)['status'].values()),{'unavailable'})

    def test_network_failure_preserves_unknown_fields_without_inventing_tags(self):
        import requests
        with patch('youtube_source_metadata.requests.get',side_effect=requests.Timeout):
            result=fetch_source_metadata(VIDEO)
        self.assertEqual(set(result['status'].values()),{'unavailable'})
        self.assertNotIn('tags',result)
    def test_valid_page_needs_only_one_request_and_rejects_invalid_ids(self):
        response=MagicMock();response.__enter__.return_value=response
        response.ok=True;response.status_code=200
        response.iter_content.return_value=[self.page(title='Title',shortDescription='Description',keywords=['original']).encode()]
        with patch('youtube_source_metadata.requests.get',return_value=response) as get:
            self.assertEqual(fetch_source_metadata(VIDEO)['tags'],['original'])
            self.assertEqual(get.call_count,1)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])
            with self.assertRaises(ValueError):fetch_source_metadata('https://evil.test')
            self.assertEqual(get.call_count,1)
    def test_original_tags_are_translated_instead_of_generated(self):
        from youtube_metadata import generate_youtube_metadata
        prompts=[]
        def call(prompt):prompts.append(prompt);return '{"title":"Title","description":"Description","tags":["translated tag"]}'
        result=generate_youtube_metadata('Story','Original','Original description','English',call,self_check_only=True,original_tags=['tag gốc'])
        self.assertEqual(len(prompts),1)
        data=json.loads(prompts[0].split('SOURCE DATA:\n',1)[1])
        self.assertEqual(data['original_tags'],['tag gốc'])
        self.assertIn('faithfully translate original_tags',prompts[0])
        self.assertNotIn('around 15 distinct',prompts[0])

    def test_complete_original_metadata_skips_story_summary_calls(self):
        from background_jobs import metadata_for_job,JobProgress
        source='Opening context. '+('Long story sentence. '*6000)+' Final context.'
        prompts=[]
        def call(prompt):
            prompts.append(prompt)
            self.assertTrue(prompt.startswith('TARGET_METADATA.'))
            return '{"title":"Title","description":"Description","tags":["translated tag"]}'
        with patch('background_jobs.overview',side_effect=AssertionError('Unnecessary story summary')):
            result=metadata_for_job(source,'Original title','Original description','English',call,
                                    JobProgress(),fast=True,original_tags=['original tag'])
        self.assertEqual(len(prompts),1)
        data=json.loads(prompts[0].split('SOURCE DATA:\n',1)[1])
        self.assertEqual(data['original_title'],'Original title')
        self.assertEqual(data['original_description'],'Original description')
        self.assertEqual(data['original_tags'],['original tag'])
        self.assertLess(len(data['story_context']),3000)
        self.assertIn('Opening context.',data['story_context'])
        self.assertIn('Final context.',data['story_context'])
        self.assertIn('not a complete plot summary',data['story_context'])
        self.assertEqual(result[2],'translated tag')

    def test_missing_original_fields_keep_whole_story_context(self):
        from background_jobs import metadata_for_job,JobProgress
        source='Complete story. '*3000
        for title,description,tags in [('', 'Description',['tag']),('Title','',['tag']),('Title','Description',[])]:
            with self.subTest(title=title,description=description,tags=tags):
                with patch('background_jobs.overview',return_value='Whole-story summary') as summary:
                    metadata_for_job(source,title,description,'English',
                        lambda _: '{"title":"Title","description":"Description","tags":["tag"]}',
                        JobProgress(),fast=True,original_tags=tags)
                summary.assert_called_once()
                self.assertEqual(summary.call_args.args[0],source)

if __name__=='__main__':unittest.main()
