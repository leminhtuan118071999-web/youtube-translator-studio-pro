import os
import tempfile
import unittest
from unittest.mock import patch
from v3 import projects, pixabay


class SelectionTests(unittest.TestCase):
    def test_projects_get_distinct_batches_and_retry_keeps_same_ids(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            first=projects.project_dir(projects.create('First')['id'])
            second=projects.project_dir(projects.create('Second')['id'])
            hits=[dict(id=i,url=f'https://cdn.pixabay.com/{i}.mp4') for i in range(50)]
            with patch.object(pixabay,'search',return_value=hits):
                a=pixabay.select_for_project(first,'forest')
                b=pixabay.select_for_project(second,'forest',preferred=a)
            self.assertEqual(len(a),15);self.assertEqual(len(b),15)
            self.assertFalse({h['id'] for h in a}&{h['id'] for h in b})
            with patch.object(pixabay,'search',side_effect=AssertionError('must reuse reservation')):
                self.assertEqual(pixabay.select_for_project(first,'other query'),a)

    def test_exhaustion_does_not_reuse_old_ids_or_write_partial_reservation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            first=projects.project_dir(projects.create('Old')['id'])
            projects.atomic(first/'pixabay-downloads.json',{'1':{'file':'old.mp4'}})
            folder=projects.project_dir(projects.create('New')['id'])
            with patch.object(pixabay,'search',side_effect=lambda *args,**kwargs: [{'id':i} for i in range(1,15)] if kwargs.get('page')==1 else []):
                with self.assertRaisesRegex(ValueError,'cần 15'):
                    pixabay.select_for_project(folder,'forest')
            self.assertFalse((folder/'pixabay-selection.json').exists())

    def test_related_query_finds_new_videos_without_unrelated_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('New')['id'])
            def search(query, page=1):
                return [{'id':i} for i in range(15)] if query=='woodland sunlight' else []
            with patch.object(pixabay,'search',side_effect=search):
                self.assertEqual(len(pixabay.select_for_project(folder,'forest sunlight')),15)
            self.assertEqual(pixabay.related_queries('special unknown subject'),['special unknown subject'])
            self.assertTrue(all('sunlight' in q for q in pixabay.related_queries('forest sunlight')))

    def test_more_pages_supply_fresh_ids(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('New')['id'])
            projects.atomic(projects.home()/'pixabay-history.json',{str(i):'old' for i in range(50)})
            with patch.object(pixabay,'search',side_effect=[[{'id':i} for i in range(50)],[{'id':i} for i in range(50,100)]]) as search:
                result=pixabay.select_for_project(folder,'forest')
                self.assertEqual(search.call_count,2)
                self.assertTrue(all(h['id']>=50 for h in result))


if __name__=='__main__':unittest.main()
