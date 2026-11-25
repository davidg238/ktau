"""Tests for act.py: run with `python3 -m unittest server/test_act.py` from the repo root."""
import http.server, json, os, sys, tempfile, threading, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import act  # noqa: E402


class Stub:
    """A one-shot OpenAI-style server on localhost; `hang` never answers."""
    def __init__(self, content='{"action":"none","text":"ok"}', hang=False):
        stub = self
        self.request = None

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                stub.path = self.path
                stub.request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if hang:
                    time.sleep(3)
                    return
                body = json.dumps({'choices': [{'message': {'content': content}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.server.daemon_threads = True
        self.url = 'http://127.0.0.1:%d' % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class ActTest(unittest.TestCase):
    def test_parse_ok(self):
        self.assertEqual(act.parse('{"action":"note","text":"buy milk"}'), ('note', 'buy milk'))

    def test_parse_rejects(self):
        for answer in ['Sure, I will note that.', '{"action":"shell","text":"rm"}', '{"text":"x"}',
                       '{"action":"say"}', '["say","x"]', '']:
            with self.subTest(answer=answer):
                with self.assertRaises(ValueError):
                    act.parse(answer)

    def test_note_appends(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sub', 'notes.txt')
            act.run('note', 'buy milk', path)
            act.run('note', 'call Bob', path)
            lines = open(path).read().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d buy milk$')
        self.assertTrue(lines[1].endswith(' call Bob'))

    def test_say_and_none_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'notes.txt')
            act.run('say', 'hi', path)
            act.run('none', 'it is noon', path)
            self.assertFalse(os.path.exists(path))

    def test_ask_body(self):
        stub = Stub('{"action":"note","text":"milk"}')
        try:
            answer = act.ask('remind me to buy milk', stub.url)
        finally:
            stub.close()
        self.assertEqual(answer, '{"action":"note","text":"milk"}')
        self.assertEqual(stub.path, '/v1/chat/completions')
        r = stub.request
        self.assertEqual(r['messages'][0], {'role': 'system', 'content': act.SYSTEM_PROMPT})
        self.assertEqual(r['messages'][1], {'role': 'user', 'content': 'remind me to buy milk'})
        self.assertEqual(r['chat_template_kwargs'], {'enable_thinking': False})
        self.assertEqual(r['response_format'], {'type': 'json_object'})
        self.assertEqual(r['temperature'], 0)

    def test_ask_timeout(self):
        stub = Stub(hang=True)
        start = time.monotonic()
        try:
            with self.assertRaises(OSError):
                act.ask('hello', stub.url, timeout_s=1)
        finally:
            stub.close()
        self.assertLess(time.monotonic() - start, 2.5)


if __name__ == '__main__':
    unittest.main()
