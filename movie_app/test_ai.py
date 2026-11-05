import unittest
from movie_app.ai import generate
class Tests(unittest.TestCase):
 def test_bad_json(self):
  with self.assertRaises(ValueError):generate({'mode':'analyze','context':'story'},lambda _: 'not json')
 def test_cast(self):
  d=generate({'mode':'cast','context':'story'},lambda _: '{"characters":[{"name":"Tulio","appearance":"suit","voice":"low","evidence":"driver"}]}')
  self.assertTrue(d['characters'][0]['design_proposed'])
 def test_alias_duplicate(self):
  c={'name':'Tulio','appearance':'','voice':'','evidence':''}
  import json
  with self.assertRaises(ValueError):generate({'mode':'cast','context':'story'},lambda _:json.dumps({'characters':[c,c]}))
 def test_wrong_speaker(self):
  import json
  shot={'characters':['Tulio'],'speaker':'Unknown','dialogue':'Hello','action':'wait','location':'car','camera':'close','wardrobe':'suit'}
  with self.assertRaises(ValueError):generate({'mode':'shots','context':'story','maximum':2,'characters':[{'name':'Tulio'}]},lambda _:json.dumps({'shots':[shot]}))
 def test_notes(self):
  d=generate({'mode':'analyze','context':'final event'},lambda p:'{"notes":"final event"}')
  self.assertEqual(d['notes'],'final event')
if __name__=='__main__':unittest.main()
