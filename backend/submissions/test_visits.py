import json
import uuid
from django.apps import apps
from django.contrib.auth.models import Group, User
from django.test import Client, TestCase, override_settings
from .apps import grant_visit_permission
from .models import PageVisit


class VisitTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = '/community/api/visits/'

    def send(self, data=None, **headers):
        defaults = dict(HTTP_ORIGIN='http://testserver', HTTP_X_JLA_VISIT='1', REMOTE_ADDR='203.0.113.5')
        defaults.update(headers)
        return self.client.post(self.url, json.dumps(data or {
            'path': '/lyrics/%E5%B0%91%E5%A5%B3/', 'event_id': str(uuid.uuid4())}),
            content_type='application/json', **defaults)

    def test_private_server_timestamp_and_ip_and_retry_deduplication(self):
        data = {'path': '/lyrics/', 'event_id': str(uuid.uuid4()),
                'visited_at': '2000-01-01', 'ip_address': '1.2.3.4'}
        for _ in range(2):
            self.assertEqual(self.send(data).status_code, 204)
        item = PageVisit.objects.get()
        self.assertEqual(item.ip_address, '203.0.113.5')
        self.assertGreater(item.visited_at.year, 2000)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertNotContains(self.client.get('/community/api/feedback/'), '203.0.113.5')

    def test_origin_and_header_are_required(self):
        for headers in [{'HTTP_ORIGIN': ''}, {'HTTP_ORIGIN': 'https://evil.example'},
                        {'HTTP_X_JLA_VISIT': ''}]:
            self.assertEqual(self.send(**headers).status_code, 403)
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_untrusted_proxy_headers_are_ignored(self):
        self.assertEqual(self.send(HTTP_X_REAL_IP='1.2.3.4', HTTP_X_FORWARDED_FOR='1.2.3.4').status_code, 204)
        self.assertEqual(PageVisit.objects.get().ip_address, '203.0.113.5')

    @override_settings(TRUST_LOOPBACK_PROXY=True)
    def test_only_loopback_proxy_can_supply_real_ip(self):
        self.assertEqual(self.send(REMOTE_ADDR='127.0.0.1', HTTP_X_REAL_IP='2001:db8::1').status_code, 204)
        self.assertEqual(PageVisit.objects.get().ip_address, '2001:db8::1')
        self.send(HTTP_X_REAL_IP='1.2.3.4')
        self.assertEqual(PageVisit.objects.first().ip_address, '203.0.113.5')

    def test_paths_and_event_ids_are_validated(self):
        for path in ['https://evil.example/', '//evil.example', '/a?secret=x', '/a#secret',
                     '/a%3Fsecret=x', '/a/../b', '/community/admin/', '/a\\b', '/a%00', '/'+'a'*1024]:
            with self.subTest(path=path):
                self.assertEqual(self.send({'path': path, 'event_id': str(uuid.uuid4())}).status_code, 400)
        self.assertEqual(self.send({'path': '/', 'event_id': 'bad'}).status_code, 400)
        self.assertEqual(self.send().status_code, 204)
        self.assertEqual(PageVisit.objects.get().path, '/lyrics/少女/')

    def test_rate_limit(self):
        from unittest.mock import patch
        with patch('submissions.visits.consume_limit', return_value=False):
            self.assertEqual(self.send().status_code, 429)
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_admin_permissions_aggregation_and_filters(self):
        self.send({'path': '/lyrics/', 'event_id': str(uuid.uuid4())})
        self.send({'path': '/lyrics/', 'event_id': str(uuid.uuid4())})
        self.send({'path': '/', 'event_id': str(uuid.uuid4())})
        url = '/community/admin/submissions/pagevisit/'
        self.assertEqual(self.client.get(url).status_code, 302)
        actor = User.objects.create_user('viewer', is_staff=True)
        self.client.force_login(actor)
        self.assertEqual(self.client.get(url).status_code, 403)
        group = Group.objects.create(name='社团内容审核员')
        actor.groups.add(group)
        grant_visit_permission(apps.get_app_config('submissions'))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context_data['visit_total'], 3)
        self.assertEqual(response.context_data['visit_page_total'], 2)
        self.assertEqual(list(response.context_data['visit_pages'])[0]['total'], 2)
        self.assertEqual(self.client.get(url, {'q': '/lyrics/'}).context_data['visit_total'], 2)
        editor = Client()
        editor.force_login(actor)
        self.assertEqual(editor.get(url+'add/').status_code, 403)
        self.assertEqual(editor.post(url+str(PageVisit.objects.first().pk)+'/change/', {}).status_code, 403)
