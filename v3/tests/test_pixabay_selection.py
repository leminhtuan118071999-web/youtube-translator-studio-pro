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
            hits=[dict(id=i,width=1920,height=1080,url=f'https://cdn.pixabay.com/{i}.mp4') for i in range(50)]
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
            with patch.object(pixabay,'search',side_effect=lambda *args,**kwargs: [{'id':i,'width':1920,'height':1080} for i in range(1,15)] if kwargs.get('page')==1 else []):
                with self.assertRaisesRegex(ValueError,'cần 15'):
                    pixabay.select_for_project(folder,'forest')
            self.assertFalse((folder/'pixabay-selection.json').exists())

    def test_related_query_finds_new_videos_without_unrelated_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('New')['id'])
            def search(query, page=1, *, ratio='16:9'):
                return [{'id':i,'width':1920,'height':1080} for i in range(15)] if query=='woodland sunlight' else []
            with patch.object(pixabay,'search',side_effect=search):
                self.assertEqual(len(pixabay.select_for_project(folder,'forest sunlight')),15)
            self.assertEqual(pixabay.related_queries('special unknown subject'),['special unknown subject'])
            self.assertTrue(all('sunlight' in q for q in pixabay.related_queries('forest sunlight')))

    def test_more_pages_supply_fresh_ids(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('New')['id'])
            projects.atomic(projects.home()/'pixabay-history.json',{str(i):'old' for i in range(50)})
            with patch.object(pixabay,'search',side_effect=lambda query,page=1,**kwargs: [{'id':i,'width':1920,'height':1080} for i in range(50)] if page==1 else [{'id':i,'width':1920,'height':1080} for i in range(50,100)]) as search:
                result=pixabay.select_for_project(folder,'forest')
                self.assertLessEqual(search.call_count,10)
                self.assertTrue(all(h['id']>=50 for h in result))

    def test_plentiful_results_are_mixed_from_three_queries_then_stop(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Mixed')['id'])
            queries=pixabay.diversity_queries('forest sunlight')[:3]
            def search(term,page=1,*,ratio='16:9'):
                start=queries.index(term)*100
                return [dict(id=start+i,width=1920,height=1080,origin=term) for i in range(50)]
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
            with patch.object(pixabay,'search',return_value=[{'id':1,'width':1920,'height':1080}]*50) as api:
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

    def test_only_16_9_dimensions_are_accepted(self):
        for w,h in [(1920,1080),(1280,720),(854,480),(3840,2160)]:
            self.assertTrue(pixabay.is_widescreen(dict(width=w,height=h)))
        for w,h in [(1080,1920),(1080,1080),(1440,1080),(1920,800),(0,0),(None,720)]:
            self.assertFalse(pixabay.is_widescreen(dict(width=w,height=h)))

    def test_search_filters_each_variant_and_cache(self):
        import json
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            pixabay.save_key('test-key')
            def video(w,h):return dict(width=w,height=h,size=100,url=f'https://cdn.pixabay.com/{w}-{h}.mp4')
            response=MagicMock();response.__enter__.return_value=response
            response.read.return_value=json.dumps(dict(hits=[
                dict(id=1,pageURL='https://pixabay.com/videos/id-1/',videos=dict(small=video(1280,720),large=video(1080,1920))),
                dict(id=2,pageURL='https://pixabay.com/videos/id-2/',videos=dict(small=video(1080,1080))),
                dict(id=3,pageURL='https://pixabay.com/videos/id-3/',videos=dict(small=video(1920,800))),
            ])).encode()
            with patch.object(pixabay,'urlopen',return_value=response) as api:
                first=pixabay.search('forest');second=pixabay.search('forest')
                portrait=pixabay.search('forest',ratio='9:16')
                self.assertEqual(portrait,pixabay.search('forest',ratio='9:16'))
            self.assertEqual([h['id'] for h in first],[1])
            self.assertEqual(first,second);self.assertEqual(api.call_count,2)
            self.assertEqual([(h['width'], h['height']) for h in portrait],[(1080,1920)])
            self.assertEqual(first[0]['width'],1280)

    def test_switching_ratio_keeps_separate_reservations_and_avoids_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Both ratios')['id'])
            def search(query, page=1, *, ratio='16:9'):
                width,height=(1920,1080) if ratio=='16:9' else (1080,1920)
                return [dict(id=i,width=width,height=height) for i in range(40)]
            with patch.object(pixabay,'search',side_effect=search):
                landscape=pixabay.select_for_project(folder,'forest')
                portrait=pixabay.select_for_project(folder,'forest',ratio='9:16')
                self.assertEqual(pixabay.select_for_project(folder,'forest'),landscape)
            self.assertEqual(len(portrait),15)
            self.assertTrue(all(pixabay.matches_ratio(h,'9:16') for h in portrait))
            self.assertFalse({h['id'] for h in landscape} & {h['id'] for h in portrait})

    def test_wrong_ratio_replacement_keeps_the_other_reserved_clips(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Replacement')['id'])
            hits=[dict(id=i,width=1080,height=1920) for i in range(50)]
            with patch.object(pixabay,'search',return_value=hits):
                first=pixabay.select_for_project(folder,'forest',ratio='9:16')
                rejected=first[0]['id']
                pixabay.drop_reserved_video(folder,'9:16',rejected)
                second=pixabay.select_for_project(folder,'forest',ratio='9:16')
            ids={h['id'] for h in second}
            self.assertEqual(len(ids),15)
            self.assertNotIn(rejected,ids)
            self.assertTrue({h['id'] for h in first[1:]} <= ids)

    def test_invalid_preferred_videos_cannot_be_reserved(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Portrait')['id'])
            wrong=[dict(id=i,width=1080,height=1920) for i in range(15)]
            with patch.object(pixabay,'search',return_value=[]):
                with self.assertRaises(ValueError):pixabay.select_for_project(folder,'forest',preferred=wrong)
            self.assertFalse((folder/'pixabay-selection.json').exists())

    def test_portrait_download_is_rejected_before_network(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,LMT_V3_HOME=tmp):
            folder=projects.project_dir(projects.create('Download')['id'])
            with patch('urllib.request.build_opener') as opener:
                with self.assertRaisesRegex(ValueError,'16:9'):
                    pixabay.download(folder,[dict(id=1,width=1080,height=1920)],Path(tmp)/'cancel',lambda *a:None)
                opener.return_value.open.assert_not_called()

    def test_diversity_expands_related_scenery_without_losing_modifiers(self):
        self.assertEqual(pixabay.diversity_queries('forest sunlight')[:3],
                         ['forest sunlight','river sunlight','mountain landscape sunlight'])
        for query in ['city night','forest winter','mountain landscape sunset']:
            modifier=query.split()[-1]
            self.assertTrue(all(modifier in q for q in pixabay.diversity_queries(query)))
        self.assertEqual(pixabay.diversity_queries('special unknown subject'),['special unknown subject'])
        self.assertNotIn('river fire',pixabay.diversity_queries('forest fire'))


if __name__=='__main__':unittest.main()

