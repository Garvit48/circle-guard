#!/usr/bin/env python3
"""Create two real relay users and verify the same flow as the mobile simulation buttons."""
import argparse
import json
import time
import uuid
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8787')
args = parser.parse_args()

def call(path, body=None, token=''):
    req = Request(args.url+path, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'})
    with urlopen(req, timeout=10) as response:
        return json.load(response)

alice = call('/users', {'name': 'Demo Alice'})
bob = call('/users', {'name': 'Demo Bob'})
group = call('/groups', {'name': 'Apple Park walk', 'latitude': 37.3349, 'longitude': -122.009, 'radius': 500}, alice['token'])['groups'][0]
call('/join', {'code': group['code']}, bob['token'])
print(f"Join this group in the app: {group['code']}")
input('Press Enter after joining (or immediately for a two-user API test)… ')
for lon in [-122.009, -121.99, -121.99]:
    result = call('/locations', {'groupId': group['id'], 'latitude': 37.3349, 'longitude': lon, 'accuracy': 5,
                  'simulated': True, 'observedAt': time.time(), 'requestId': str(uuid.uuid4())}, alice['token'])
    print('Location accepted:', result)
events = call('/events', token=bob['token'])['events']
assert len(events) == 1 and events[0]['simulated'] == 1, events
print('PASS: Bob received exactly one exit alert:', events[0]['body'])
