"""Local integration tests; no paid API access required."""
import base64
import http.client
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as app


class MovieStudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.fixtures = cls.root / 'fixture.mp4'
        subprocess.run([shutil.which('ffmpeg'), '-nostdin','-y','-loglevel','error',
                        '-f','lavfi','-i','color=c=purple:s=320x180:r=15:d=0.6',
                        '-f','lavfi','-i','sine=frequency=440:duration=0.6',
                        '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',
                        str(cls.fixtures)],check=True)
        cls.original = {name:getattr(app,name) for name in ['DATA','VIDEOS','PHOTOS','JOBS_FILE','PHOTOS_FILE','JOBS','PHOTO_LIBRARY','FAL_KEY','APP_PASSWORD']}
        app.DATA=cls.root/'data';app.VIDEOS=cls.root/'videos';app.PHOTOS=cls.root/'photos'
        for folder in [app.DATA,app.VIDEOS,app.PHOTOS]:folder.mkdir()
        app.JOBS_FILE=app.DATA/'jobs.json';app.PHOTOS_FILE=app.DATA/'photos.json'
        app.JOBS={};app.PHOTO_LIBRARY={};app.FAL_KEY='local-test-only';app.APP_PASSWORD='secret'
        cls.httpd=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True)
        cls.thread.start()
        cls.port=cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join(timeout=2)
        for name,value in cls.original.items():setattr(app,name,value)
        cls.temp.cleanup()

    def call(self,method,path,payload=None,headers=None):
        headers=dict(headers or {})
        headers['Authorization']='Basic '+base64.b64encode(b'owner:secret').decode('ascii')
        if isinstance(payload,dict):
            payload=json.dumps(payload).encode()
            headers['Content-Type']='application/json'
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        conn.request(method,path,body=payload,headers=headers)
        resp=conn.getresponse();raw=resp.read();status=resp.status;info=dict(resp.getheaders());conn.close()
        return status,raw,info

    def upload_photo(self):
        # Real 1x1 PNG, small enough for API validation (the image handler checks bytes).
        img=(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==')+b'\x00'*64)
        status,body,_=self.call('POST','/api/photos',img,{'X-Photo-Consent':'yes','X-Photo-Name':'hero.png','Content-Type':'image/png'})
        self.assertEqual(status,201,body)
        return json.loads(body)['photo']['id']

    def test_01_auth_and_health(self):
        conn=http.client.HTTPConnection('127.0.0.1',self.port)
        conn.request('GET','/healthz');self.assertEqual(conn.getresponse().status,200)
        conn.request('GET','/api/photos');self.assertEqual(conn.getresponse().status,401)
        conn.close()

    def test_02_photo_upload_and_private_access(self):
        s,b,_=self.call('POST','/api/photos',b'\xff\xd8\xff'+b'0'*80+b'\xff\xd9')
        self.assertEqual(s,400)
        pid=self.upload_photo()
        s,b,headers=self.call('GET',f'/api/photos/{pid}')
        self.assertEqual(s,200)
        self.assertEqual(headers['Content-Type'],'image/png')
        self.assertTrue(b.startswith(b'\x89PNG'))
        s,b,_=self.call('GET','/api/photos')
        self.assertEqual(s,200)
        self.assertTrue(any(p['id']==pid for p in json.loads(b)['photos']))

    def test_03_provider_image_payload(self):
        pid=self.upload_photo()
        args=[]
        def fake_fal(url,*,payload=None):
            args.append((url,payload))
            if payload is not None:return {'request_id':'mock','status_url':'https://queue.fal.run/mock/status','response_url':'https://queue.fal.run/mock/result'}
            if url.endswith('/status'):return {'status':'COMPLETED'}
            return {'video':{'url':'https://fal.media/mock.mp4'}}
        with patch.object(app,'fal_request',side_effect=fake_fal),patch.object(app,'download_generated_video',side_effect=lambda u,p:shutil.copyfile(self.fixtures,p)),patch.object(app.time,'sleep'):
            path=self.root/'photo-video.mp4'
            app.render_one('The actor waves to the camera','9:16','720p',5,[pid],path,lambda x:None)
        self.assertTrue(path.exists())
        self.assertIn('/image-to-video',args[0][0])
        self.assertTrue(args[0][1]['image_url'].startswith('data:image/png;base64,'))
        args.clear()
        with patch.object(app,'fal_request',side_effect=fake_fal),patch.object(app,'download_generated_video',side_effect=lambda u,p:shutil.copyfile(self.fixtures,p)),patch.object(app.time,'sleep'):
            app.render_one('The two actors talk','16:9','720p',5,[pid,self.upload_photo()],self.root/'two-actors.mp4',lambda x:None)
        self.assertIn('/reference-to-video',args[0][0])
        self.assertEqual(len(args[0][1]['image_urls']),2)

    def test_04_story_validation_and_movie_assembly(self):
        pid=self.upload_photo()
        spec={'title':'Ruthless','plot':'Two childhood friends face a neighborhood betrayal and a hard choice.',
              'genre':'Street crime drama','tone':'Gritty realistic',
              'scenes':['Introduce the lead by his corner store and his old friend.',
                        'The two friends argue about a mysterious message from family.',
                        'They reconcile during an emotional sunset conversation.'],
              'duration':5,'resolution':'720p','aspect_ratio':'16:9','photo_ids':[pid],
              'photo_consent':True,'acknowledge_cost':False}
        status,b,_=self.call('POST','/api/movies',spec)
        self.assertEqual(status,400)
        self.assertIn('Confirm',b.decode())
        spec['acknowledge_cost']=True
        def fake_render(*args):
            path=args[5]
            shutil.copyfile(self.fixtures,path)
            args[6]('Test footage rendered')
        with patch.object(app,'render_one',side_effect=fake_render):
            status,b,_=self.call('POST','/api/movies',spec)
            self.assertEqual(status,202,b)
            job=json.loads(b)['job'];jid=job['id']
            for i in range(100):
                if app.JOBS[jid]['status'] in ('completed','failed'):break
                time.sleep(.07)
        self.assertEqual(app.JOBS[jid]['status'],'completed',app.JOBS[jid].get('error'))
        self.assertEqual(len(app.JOBS[jid]['completed_scenes']),3)
        status,video,headers=self.call('GET',f'/api/video/{jid}',headers={'Range':'bytes=0-99'})
        self.assertEqual(status,206)
        self.assertEqual(len(video),100)
        self.assertEqual(headers['Accept-Ranges'],'bytes')
        s,b,_=self.call('GET',f'/api/video/{jid}/scene/2')
        self.assertEqual(s,200)
        self.assertGreater(len(b),500)


if __name__=='__main__':unittest.main()
