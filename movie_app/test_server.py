import unittest
from movie_app.server import video_id
class Tests(unittest.TestCase):
 def test_links(self):
  for link in ['https://youtu.be/2MT2ATgU3B8','https://www.youtube.com/watch?v=2MT2ATgU3B8','https://youtube.com/shorts/2MT2ATgU3B8']:
   self.assertEqual(video_id(link),'2MT2ATgU3B8')
 def test_reject_other_hosts(self):
  for link in ['http://127.0.0.1/','https://youtube.com.evil.org/watch?v=2MT2ATgU3B8','https://youtube.com/watch?v=bad']:
   with self.assertRaises(ValueError):video_id(link)
if __name__=='__main__':unittest.main()
