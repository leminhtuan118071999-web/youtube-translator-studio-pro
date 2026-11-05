"""Local-only YouTube captions bridge; no arbitrary URL fetching."""
import json,re,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parent

def video_id(url):
    p=urlparse(url.strip());host=(p.hostname or '').lower()
    if p.scheme!='https' or host not in {'youtube.com','www.youtube.com','m.youtube.com','youtu.be'}: raise ValueError('Hãy dùng link HTTPS YouTube hoặc youtu.be.')
    value=p.path.strip('/').split('/')[0] if host=='youtu.be' else parse_qs(p.query).get('v',[''])[0]
    if host!='youtu.be' and p.path.startswith(('/shorts/','/embed/','/live/')): value=p.path.split('/')[2]
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',value): raise ValueError('Không đọc được mã video từ link.')
    return value

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,data):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path.split('?')[0] not in {'/','/index.html'}: self.send_error(404);return
        raw=(ROOT/'index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if self.path!='/api/youtube': self.send_error(404);return
        if self.headers.get('Origin') not in {None,'http://127.0.0.1:8505','http://localhost:8505'}: self.respond(403,{'error':'Nguồn yêu cầu không hợp lệ.'});return
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<10000: raise ValueError('Yêu cầu không hợp lệ.')
            data=json.loads(self.rfile.read(size));vid=video_id(data.get('url',''))
        except (ValueError,TypeError) as e: self.respond(400,{'error':str(e)});return
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            tracks=list(YouTubeTranscriptApi().list(vid))
            tracks.sort(key=lambda t:(t.is_generated,t.language_code not in {'vi','en'}))
            transcript=None
            for track in tracks:
                try: transcript=track.fetch();break
                except Exception: continue
            if transcript is None: raise RuntimeError('Không lấy được phụ đề.')
            segments=[{'start':x.start,'duration':x.duration,'text':x.text} for x in transcript]
            text='\n'.join(x['text'] for x in segments)
            if len(text)>350000: self.respond(413,{'error':'Nguồn vượt 350.000 ký tự; cần chia thành nhiều dự án. Không cắt bớt nguồn.'});return
            self.respond(200,{'video_id':vid,'source':text,'language':track.language_code,'automatic':track.is_generated,'segments':segments,'visual_analysis':False})
        except Exception:
            self.respond(422,{'error':'Không lấy được phụ đề: video có thể không có phụ đề, bị giới hạn hoặc YouTube chặn truy cập. Hãy dán nội dung hoặc tải TXT/SRT/VTT. Chưa phân tích hình ảnh hay tách lời thoại theo nhân vật.'})
if __name__=='__main__':
    print('LMT Film Builder: http://127.0.0.1:8505',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8505),Handler).serve_forever()
