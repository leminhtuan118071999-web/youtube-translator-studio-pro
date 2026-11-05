import json
import unittest
from movie_app.ai import generate

class ContinuityTests(unittest.TestCase):
    def test_generation_requires_states(self):
        shot=dict(characters=['Anna'],speaker='',dialogue='',action='opens door',location='room',camera='wide',wardrobe='coat')
        data=dict(mode='shots',context='Previous ending: Anna holds the handle.',maximum=1,characters=[{'name':'Anna'}])
        with self.assertRaisesRegex(ValueError,'nối cảnh'):
            generate(data,lambda _:json.dumps({'shots':[shot]}))
        shot.update(story_beat='Enters room',continuity_start='Hand on handle outside',continuity_end='Inside room, door open',transition_context='Immediate continuation')
        prompts=[]
        def call(prompt):
            prompts.append(prompt)
            return json.dumps({'shots':[shot]})
        result=generate(data,call)
        self.assertEqual(result['shots'][0]['continuity_end'],'Inside room, door open')
        self.assertIn('new camera angle alone is not a new story beat',prompts[0])
if __name__=='__main__':unittest.main()
