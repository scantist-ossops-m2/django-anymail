from __future__ import unicode_literals

import unittest

from django.test import SimpleTestCase
from django.test.utils import override_settings

from anymail.exceptions import AnymailAPIError
from anymail.message import AnymailMessage

from .utils import AnymailTestMixin, sample_image_path, RUN_LIVE_TESTS


@unittest.skipUnless(RUN_LIVE_TESTS, "RUN_LIVE_TESTS disabled in this environment")
@override_settings(ANYMAIL_POSTMARK_SERVER_TOKEN="POSTMARK_API_TEST",
                   EMAIL_BACKEND="anymail.backends.postmark.PostmarkBackend")
class PostmarkBackendIntegrationTests(SimpleTestCase, AnymailTestMixin):
    """Postmark API integration tests

    These tests run against the **live** Postmark API, but using a
    test key that's not capable of sending actual email.
    """

    def setUp(self):
        super(PostmarkBackendIntegrationTests, self).setUp()
        self.message = AnymailMessage('Anymail Postmark integration test', 'Text content',
                                      'from@example.com', ['to@example.com'])
        self.message.attach_alternative('<p>HTML content</p>', "text/html")

    def test_simple_send(self):
        # Example of getting the SendGrid send status and message id from the message
        sent_count = self.message.send()
        self.assertEqual(sent_count, 1)

        anymail_status = self.message.anymail_status
        sent_status = anymail_status.recipients['to@example.com'].status
        message_id = anymail_status.recipients['to@example.com'].message_id

        self.assertEqual(sent_status, 'sent')
        self.assertGreater(len(message_id), 0)  # non-empty string
        self.assertEqual(anymail_status.status, {sent_status})  # set of all recipient statuses
        self.assertEqual(anymail_status.message_id, message_id)

    def test_all_options(self):
        message = AnymailMessage(
            subject="Anymail all-options integration test",
            body="This is the text body",
            from_email="Test From <from@example.com>",
            to=["to1@example.com", "Recipient 2 <to2@example.com>"],
            cc=["cc1@example.com", "Copy 2 <cc2@example.com>"],
            bcc=["bcc1@example.com", "Blind Copy 2 <bcc2@example.com>"],
            reply_to=["reply1@example.com", "Reply 2 <reply2@example.com>"],
            headers={"X-Anymail-Test": "value"},

            # no metadata, send_at, track_clicks support
            tags=["tag 1"],  # max one tag
            track_opens=True,
        )
        message.attach("attachment1.txt", "Here is some\ntext for you", "text/plain")
        message.attach("attachment2.csv", "ID,Name\n1,Amy Lina", "text/csv")
        cid = message.attach_inline_image_file(sample_image_path())
        message.attach_alternative(
            "<p><b>HTML:</b> with <a href='http://example.com'>link</a>"
            "and image: <img src='cid:%s'></div>" % cid,
            "text/html")

        message.send()
        self.assertEqual(message.anymail_status.status, {'sent'})

    def test_invalid_from(self):
        self.message.from_email = 'webmaster@localhost'  # Django's default From
        with self.assertRaises(AnymailAPIError) as cm:
            self.message.send()
        err = cm.exception
        self.assertEqual(err.status_code, 422)
        self.assertIn("Invalid 'From' address", str(err))

    @override_settings(ANYMAIL_POSTMARK_SERVER_TOKEN="Hey, that's not a server token!")
    def test_invalid_server_token(self):
        with self.assertRaises(AnymailAPIError) as cm:
            self.message.send()
        err = cm.exception
        self.assertEqual(err.status_code, 401)
        # Make sure the exception message includes Postmark's response:
        self.assertIn("Please verify that you are using a valid token", str(err))
