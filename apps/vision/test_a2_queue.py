"""Fast admission checks; no model, assets or HTTP sockets are loaded."""
import threading
import unittest
from unittest.mock import patch

from a2_server import serve_candidate


class Handler:
    def __init__(self):
        self.responses = []

    def respond(self, status, payload):
        self.responses.append((status, payload))


class QueueTest(unittest.TestCase):
    def test_waiting_request_runs_once_after_inference_releases(self):
        entered = threading.Event()
        release = threading.Event()

        class GateLock:
            def acquire(self, timeout):
                entered.set()
                return release.wait(timeout)

            def release(self):
                pass

        lock = GateLock()
        slots = threading.BoundedSemaphore(2)
        handler = Handler()
        calls = []
        worker = threading.Thread(target=serve_candidate,
                                  args=(handler, lambda h: calls.append(h), lock, slots))
        worker.start()
        self.assertTrue(entered.wait(timeout=1))
        self.assertEqual(calls, [])
        release.set()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(calls, [handler])
        self.assertEqual(handler.responses, [])

    def test_full_queue_fails_without_running_model(self):
        lock = threading.Lock()
        slots = threading.BoundedSemaphore(2)
        slots.acquire()
        slots.acquire()
        handler = Handler()
        serve_candidate(handler, lambda _: self.fail('model ran'), lock, slots)
        self.assertEqual(handler.responses[0][0], 503)
        slots.release()
        slots.release()

    def test_wait_timeout_releases_slot(self):
        lock = threading.Lock()
        slots = threading.BoundedSemaphore(2)
        handler = Handler()
        lock.acquire()
        try:
            with patch('a2_server.QUEUE_WAIT_SECONDS', 0):
                serve_candidate(handler, lambda _: self.fail('model ran'), lock, slots)
        finally:
            lock.release()
        self.assertEqual(handler.responses[0][0], 503)
        self.assertTrue(slots.acquire(blocking=False))
        slots.release()


if __name__ == '__main__':
    unittest.main()
