"""Business-mode integration tests with a local HTTP server, no paid providers."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import unittest
import requests

APP=Path(__file__).resolve().parents[1]

class BusinessPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));cls.port=sock.getsockname()[1]
        env=dict(os.environ,PORT=str(cls.port),HOST='127.0.0.1',BUSINESS_MODE='1',COOKIE_SECURE='0',STORAGE_ROOT=cls.tmp.name,
                 BUSINESS_DB_PATH=str(Path(cls.tmp.name)/'data'/'accounts.db'),OWNER_EMAIL='owner@example.com',
                 OWNER_INVITE_CODE='very-long-private-owner-invitation-code-12345',FAL_KEY='fake-local-test-key',SIGNUPS_ENABLED='1')
        cls.process=subprocess.Popen(['python','server.py'],cwd=APP,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.base='http://127.0.0.1:'+str(cls.port)
        for i in range(60):
            try:
                if requests.get(cls.base+'/healthz',timeout=.5).status_code==200:break
            except requests.RequestException:time.sleep(.1)
        else:raise RuntimeError('Business server did not start')
    @classmethod
    def tearDownClass(cls):
        cls.process.terminate();cls.process.wait(timeout=6);cls.tmp.cleanup()
    def test_01_public_pages_and_login(self):
        for page in ['/','/pricing','/login','/studio','/admin','/dashboard']:
            r=requests.get(self.base+page);self.assertEqual(r.status_code,200,page)
        self.assertEqual(requests.get(self.base+'/api/jobs').status_code,401)
    def test_02_user_owner_and_isolation(self):
        owner=requests.Session()
        r=owner.post(self.base+'/api/auth/register',json={'email':'owner@example.com','name':'IconEnt Owner','password':'ThisIsA-Strong-Password-56',
                          'owner_code':'very-long-private-owner-invitation-code-12345'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['user']['role'],'owner')
        self.assertEqual(owner.get(self.base+'/api/auth/me').json()['user']['role'],'owner')
        r=owner.post(self.base+'/api/auth/register',json={'email':'other-owner@example.com','name':'Random','password':'strongpass1234567',
                          'owner_code':'fake'})
        self.assertEqual(r.status_code,400)
        customer=requests.Session()
        r=customer.post(self.base+'/api/auth/register',json={'email':'guest@example.com','name':'Guest User','password':'longAndStrongPassword1234'})
        self.assertEqual(r.status_code,200,r.text)
        uid=r.json()['user']['id'];self.assertEqual(r.json()['user']['credits'],0)
        self.assertEqual(customer.get(self.base+'/api/admin/stats').status_code,403)
        sample=b'\xff\xd8\xff'+b'0'*80+b'\xff\xd9'
        photo=owner.post(self.base+'/api/photos',data=sample,headers={'X-Photo-Consent':'yes','X-Photo-Name':'owner-cast.jpg'})
        self.assertEqual(photo.status_code,201,photo.text)
        pid=photo.json()['photo']['id']
        self.assertEqual(customer.get(self.base+'/api/photos/'+pid).status_code,404)
        self.assertEqual(len(customer.get(self.base+'/api/photos').json()['photos']),0)
        self.assertEqual(customer.delete(self.base+'/api/photos/'+pid).json()['deleted'],False)
        self.assertEqual(owner.get(self.base+'/api/photos/'+pid).status_code,200)
        self.assertEqual(owner.get(self.base+'/api/admin/users').status_code,200)
        r=owner.post(self.base+'/api/admin/grant',json={'user_id':uid,'amount':12});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(customer.get(self.base+'/api/account/summary').json()['user']['credits'],12)
        self.assertEqual(owner.get(self.base+'/api/account/summary').json()['user']['credits'],0)
        # No payment processor is configured: verify checkout cannot create a charge.
        r=customer.post(self.base+'/api/billing/checkout',json={'sku':'starter'})
        self.assertEqual(r.status_code,400,r.text)
        # Zero fal requests: separately test that owner is not charged within app.
        self.assertEqual(owner.get(self.base+'/api/pricing').status_code,200)
        # No unrelated user can access the owner image as a video reference.
        video=customer.post(self.base+'/api/jobs',json={'prompt':'The character waves at sunset','aspect_ratio':'16:9',
         'resolution':'720p','duration':5,'photo_ids':[pid],'photo_consent':True})
        self.assertEqual(video.status_code,400,video.text)
        # Credit reservation works when we submit a render. The real provider will fail (local test), then credits refund.
        result=customer.post(self.base+'/api/jobs',json={'prompt':'The character waves at sunset','aspect_ratio':'16:9',
             'resolution':'720p','duration':5,'photo_ids':[],'photo_consent':False})
        self.assertEqual(result.status_code,202,result.text)
        jid=result.json()['job']['id'];self.assertEqual(result.json()['job']['credits_used'],2)
        self.assertEqual(owner.get(self.base+'/api/jobs/'+jid).status_code,404)
        for i in range(40):
            stat=customer.get(self.base+'/api/jobs/'+jid).json()['job']['status']
            if stat in ['failed','completed']:break
            time.sleep(.1)
        self.assertEqual(stat,'failed')
        self.assertEqual(customer.get(self.base+'/api/account/summary').json()['user']['credits'],12)
        r=customer.post(self.base+'/api/auth/logout',json={});self.assertEqual(r.status_code,200)
        self.assertIsNone(customer.get(self.base+'/api/auth/me').json()['user'])

if __name__=='__main__':unittest.main()
