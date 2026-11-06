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
            with patch.object(pixabay,'search',side_effect=lambda query,page=1: [{'id':i} for i in range(50)] if page==1 else [{'id':i} for i in range(50,100)]) as search:
                result=pixabay.select_for_project(folder,'forest')
                self.assertLessEqual(search.call_count,10)
                self.assertTrue(all(h['id']>=50 for h in result))

    def test_plentiful_results_are_mixed_from_three_queries_then_stop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Mixed')['id'])
            queries=pixabay.related_queries('forest sunlight')[:3]
            def search(term,page=1):
                start=queries.index(term)*100
                return [dict(id=start+i,origin=term) for i in range(50)]
            updates=[]
            with patch.object(pixabay,'search',side_effect=search) as api:
                result=pixabay.select_for_project(folder,'forest sunlight',update=updates.append)
            self.assertEqual(api.call_count,3)
            self.assertEqual(len({h['id'] for h in result}),15)
            self.assertEqual({term:sum(h['origin']==term for h in result) for term in queries},dict.fromkeys(queries,5))
            self.assertEqual(projects.read(folder/'pixabay-selection.json')['searched_queries'],queries)
            self.assertIn('15 video',updates[-1])

    def test_duplicate_results_and_exhaustion_keep_ten_request_cap(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Duplicates')['id'])
            with patch.object(pixabay,'search',return_value=[{'id':1}]*50) as api:
                with self.assertRaises(ValueError):pixabay.select_for_project(folder,'forest sunlight')
            self.assertEqual(api.call_count,10)
            self.assertFalse((folder/'pixabay-selection.json').exists())

    def test_cancelled_search_does_not_reserve_ids(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Cancel')['id'])
            cancel=Path(tmp)/'cancel';cancel.touch()
            with patch.object(pixabay,'search') as api:
                with self.assertRaises(pixabay.Cancelled):pixabay.select_for_project(folder,'forest',cancel=cancel)
            api.assert_not_called()
            self.assertFalse((folder/'pixabay-selection.json').exists())

    def test_theme_variants_keep_explicit_qualifiers(self):
        for query,qualifier in [('city night','night'),('snow winter','winter'),('luxury mansion','luxury'),('office interior','interior')]:
            variants=pixabay.related_queries(query)
            self.assertGreater(len(variants),1)
            self.assertTrue(all(qualifier in term for term in variants))


if __name__=='__main__':unittest.main()

