import unittest
from unittest.mock import patch
import sys
import time
import types
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'firmware'))
time.ticks_ms = getattr(time, 'ticks_ms', lambda: 100)
time.ticks_diff = getattr(time, 'ticks_diff', lambda a, b: a-b)
import cloud
import http_client


class CloudTransportTests(unittest.TestCase):
    def test_uncertain_button_retry_keeps_the_identical_request(self):
        cloud._cached = {'enabled': True, 'device_token': 'isolated-test-only', 'api_base': 'https://example.test'}
        cloud._boot = {'bootId': 'test-boot-0000000001', 'bootCounter': 1}
        cloud._pending_press = None
        sent = []
        def request(method, path, body, **kwargs):
            sent.append(dict(body))
            cloud._last_status = 0 if len(sent) == 1 else 200
            return None if len(sent) == 1 else {'ok': True, 'replayed': True}
        with patch.object(cloud, '_request', request):
            self.assertFalse(cloud.press_button(8)['ok'])
            self.assertTrue(cloud.press_button(9)['ok'])
        self.assertEqual(sent[0], sent[1])
        self.assertEqual(sent[1]['revision'], 8)
        self.assertIsNone(cloud._pending_press)

    def test_boot_identity_is_persisted_before_use_and_increases(self):
        previous = os.getcwd()
        with tempfile.TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                cloud._boot = None
                first = cloud.identity()
                cloud._boot = None
                second = cloud.identity()
                self.assertEqual(second['bootCounter'], first['bootCounter']+1)
                self.assertNotEqual(second['bootId'], first['bootId'])
            finally:
                os.chdir(previous)

    def test_https_checks_ca_hostname_and_writes_the_complete_request(self):
        response = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\nB\r\n{"ok":true}\r\n0\r\n\r\n'
        written = bytearray()
        class Socket:
            def settimeout(self, timeout): pass
            def connect(self, address): pass
            def close(self): pass
        class Stream:
            def write(self, data):
                n = min(7, len(data)); written.extend(data[:n]); return n
            def read(self, length):
                nonlocal response
                data, response = response[:13], response[13:]
                return data
            def close(self): pass
        contexts = []
        class Context:
            def __init__(self, protocol): contexts.append(self)
            def load_verify_locations(self, cadata): self.ca = cadata
            def wrap_socket(self, sock, server_hostname): self.host = server_hostname; return Stream()
        sockets = types.SimpleNamespace(SOCK_STREAM=1, socket=Socket, getaddrinfo=lambda *args: [(None,None,None,None,('example.test',443))])
        ssl = types.SimpleNamespace(SSLContext=Context,PROTOCOL_TLS_CLIENT=16,CERT_REQUIRED=2)
        with patch.object(http_client,'socket',sockets),patch.object(http_client,'ssl',ssl):
            status, body = http_client.request_json('POST','https://example.test/api',{'action':'step'})
        self.assertEqual(status,200); self.assertTrue(body['ok'])
        self.assertEqual(contexts[0].verify_mode,2); self.assertEqual(contexts[0].host,'example.test')
        self.assertGreater(len(contexts[0].ca),1000)
        self.assertTrue(written.endswith(b'{"action": "step"}'))


if __name__ == '__main__':
    unittest.main()
