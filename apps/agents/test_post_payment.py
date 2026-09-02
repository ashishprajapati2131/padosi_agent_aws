from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.agents.services.post_payment import queue_invoice_and_welcome


class PostPaymentQueueTests(SimpleTestCase):
    def test_missing_ids_do_not_start_a_thread(self):
        with patch('apps.agents.services.post_payment.threading.Thread') as thread_cls:
            queue_invoice_and_welcome(None, 1)
            queue_invoice_and_welcome(1, None)
            thread_cls.assert_not_called()

    @patch('apps.agents.services.post_payment.transaction.get_connection')
    @patch('apps.agents.services.post_payment.threading.Thread')
    def test_queue_starts_daemon_worker(self, thread_cls, get_connection):
        get_connection.return_value.in_atomic_block = False
        worker = MagicMock()
        thread_cls.return_value = worker

        queue_invoice_and_welcome(12, 34)

        thread_cls.assert_called_once()
        kwargs = thread_cls.call_args.kwargs
        self.assertEqual(kwargs['args'], (12, 34))
        self.assertTrue(kwargs['daemon'])
        worker.start.assert_called_once()
