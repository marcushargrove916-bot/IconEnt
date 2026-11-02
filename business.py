"""One Hit Wonder business MVP: accounts, sessions, credits, checkout, and admin.

No card information is processed or stored here. All payments use Stripe Checkout
and credit grants rely exclusively on verified Stripe webhooks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from urllib import parse, request, error

DATABASE = Path(os.environ.get('BUSINESS_DB_PATH', str(Path(__file__).resolve().parent / 'data' / 'business.sqlite3')))
DATABASE.parent.mkdir(parents=True, exist_ok=True)
OWNER_EMAIL = os.environ.get('OWNER_EMAIL', '').strip().lower()
OWNER_INVITE_CODE = os.environ.get('OWNER_INVITE_CODE', '')
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '').strip()
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '').strip()
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
SESSION_COOKIE = 'ohw_session'
SESSION_LIFETIME = 30 * 86400
MAX_SESSIONS_PER_ACCOUNT = 10
LOCK = threading.RLock()
FAILED_ATTEMPTS = {}

CREDIT_PACKS = {
    'starter': {'name':'Starter Pack','type':'payment','price':999,'credits':10,'env':'STRIPE_PRICE_STARTER'},
    'creator': {'name':'Creator Pack','type':'payment','price':2499,'credits':30,'env':'STRIPE_PRICE_CREATOR'},
    'director': {'name':'Director Pack','type':'payment','price':4999,'credits':70,'env':'STRIPE_PRICE_DIRECTOR'},
    'studio_pack': {'name':'Studio Pack','type':'payment','price':9999,'credits':160,'env':'STRIPE_PRICE_STUDIO_PACK'},
    'basic': {'name':'Basic','type':'subscription','price':1499,'credits':15,'env':'STRIPE_PRICE_BASIC'},
    'pro': {'name':'Pro','type':'subscription','price':3999,'credits':50,'env':'STRIPE_PRICE_PRO'},
    'studio': {'name':'Studio','type':'subscription','price':9999,'credits':150,'env':'STRIPE_PRICE_STUDIO'},
}


def connect():
    conn = sqlite3.connect(DATABASE, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=15000')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def initialize():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
          password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role in ('owner','customer')),
          credits INTEGER NOT NULL DEFAULT 0 CHECK(credits >= 0),
          plan TEXT NOT NULL DEFAULT 'free', disabled INTEGER NOT NULL DEFAULT 0,
          stripe_customer_id TEXT, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS sessions (
          digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ledger (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          amount INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS purchases (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
          sku TEXT NOT NULL, cents INTEGER NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS webhook_events (
          id TEXT PRIMARY KEY, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
          id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT NOT NULL,
          action TEXT NOT NULL, target_id TEXT, created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS ledger_user ON ledger(user_id);
        ''')


def now(): return int(time.time())


def password_hash(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 270_000)
    return 'pbkdf2_sha256$270000$'+salt.hex()+'$'+derived.hex()


def password_ok(password, stored):
    try:
        _, iterations, salt, stored_digest = stored.split('$')
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest, bytes.fromhex(stored_digest))
    except (ValueError, TypeError):
        return False


def public_user(user):
    return {'id':user['id'],'email':user['email'],'name':user['name'], 'role':user['role'],
            'credits':user['credits'],'plan':user['plan'],'disabled':bool(user['disabled'])}


def create_user(email, name, password, owner_code=''):
    email = str(email or '').strip().lower()
    name = str(name or '').strip()
    password = str(password or '')
    if not re.fullmatch(r'[^\s@]{1,96}@[^\s@]{1,150}\.[A-Za-z]{2,}', email):
        raise ValueError('Enter a valid email address')
    if not 2 <= len(name) <= 70:
        raise ValueError('Enter a name between 2 and 70 characters')
    if not 12 <= len(password) <= 128:
        raise ValueError('Password must contain at least 12 characters')
    role = 'customer'
    if owner_code:
        if not (OWNER_EMAIL and len(OWNER_INVITE_CODE) >= 20 and email == OWNER_EMAIL and secrets.compare_digest(owner_code, OWNER_INVITE_CODE)):
            raise ValueError('Owner invitation is not valid for this email')
        role = 'owner'
    elif os.environ.get('SIGNUPS_ENABLED', '1') != '1':
        raise ValueError('New customer signups are not open yet')
    uid = secrets.token_hex(16)
    try:
        with connect() as db:
            if role == 'owner' and db.execute("SELECT 1 FROM users WHERE role='owner'").fetchone():
                raise ValueError('Owner account already exists')
            db.execute('INSERT INTO users(id,email,name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                       (uid,email,name,password_hash(password),role,now()))
            user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        return public_user(user)
    except sqlite3.IntegrityError:
        raise ValueError('This email already has an account')


def login(email,password):
    email=str(email or '').strip().lower()
    key=hashlib.sha256(email.encode()).hexdigest()
    when, attempts = FAILED_ATTEMPTS.get(key,(0,0))
    if now()-when > 600: attempts=0
    if attempts>=8:
        raise ValueError('Too many login attempts. Try again later.')
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
    if not user or not password_ok(str(password or ''),user['password_hash']) or user['disabled']:
        FAILED_ATTEMPTS[key]=(now(), attempts+1)
        raise ValueError('Invalid email or password')
    FAILED_ATTEMPTS.pop(key,None)
    raw=secrets.token_urlsafe(42)
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE expires_at<?',(now(),))
        # Limit persistent sessions, remove oldest first.
        old=db.execute('SELECT digest FROM sessions WHERE user_id=? ORDER BY created_at DESC',(user['id'],)).fetchall()
        for record in old[MAX_SESSIONS_PER_ACCOUNT-1:]:
            db.execute('DELETE FROM sessions WHERE digest=?',(record['digest'],))
        db.execute('INSERT INTO sessions(digest,user_id,expires_at,created_at) VALUES(?,?,?,?)',
                   (hashlib.sha256(raw.encode()).hexdigest(),user['id'],now()+SESSION_LIFETIME,now()))
    return raw,public_user(user)


def cookie(raw, *, clear=False):
    secure = os.environ.get('COOKIE_SECURE', '1') == '1'
    flags = '; Path=/; HttpOnly; SameSite=Lax' + ('; Secure' if secure else '')
    if clear: return f'{SESSION_COOKIE}=; Max-Age=0'+flags
    return f'{SESSION_COOKIE}={raw}; Max-Age={SESSION_LIFETIME}'+flags


def from_cookie(cookie_header):
    match=re.search(r'(?:^|;\s*)'+SESSION_COOKIE+r'=([^;]+)',cookie_header or '')
    if not match:return None
    digest=hashlib.sha256(match.group(1).encode()).hexdigest()
    with connect() as db:
        row=db.execute('''SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                           WHERE s.digest=? AND s.expires_at>? AND u.disabled=0''',(digest,now())).fetchone()
    return public_user(row) if row else None


def logout(cookie_header):
    match=re.search(r'(?:^|;\s*)'+SESSION_COOKIE+r'=([^;]+)',cookie_header or '')
    if match:
        with connect() as db: db.execute('DELETE FROM sessions WHERE digest=?',(hashlib.sha256(match.group(1).encode()).hexdigest(),))


def credit_quote(kind, quality, seconds, photos, scene_count=1):
    if kind=='clip':return 2 + int(photos>0) + int(quality=='1080p') + (3 if quality=='4k' else 0) + int(seconds>=9)
    base={3:8,5:12,8:18}.get(scene_count)
    if base is None: raise ValueError('Select 3, 5 or 8 scenes')
    return base + (2 if quality=='1080p' else 0) + (2 if seconds>=9 else 0) + int(photos>0)


def reserve_credits(uid, job_id, amount, is_owner):
    if is_owner:return 0
    with LOCK, connect() as db:
        updated=db.execute('UPDATE users SET credits=credits-? WHERE id=? AND credits>=? AND disabled=0',(amount,uid,amount))
        if updated.rowcount!=1:raise ValueError(f'Not enough credits. This render requires {amount} credits.')
        db.execute('INSERT INTO ledger(id,user_id,amount,reason,created_at) VALUES(?,?,?,?,?)',
                   ('render:'+job_id,uid,-amount,'AI video generation',now()))
        return amount


def refund_render(uid, job_id, amount):
    if not amount:return
    with LOCK,connect() as db:
        try:
            db.execute('INSERT INTO ledger(id,user_id,amount,reason,created_at) VALUES(?,?,?,?,?)',
                       ('refund:'+job_id,uid,amount,'Failed generation refund',now()))
        except sqlite3.IntegrityError:
            return
        db.execute('UPDATE users SET credits=credits+? WHERE id=?',(amount,uid))


def grant_credits(actor_id, target_id, amount):
    if not isinstance(amount,int) or not 1<=amount<=1000:raise ValueError('Grant between 1 and 1,000 credits')
    with connect() as db:
        if not db.execute('SELECT 1 FROM users WHERE id=?',(target_id,)).fetchone():raise ValueError('User not found')
        db.execute('UPDATE users SET credits=credits+? WHERE id=?',(amount,target_id))
        db.execute('INSERT INTO ledger(id,user_id,amount,reason,created_at) VALUES(?,?,?,?,?)',
                   ('admin:'+secrets.token_hex(12),target_id,amount,'Owner bonus credits',now()))
        db.execute('INSERT INTO audit_log(actor_id,action,target_id,created_at) VALUES(?,?,?,?)',
                   (actor_id,'grant:'+str(amount),target_id,now()))


def admin_users():
    with connect() as db:
        rows=db.execute('SELECT id,email,name,role,credits,plan,disabled,created_at FROM users ORDER BY created_at DESC LIMIT 250').fetchall()
    return [dict(r) for r in rows]


def admin_stats(jobs):
    with connect() as db:
        users=db.execute('SELECT count(*) AS n FROM users').fetchone()['n']
        customers=db.execute("SELECT count(*) AS n FROM users WHERE role='customer'").fetchone()['n']
        revenue=db.execute('SELECT coalesce(sum(cents),0) AS n FROM purchases').fetchone()['n']
    return {'users':users,'customers':customers,'revenue_cents':revenue,
            'generations':len(jobs),'completed':sum(x.get('status')=='completed' for x in jobs),
            'estimated_provider_usd':round(sum(x.get('cost_estimate',0) for x in jobs),2)}


def prices():
    return {'configured':bool(os.environ.get('CHECKOUT_ENABLED')=='1' and STRIPE_SECRET_KEY and PUBLIC_BASE_URL),
            'packs':[{'sku':k,'name':v['name'],'kind':v['type'],'cents':v['price'],
                      'credits':v['credits'],'available':bool(os.environ.get('CHECKOUT_ENABLED')=='1' and STRIPE_SECRET_KEY and PUBLIC_BASE_URL and os.getenv(v['env']))}
                     for k,v in CREDIT_PACKS.items()]}


def stripe_call(method, endpoint, form=None):
    if not STRIPE_SECRET_KEY:raise ValueError('Payments are not configured yet')
    body=parse.urlencode(form).encode() if form is not None else None
    req=request.Request('https://api.stripe.com/v1/'+endpoint.lstrip('/'),data=body,method=method,
                        headers={'Authorization':'Bearer '+STRIPE_SECRET_KEY,'Content-Type':'application/x-www-form-urlencoded'})
    try:
        with request.urlopen(req,timeout=30) as resp:return json.load(resp)
    except error.HTTPError as ex:
        # Do not expose Stripe API secrets or full HTTP request metadata in the error message.
        raise ValueError('Payment provider rejected the request. Check Stripe configuration.') from ex


def checkout(uid,sku):
    v=CREDIT_PACKS.get(sku)
    if not v:raise ValueError('Choose a valid plan')
    priceid=os.getenv(v['env'])
    if os.environ.get('CHECKOUT_ENABLED') != '1' or not STRIPE_SECRET_KEY or not priceid or not PUBLIC_BASE_URL.startswith('https://'):
        raise ValueError('Live checkout is not connected yet. The owner must configure Stripe keys and prices.')
    with connect() as db:
        user=db.execute('SELECT email,stripe_customer_id FROM users WHERE id=?',(uid,)).fetchone()
    if not user:raise ValueError('Sign in again to continue')
    form={
       'mode':v['type'],'line_items[0][price]':priceid,'line_items[0][quantity]':'1',
       'client_reference_id':uid,
       'success_url':PUBLIC_BASE_URL+'/dashboard?payment=success',
       'cancel_url':PUBLIC_BASE_URL+'/pricing?payment=canceled',
       'metadata[user_id]':uid, 'metadata[sku]':sku,
       'allow_promotion_codes':'true',
    }
    if user['stripe_customer_id']:form['customer']=user['stripe_customer_id']
    else:form['customer_email']=user['email']
    if v['type']=='subscription':
        form['subscription_data[metadata][user_id]']=uid
        form['subscription_data[metadata][sku]']=sku
    session=stripe_call('POST','checkout/sessions',form)
    url=session.get('url') or ''
    if not url.startswith('https://checkout.stripe.com/') and not url.startswith('https://billing.stripe.com/'):
        raise ValueError('Payment provider did not return a valid checkout URL')
    return url


def verify_stripe_signature(payload,signature):
    if not STRIPE_WEBHOOK_SECRET:raise ValueError('Stripe webhook secret is not configured')
    parts=dict(x.split('=',1) for x in signature.split(',') if '=' in x)
    stamp=int(parts.get('t','0'))
    if abs(now()-stamp)>300:raise ValueError('Webhook timestamp is invalid')
    candidate=hmac.new(STRIPE_WEBHOOK_SECRET.encode(),str(stamp).encode()+b'.'+payload,hashlib.sha256).hexdigest()
    signatures=[v.split('=',1)[1] for v in signature.split(',') if v.startswith('v1=')]
    if not any(hmac.compare_digest(candidate,s) for s in signatures):raise ValueError('Webhook signature invalid')


def handle_webhook(payload,signature):
    verify_stripe_signature(payload,signature)
    event=json.loads(payload)
    eid=event.get('id','')
    obj=event.get('data',{}).get('object',{})
    if not eid or not isinstance(obj,dict):raise ValueError('Invalid Stripe event')
    typ=event.get('type')
    with LOCK,connect() as db:
        if db.execute('SELECT 1 FROM webhook_events WHERE id=?',(eid,)).fetchone():return {'ok':True,'duplicate':True}
        if typ=='checkout.session.completed':
            uid=obj.get('metadata',{}).get('user_id') or obj.get('client_reference_id')
            sku=obj.get('metadata',{}).get('sku')
            plan=CREDIT_PACKS.get(sku)
            if uid and plan and db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():
                customer=obj.get('customer')
                if customer:db.execute('UPDATE users SET stripe_customer_id=? WHERE id=?',(customer,uid))
                if plan['type']=='payment' and obj.get('payment_status')=='paid':
                    purchase_id='session:'+str(obj.get('id'))
                    if not db.execute('SELECT 1 FROM purchases WHERE id=?',(purchase_id,)).fetchone():
                        db.execute('INSERT INTO purchases(id,user_id,sku,cents,created_at) VALUES(?,?,?,?,?)',
                                   (purchase_id,uid,sku,int(obj.get('amount_total') or plan['price']),now()))
                        db.execute('UPDATE users SET credits=credits+? WHERE id=?',(plan['credits'],uid))
                        db.execute('INSERT INTO ledger(id,user_id,amount,reason,created_at) VALUES(?,?,?,?,?)',
                                   (purchase_id,uid,plan['credits'],'Credit pack purchase',now()))
                if plan['type']=='subscription':
                    db.execute('UPDATE users SET plan=? WHERE id=?',(sku,uid))
        elif typ=='invoice.paid':
            meta=(obj.get('subscription_details') or {}).get('metadata') or (obj.get('parent') or {}).get('subscription_details',{}).get('metadata') or {}
            uid=meta.get('user_id');sku=meta.get('sku')
            if (not uid or not sku) and obj.get('subscription'):
                # Recover subscription metadata if the invoice doesn't embed it.
                sub=stripe_call('GET','subscriptions/'+parse.quote(str(obj['subscription']),safe=''))
                uid=uid or sub.get('metadata',{}).get('user_id')
                sku=sku or sub.get('metadata',{}).get('sku')
            plan=CREDIT_PACKS.get(sku)
            if uid and plan and plan['type']=='subscription' and db.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone():
                pid='invoice:'+str(obj.get('id'))
                if not db.execute('SELECT 1 FROM purchases WHERE id=?',(pid,)).fetchone():
                    db.execute('INSERT INTO purchases(id,user_id,sku,cents,created_at) VALUES(?,?,?,?,?)',
                               (pid,uid,sku,int(obj.get('amount_paid') or 0),now()))
                    db.execute('UPDATE users SET credits=credits+?,plan=? WHERE id=?',(plan['credits'],sku,uid))
                    db.execute('INSERT INTO ledger(id,user_id,amount,reason,created_at) VALUES(?,?,?,?,?)',
                               (pid,uid,plan['credits'],'Monthly subscription credits',now()))
        db.execute('INSERT INTO webhook_events(id,created_at) VALUES(?,?)',(eid,now()))
    return {'ok':True}


initialize()
