"""Optional Apple push transport. Credentials and packages stay local to the project."""
import os
from pathlib import Path
import threading
import time


def start_worker(store):
    import httpx
    import jwt
    key = Path(os.environ['APNS_KEY_PATH']).read_text()
    team = os.environ['APNS_TEAM_ID']
    key_id = os.environ['APNS_KEY_ID']
    topic = os.environ.get('APNS_TOPIC', 'app.circleguard.ios')

    def work():
        with httpx.Client(http2=True, timeout=15) as client:
            while True:
                try:
                    with store.transaction() as db:
                        events = [dict(e) for e in db.execute('''SELECT * FROM events e WHERE pushed=0 AND attempts<10 AND retry_at<?
                            AND created_at>? AND EXISTS(SELECT 1 FROM devices d WHERE d.user_id=e.recipient_id)
                            ORDER BY id LIMIT 50''', (time.time(), time.time()-86400))]
                    for event in events:
                        with store.transaction() as db:
                            devices = [dict(d) for d in db.execute('SELECT * FROM devices WHERE user_id=?', (event['recipient_id'],))]
                        if not devices:
                            continue
                        auth = jwt.encode({'iss': team, 'iat': int(time.time())}, key, algorithm='ES256', headers={'kid': key_id})
                        success = True
                        for device in devices:
                            host = 'api.sandbox.push.apple.com' if device['environment'] == 'sandbox' else 'api.push.apple.com'
                            response = client.post(f'https://{host}/3/device/{device["token"]}',
                                headers={'authorization': f'bearer {auth}', 'apns-topic': topic, 'apns-push-type': 'alert',
                                         'apns-priority': '10', 'apns-collapse-id': f'event-{event["id"]}',
                                         'apns-expiration': str(int(event['created_at'] + 86400))},
                                json={'aps': {'alert': {'title': event['title'], 'body': event['body']}, 'sound': 'default'}, 'eventId': event['id']})
                            if response.status_code == 410 or (response.status_code == 400 and response.json().get('reason') == 'BadDeviceToken'):
                                with store.transaction() as db:
                                    db.execute('DELETE FROM devices WHERE token=?', (device['token'],))
                            elif response.status_code != 200:
                                success = False
                                print(f'APNs event {event["id"]}: {response.status_code} {response.text}', flush=True)
                        with store.transaction() as db:
                            db.execute('UPDATE events SET pushed=?,attempts=attempts+1,retry_at=? WHERE id=?',
                                       (int(success), time.time()+min(300, 2**(event['attempts']+1)), event['id']))
                except Exception as error:
                    print(f'APNs retry: {error}', flush=True)
                time.sleep(3)
    threading.Thread(target=work, daemon=True).start()
