import json
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from app import make_server


class RelayIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server('127.0.0.1', 0, self.temp.name + '/test.sqlite3')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.alice = self.call('POST', '/users', {'name': 'Alice'})
        self.bob = self.call('POST', '/users', {'name': 'Bob'})
        self.eve = self.call('POST', '/users', {'name': 'Eve'})
        result = self.call('POST', '/groups', {'name': 'Home', 'latitude': 0, 'longitude': 0, 'radius': 500}, self.alice)
        self.group = result['groups'][0]
        self.call('POST', '/join', {'code': self.group['code']}, self.bob)
        self.clock = time.time()-30

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.store.db.close()
        self.temp.cleanup()

    def call(self, method, path, data=None, user=None):
        request = Request(self.base+path, data=json.dumps(data).encode() if data is not None else None,
                          method=method, headers={'Content-Type': 'application/json', 'Authorization': 'Bearer '+(user['token'] if user else '')})
        with urlopen(request, timeout=3) as response:
            return json.load(response)

    def locate(self, lon, user=None, **extra):
        self.clock += 1
        data = {'latitude': 0, 'longitude': lon, 'accuracy': 5, 'simulated': True,
                'observedAt': self.clock, 'requestId': str(self.clock), 'groupId': self.group['id']} | extra
        return self.call('POST', '/locations', data, user or self.alice)

    def events(self, user):
        return self.call('GET', '/events', user=user)['events']

    def test_real_http_exit_notifies_other_members_once_and_rearms(self):
        self.locate(0)
        self.assertEqual(self.locate(0.01)['exits'], 1)
        self.locate(0.012)
        self.assertEqual(len(self.events(self.bob)), 1)
        self.assertEqual(self.events(self.alice), [])
        self.assertEqual(self.events(self.eve), [])
        self.assertTrue(self.events(self.bob)[0]['title'].startswith('[TEST]'))
        self.locate(0)
        self.locate(0.01)
        events = self.events(self.bob)
        self.assertEqual(len(events), 2)
        self.assertEqual(self.call('GET', f'/events?after={events[-1]["id"]}', user=self.bob)['events'], [])

    def test_initial_outside_jitter_and_inaccurate_fixes_do_not_alert(self):
        self.locate(0.01)
        self.assertEqual(self.events(self.bob), [])
        self.locate(0)
        self.locate(0.00455)
        self.locate(0.005, accuracy=100)
        self.assertEqual(self.events(self.bob), [])

    def test_idempotency_and_out_of_order(self):
        self.locate(0)
        self.locate(0.01, requestId='unique-exit')
        self.assertTrue(self.locate(0.01, requestId='unique-exit')['duplicate'])
        self.locate(0, observedAt=self.clock-10)
        self.locate(0.01)
        self.assertEqual(len(self.events(self.bob)), 1)

    def test_switching_from_simulation_resets_baseline(self):
        self.locate(0)
        self.locate(0.01, simulated=False)
        self.assertEqual(self.events(self.bob), [])
        self.locate(0, simulated=False)
        self.locate(0.01, simulated=False)
        self.assertFalse(self.events(self.bob)[0]['simulated'])

    def test_auth_membership_and_owner_checks(self):
        with self.assertRaises(HTTPError) as error:
            self.call('GET', '/groups')
        self.assertEqual(error.exception.code, 401)
        with self.assertRaises(HTTPError) as error:
            self.locate(0, self.eve)
        self.assertEqual(error.exception.code, 403)
        with self.assertRaises(HTTPError) as error:
            self.call('PUT', '/groups/'+self.group['id'], {'latitude': 1, 'longitude': 1, 'radius': 500}, self.bob)
        self.assertEqual(error.exception.code, 403)

    def test_leave_stops_future_alerts(self):
        self.call('POST', '/groups/'+self.group['id']+'/leave', {}, self.bob)
        self.locate(0)
        self.locate(0.01)
        self.assertEqual(self.events(self.bob), [])

    def test_invalid_coordinates_and_nan_rejected(self):
        for lon in [181, float('nan'), '0']:
            with self.assertRaises(HTTPError) as error:
                self.locate(lon)
            self.assertEqual(error.exception.code, 400)

    def test_fence_edit_resets_baseline(self):
        self.locate(0)
        self.call('PUT', '/groups/'+self.group['id'], {'latitude': 1, 'longitude': 1, 'radius': 500}, self.alice)
        self.locate(0)
        self.assertEqual(self.events(self.bob), [])


if __name__ == '__main__':
    unittest.main()
