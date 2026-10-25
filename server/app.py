#!/usr/bin/env python3
"""Local-first group relay. SQLite + standard-library HTTP; optional APNs worker."""
from contextlib import contextmanager
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlparse, parse_qs
import uuid


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def text(value, field, maximum=80):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ApiError(400, f'{field} must contain 1–{maximum} characters')
    return value.strip()


def number(value, field, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ApiError(400, f'{field} must be between {low} and {high}')
    return float(value)


def fence(data):
    return (number(data.get('latitude'), 'Latitude', -90, 90),
            number(data.get('longitude'), 'Longitude', -180, 180),
            number(data.get('radius'), 'Radius', 100, 10_000))


def distance(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6_371_000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS groups_(id TEXT PRIMARY KEY, name TEXT, code TEXT UNIQUE, owner_id TEXT,
                latitude REAL, longitude REAL, radius REAL, version INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS members(group_id TEXT, user_id TEXT, state TEXT DEFAULT 'unknown',
                mode TEXT DEFAULT '', updated_at REAL DEFAULT 0, distance REAL,
                PRIMARY KEY(group_id,user_id), FOREIGN KEY(group_id) REFERENCES groups_(id), FOREIGN KEY(user_id) REFERENCES users(id));
            CREATE TABLE IF NOT EXISTS reports(user_id TEXT, request_id TEXT, created_at REAL, PRIMARY KEY(user_id,request_id));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT, actor_id TEXT,
                recipient_id TEXT, title TEXT, body TEXT, simulated INTEGER, created_at REAL,
                pushed INTEGER DEFAULT 0, attempts INTEGER DEFAULT 0, retry_at REAL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS event_recipient ON events(recipient_id,id);
            CREATE TABLE IF NOT EXISTS devices(token TEXT PRIMARY KEY, user_id TEXT, environment TEXT);
        ''')

    @contextmanager
    def transaction(self):
        with self.lock, self.db:
            yield self.db

    def user(self, token):
        digest = hashlib.sha256(token.encode()).hexdigest()
        row = self.db.execute('SELECT * FROM users WHERE token_hash=?', (digest,)).fetchone()
        if not row:
            raise ApiError(401, 'Session missing or invalid. Create a new profile.')
        return row

    def snapshot(self, user_id):
        groups = []
        for row in self.db.execute('SELECT g.* FROM groups_ g JOIN members m ON g.id=m.group_id WHERE m.user_id=? ORDER BY g.rowid', (user_id,)):
            item = dict(row)
            item['members'] = [dict(m) for m in self.db.execute('''SELECT u.id,u.name,m.state,m.mode,m.updated_at,m.distance
                FROM members m JOIN users u ON u.id=m.user_id WHERE m.group_id=? ORDER BY u.name''', (row['id'],))]
            groups.append(item)
        return groups

    def handle(self, method, path, data, token='', query=None):
        query = query or {}
        with self.transaction() as db:
            if method == 'GET' and path == '/health':
                return {'status': 'ok', 'apns': bool(os.getenv('APNS_KEY_PATH'))}
            if method == 'POST' and path == '/users':
                name = text(data.get('name'), 'Name', 40)
                uid, secret = str(uuid.uuid4()), secrets.token_urlsafe(32)
                db.execute('INSERT INTO users VALUES(?,?,?)', (uid, name, hashlib.sha256(secret.encode()).hexdigest()))
                return {'id': uid, 'name': name, 'token': secret}
            user = self.user(token)
            uid = user['id']
            if method == 'GET' and path == '/groups':
                return {'groups': self.snapshot(uid)}
            if method == 'POST' and path == '/groups':
                name = text(data.get('name'), 'Group name')
                lat, lon, radius = fence(data)
                gid = str(uuid.uuid4())
                code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(10))
                db.execute('INSERT INTO groups_(id,name,code,owner_id,latitude,longitude,radius) VALUES(?,?,?,?,?,?,?)',
                           (gid, name, code, uid, lat, lon, radius))
                db.execute('INSERT INTO members(group_id,user_id) VALUES(?,?)', (gid, uid))
                return {'groups': self.snapshot(uid), 'groupId': gid}
            if method == 'POST' and path == '/join':
                code = text(data.get('code'), 'Invite code', 20).upper().replace(' ', '')
                group = db.execute('SELECT id FROM groups_ WHERE code=?', (code,)).fetchone()
                if not group:
                    raise ApiError(404, 'Invite code not found')
                count = db.execute('SELECT COUNT(*) FROM members WHERE group_id=?', (group['id'],)).fetchone()[0]
                if count >= 100:
                    raise ApiError(409, 'Group is full')
                db.execute('INSERT OR IGNORE INTO members(group_id,user_id) VALUES(?,?)', (group['id'], uid))
                return {'groups': self.snapshot(uid), 'groupId': group['id']}
            if path.startswith('/groups/'):
                parts = path.split('/')
                gid = parts[2]
                group = db.execute('SELECT * FROM groups_ WHERE id=?', (gid,)).fetchone()
                member = db.execute('SELECT 1 FROM members WHERE group_id=? AND user_id=?', (gid, uid)).fetchone()
                if not group or not member:
                    raise ApiError(404, 'Group not found')
                if method == 'POST' and path.endswith('/leave'):
                    db.execute('DELETE FROM members WHERE group_id=? AND user_id=?', (gid, uid))
                    successor = db.execute('SELECT user_id FROM members WHERE group_id=? LIMIT 1', (gid,)).fetchone()
                    if not successor:
                        db.execute('DELETE FROM groups_ WHERE id=?', (gid,))
                    elif group['owner_id'] == uid:
                        db.execute('UPDATE groups_ SET owner_id=? WHERE id=?', (successor['user_id'], gid))
                    return {'groups': self.snapshot(uid)}
                if method == 'PUT' and len(parts) == 3:
                    if group['owner_id'] != uid:
                        raise ApiError(403, 'Only the group owner can edit its fence')
                    lat, lon, radius = fence(data)
                    db.execute('UPDATE groups_ SET latitude=?,longitude=?,radius=?,version=version+1 WHERE id=?', (lat, lon, radius, gid))
                    db.execute("UPDATE members SET state='unknown',mode='',distance=NULL,updated_at=0 WHERE group_id=?", (gid,))
                    return {'groups': self.snapshot(uid)}
            if method == 'POST' and path == '/locations':
                lat = number(data.get('latitude'), 'Latitude', -90, 90)
                lon = number(data.get('longitude'), 'Longitude', -180, 180)
                accuracy = number(data.get('accuracy', 10), 'Accuracy', 0, 10_000)
                observed = number(data.get('observedAt'), 'Observation time', time.time()-86400, time.time()+60)
                request_id = text(data.get('requestId'), 'Request ID', 100)
                simulated = data.get('simulated', False)
                if not isinstance(simulated, bool):
                    raise ApiError(400, 'simulated must be a boolean')
                gid = data.get('groupId')
                if simulated and not gid:
                    raise ApiError(400, 'Simulation requires a groupId')
                if gid and not db.execute('SELECT 1 FROM members WHERE user_id=? AND group_id=?', (uid, gid)).fetchone():
                    raise ApiError(403, 'You are not a member of this group')
                inserted = db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?)', (uid, request_id, time.time())).rowcount
                if not inserted:
                    return {'duplicate': True, 'exits': 0}
                db.execute('DELETE FROM reports WHERE created_at<?', (time.time()-172800,))
                rows = db.execute('''SELECT g.*,m.state,m.mode,m.updated_at FROM groups_ g JOIN members m ON g.id=m.group_id
                                     WHERE m.user_id=?''', (uid,)).fetchall()
                exits = 0
                for group in rows:
                    if gid and gid != group['id']:
                        continue
                    if observed <= group['updated_at']:
                        continue
                    mode = 'simulation' if simulated else 'gps'
                    previous = group['state'] if group['mode'] == mode else 'unknown'
                    dist = distance(lat, lon, group['latitude'], group['longitude'])
                    margin = max(15, accuracy)
                    state = 'outside' if dist > group['radius']+margin else 'inside' if dist < max(0, group['radius']-margin) else previous
                    db.execute('UPDATE members SET state=?,mode=?,updated_at=?,distance=? WHERE group_id=? AND user_id=?',
                               (state, mode, observed, dist, group['id'], uid))
                    if previous == 'inside' and state == 'outside':
                        exits += 1
                        title = ('[TEST] ' if simulated else '') + 'Geofence exit'
                        body = f"{user['name']} left {group['name']}’s safe area."
                        for member in db.execute('SELECT user_id FROM members WHERE group_id=? AND user_id!=?', (group['id'], uid)):
                            db.execute('INSERT INTO events(group_id,actor_id,recipient_id,title,body,simulated,created_at) VALUES(?,?,?,?,?,?,?)',
                                       (group['id'], uid, member['user_id'], title, body, simulated, time.time()))
                return {'duplicate': False, 'exits': exits}
            if method == 'GET' and path == '/events':
                try:
                    after = max(0, int(query.get('after', ['0'])[0]))
                except (ValueError, TypeError):
                    raise ApiError(400, 'Invalid event cursor')
                events = [dict(e) for e in db.execute('''SELECT id,group_id,actor_id,title,body,simulated,created_at
                    FROM events WHERE recipient_id=? AND id>? ORDER BY id LIMIT 100''', (uid, after))]
                return {'events': events, 'cursor': events[-1]['id'] if events else after}
            if method == 'POST' and path == '/devices':
                device = text(data.get('token'), 'Device token', 256)
                if any(c not in '0123456789abcdef' for c in device.lower()) or len(device) < 32:
                    raise ApiError(400, 'Invalid APNs device token')
                environment = data.get('environment', 'sandbox')
                if environment not in ('sandbox', 'production'):
                    raise ApiError(400, 'Invalid APNs environment')
                db.execute('INSERT INTO devices VALUES(?,?,?) ON CONFLICT(token) DO UPDATE SET user_id=excluded.user_id,environment=excluded.environment', (device, uid, environment))
                return {'ok': True}
            raise ApiError(404, 'Endpoint not found')


class Handler(BaseHTTPRequestHandler):
    server_version = 'CircleGuard/1.0'

    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch()
    def do_PUT(self): self.dispatch()

    def dispatch(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 32_768:
                raise ApiError(413, 'Request too large')
            data = json.loads(self.rfile.read(length)) if length else {}
            if not isinstance(data, dict):
                raise ApiError(400, 'JSON object required')
            url = urlparse(self.path)
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            result = self.server.store.handle(self.command, url.path.rstrip('/') or '/', data, token, parse_qs(url.query))
            self.respond(200, result)
        except ApiError as e:
            self.respond(e.status, {'error': e.message})
        except (ValueError, UnicodeDecodeError):
            self.respond(400, {'error': 'Invalid JSON or request length'})
        except Exception:
            import traceback
            traceback.print_exc()
            self.respond(500, {'error': 'Internal server error'})

    def respond(self, status, value):
        payload = json.dumps(value, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)


def make_server(host, port, db_path):
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.store = Store(db_path)
    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--db', default=str(Path(__file__).resolve().parents[1] / '.data/circleguard.sqlite3'))
    args = parser.parse_args()
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    server = make_server(args.host, args.port, args.db)
    if os.getenv('APNS_KEY_PATH'):
        from apns import start_worker
        start_worker(server.store)
    print(f'CircleGuard relay: http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == '__main__':
    main()
