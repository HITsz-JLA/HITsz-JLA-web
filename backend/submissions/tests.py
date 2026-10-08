import io
import json
import uuid
import zipfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission, User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .mailer import send_notifications
from .models import ModerationLog, Notification, Submission
from .services import moderate


class LocalAudioPreviewTests(TestCase):
    def test_byte_ranges_support_metadata_and_seeking(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from django.test import RequestFactory
        from config.local_preview import serve_file

        factory = RequestFactory()
        audio = b'0123456789'
        with TemporaryDirectory() as directory:
            Path(directory, 'audio.mp3').write_bytes(audio)
            for value, expected in [('bytes=0-3', b'0123'), ('bytes=7-', b'789'),
                                    ('bytes=-3', b'789'), ('bytes=8-99', b'89')]:
                with self.subTest(range=value):
                    response = serve_file(directory, 'audio.mp3', factory.get('/', HTTP_RANGE=value))
                    try:
                        self.assertEqual(response.status_code, 206)
                        self.assertEqual(b''.join(response.streaming_content), expected)
                        self.assertEqual(int(response['Content-Length']), len(expected))
                        self.assertEqual(response['Accept-Ranges'], 'bytes')
                    finally:
                        response.close()
            for value in ['bytes=10-', 'bytes=5-3', 'bytes=-0']:
                response = serve_file(directory, 'audio.mp3', factory.get('/', HTTP_RANGE=value))
                self.assertEqual(response.status_code, 416)
                self.assertEqual(response['Content-Range'], 'bytes */10')
            # Malformed/multipart ranges are ignored; the full file remains available.
            for value in ['', 'bytes=abc', 'bytes=0-1,3-4']:
                response = serve_file(directory, 'audio.mp3', factory.get('/', HTTP_RANGE=value))
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(b''.join(response.streaming_content), audio)
                finally:
                    response.close()


@override_settings(FORM_MIN_SECONDS=0)
class CommunityTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.tokens = self.client.get('/community/api/csrf/').json()
        self.actor = User.objects.create_user('reviewer', is_staff=True)
        self.actor.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='submissions', codename__in=[
                'moderate_submission', 'change_submission', 'view_submission']))

    def payload(self, **extra):
        return dict(request_id=str(uuid.uuid4()), form_token=self.tokens['form_token'],
                    category='activity', nickname='', body='希望举办日语歌曲交流活动。', consent=True, **extra)

    def submit(self, data=None, kind='feedback'):
        return self.client.post(f'/community/api/submissions/{kind}/',
                                json.dumps(data or self.payload()), content_type='application/json',
                                HTTP_X_CSRFTOKEN=self.tokens['csrf_token'])

    def test_pending_is_private_and_approval_and_hiding_are_immediate(self):
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        item = Submission.objects.get(pk=response.json()['reference'])
        self.assertEqual(item.status, 'pending')
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(self.client.get('/community/api/feedback/').json()['total'], 0)
        moderate(item, self.actor, 'approved', '感谢建议！', '管理员私密记录')
        public = self.client.get('/community/api/feedback/')
        self.assertEqual(public.json()['total'], 1)
        self.assertEqual(public.json()['items'][0]['reply'], '感谢建议！')
        self.assertNotContains(public, '管理员私密记录')
        self.assertNotContains(public, 'request_id')
        moderate(item, self.actor, 'hidden')
        self.assertEqual(self.client.get('/community/api/feedback/').json()['total'], 0)
        self.assertEqual(ModerationLog.objects.count(), 2)

    def test_retry_does_not_duplicate_submission_or_mail(self):
        data = self.payload()
        first = self.submit(data)
        second = self.submit(data)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()['reference'], second.json()['reference'])
        data['body'] = '用相同编号提交不同内容。'
        self.assertEqual(self.submit(data).status_code, 409)
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_csrf_and_origin_are_enforced(self):
        self.assertEqual(self.client.post('/community/api/submissions/feedback/',
            json.dumps(self.payload()), content_type='application/json').status_code, 403)
        self.assertEqual(self.client.post('/community/api/submissions/feedback/',
            json.dumps(self.payload()), content_type='application/json',
            HTTP_X_CSRFTOKEN=self.tokens['csrf_token'], HTTP_ORIGIN='https://evil.example').status_code, 403)
        self.assertEqual(Submission.objects.count(), 0)

    def test_rate_limit_and_retry_after(self):
        with override_settings(SUBMISSION_RATE_LIMIT=2):
            data = self.payload()
            self.assertEqual(self.submit(data).status_code, 201)
            self.assertEqual(self.submit(data).status_code, 200)
            self.assertEqual(self.submit().status_code, 201)
            response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '600')

    def test_cannot_set_own_approval_or_internal_note(self):
        self.submit(self.payload(status='approved', internal_note='forged', selected=True))
        item = Submission.objects.get()
        self.assertEqual(item.status, 'pending')
        self.assertFalse(item.selected)
        self.assertEqual(item.internal_note, '')

    def test_invalid_inputs_and_honeypot(self):
        for key, value in [('body', '短'), ('body', '字' * 2001), ('consent', False),
                           ('website', 'spam'), ('form_token', 'bad'), ('category', 'fake')]:
            data = self.payload()
            data[key] = value
            self.assertEqual(self.submit(data).status_code, 400, key)
        with override_settings(FORM_MIN_SECONDS=60):
            self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(Submission.objects.count(), 0)

    def test_song_urls_validated_and_approved_songs_still_private(self):
        for url in ['javascript:alert(1)', 'http://example.com/song', 'https://user:pass@example.com/song']:
            data = self.payload(song_title='歌名', artist='歌手', music_url=url)
            self.assertEqual(self.submit(data, 'song').status_code, 400)
        response = self.submit(self.payload(song_title='歌名', artist='歌手',
                                           music_url='https://example.com/song'), 'song')
        self.assertEqual(response.status_code, 201)
        moderate(Submission.objects.get(), self.actor, 'approved', selected=True)
        self.assertEqual(self.client.get('/community/api/feedback/').json()['total'], 0)

    def test_unprivileged_user_cannot_moderate(self):
        self.submit()
        user = User.objects.create_user('ordinary')
        with self.assertRaises(PermissionError):
            moderate(Submission.objects.get(), user, 'approved')
        self.assertEqual(Submission.objects.get().status, 'pending')
        self.assertEqual(self.client.get('/community/admin/').status_code, 302)

    def test_feedback_without_category_can_be_submitted_and_approved(self):
        data = self.payload()
        data.pop('category')
        self.assertEqual(self.submit(data).status_code, 201)
        item = Submission.objects.get()
        self.assertEqual(item.category, '')
        self.assertEqual(item.status, 'pending')
        moderate(item, self.actor, 'approved')
        self.assertEqual(self.client.get('/community/api/feedback/').json()['items'][0]['category'], '')

    def test_song_optional_fields_accept_blank_omitted_and_short_reason(self):
        for mode in ('blank', 'omitted', 'short'):
            data = self.payload(song_title='歌名', artist='歌手')
            data.pop('body')
            if mode != 'omitted':
                data.update(body='助词' if mode == 'short' else '', music_url='')
            response = self.submit(data, 'song')
            self.assertEqual(response.status_code, 201, response.content)
            item = Submission.objects.get(pk=response.json()['reference'])
            self.assertEqual(item.body, '助词' if mode == 'short' else '')
            self.assertEqual(item.music_url, '')
            self.assertEqual(item.status, 'pending')
            self.assertTrue(Notification.objects.filter(submission=item).exists())

    def test_admin_edits_only_review_fields_and_escapes_content(self):
        data = self.payload()
        data['body'] = '<script>alert("unsafe")</script>'
        self.submit(data)
        item = Submission.objects.get()
        admin_client = Client()
        admin_client.force_login(self.actor)
        url = f'/community/admin/submissions/submission/{item.pk}/change/'
        page = admin_client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, '<script>alert("unsafe")</script>')
        self.assertContains(page, '&lt;script&gt;')
        saved = admin_client.post(url, dict(status='approved', public_reply='收到建议',
                                            internal_note='仅管理员可见', body='恶意篡改原文', _save='保存'))
        self.assertEqual(saved.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.body, data['body'])
        self.assertEqual(item.status, 'approved')
        self.assertEqual(item.reviewed_by, self.actor)
        self.assertEqual(ModerationLog.objects.count(), 1)

    def test_export_is_draft_and_escapes_untrusted_markdown(self):
        data = self.payload(song_title='歌名', artist='歌手', music_url='https://example.com/song')
        data['body'] = '<script>alert(1)</script> [click](javascript:alert(1))'
        self.submit(data, 'song')
        item = moderate(Submission.objects.get(), self.actor, 'approved')
        admin_client = Client()
        admin_client.force_login(self.actor)
        response = admin_client.post('/community/admin/submissions/submission/',
            {'action': 'export_songs', '_selected_action': str(item.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            draft = archive.read(archive.namelist()[0]).decode()
        self.assertIn('draft: true', draft)
        self.assertNotIn('<script>', draft)
        self.assertNotIn('[click](javascript:', draft)


@override_settings(NOTIFY_TO=['admin@example.com'], NOTIFY_CC=['cc@example.com'],
                   DEFAULT_FROM_EMAIL='sender@example.com', EMAIL_MODE='test')
class NotificationTests(TestCase):
    def setUp(self):
        self.item = Submission.objects.create(request_id=uuid.uuid4(), payload_hash='hash',
                                              kind='feedback', body='希望开展更多社团活动。')
        self.notification = Notification.objects.create(submission=self.item, next_attempt_at=timezone.now())

    def test_delivery_has_cc_and_login_link_and_is_not_resent(self):
        self.assertEqual(send_notifications(), (1, 0))
        self.assertEqual(send_notifications(), (0, 0))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].cc, ['cc@example.com'])
        self.assertIn(f'/community/admin/submissions/submission/{self.item.pk}/change/', mail.outbox[0].body)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, 'sent')

    def test_failure_preserves_submission_and_retries_without_secret_logging(self):
        with patch('submissions.mailer.EmailMessage.send', side_effect=OSError('secret must not be saved')):
            self.assertEqual(send_notifications(), (0, 1))
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, 'pending')
        self.assertEqual(self.notification.last_error, 'OSError')
        self.assertEqual(Submission.objects.count(), 1)
        self.assertEqual(send_notifications(), (0, 0))
        Notification.objects.update(next_attempt_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(send_notifications(), (1, 0))

    def test_interrupted_worker_lease_is_recovered(self):
        Notification.objects.update(status='sending', locked_at=timezone.now() - timedelta(minutes=6))
        self.assertEqual(send_notifications(), (1, 0))

    def test_eighth_failure_stops_automatic_retries(self):
        Notification.objects.update(attempts=7)
        with patch('submissions.mailer.EmailMessage.send', side_effect=OSError):
            self.assertEqual(send_notifications(), (0, 1))
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, 'failed')
        self.assertEqual(send_notifications(), (0, 0))
