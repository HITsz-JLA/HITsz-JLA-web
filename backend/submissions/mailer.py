from datetime import timedelta
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Notification, RateBucket


def send_notifications(limit=10):
    """Persist work before SMTP; lease recovery handles interrupted workers."""
    sent = failed = 0
    for _ in range(limit):
        now = timezone.now()
        with transaction.atomic():
            item = Notification.objects.select_for_update().filter(
                Q(status='pending', next_attempt_at__lte=now) |
                Q(status='sending', locked_at__lt=now - timedelta(minutes=5))
            ).order_by('next_attempt_at', 'pk').first()
            if item is None:
                break
            item.status = 'sending'
            item.locked_at = now
            item.attempts += 1
            item.save(update_fields=['status', 'locked_at', 'attempts'])
        try:
            if not settings.NOTIFY_TO:
                raise ValueError('No administrator recipients configured')
            submission = item.submission
            kind = submission.get_kind_display()
            link = f'{settings.COMMUNITY_BASE_URL}/community/admin/submissions/submission/{submission.pk}/change/'
            body = (f'收到一条新的{kind}，请登录后台审核。\n\n'
                    f'提交时间：{timezone.localtime(submission.created_at):%Y-%m-%d %H:%M}\n'
                    f'署名：{submission.nickname or "匿名"}\n')
            if submission.song_title:
                body += f'歌曲：{submission.song_title}\n歌手：{submission.artist}\n试听：{submission.music_url}\n'
            body += f'\n内容摘要：\n{submission.body[:400]}\n\n审核页面：{link}\n\n此链接仅打开后台，审核操作需要登录。'
            email = EmailMessage(
                settings.EMAIL_SUBJECT_PREFIX + f'收到新的{kind}', body,
                settings.DEFAULT_FROM_EMAIL, settings.NOTIFY_TO, cc=settings.NOTIFY_CC,
                headers={'Message-ID': f'<jla-submission-{submission.pk}@hitszjla.club>'},
            )
            if email.send(fail_silently=False) != 1:
                raise RuntimeError('Mail backend did not accept the message')
        except Exception as exc:
            Notification.objects.filter(pk=item.pk).update(
                status='failed' if item.attempts >= 8 else 'pending', locked_at=None,
                next_attempt_at=now + timedelta(seconds=min(60 * 2 ** (item.attempts - 1), 3600)),
                last_error=type(exc).__name__, delivery_mode=settings.EMAIL_MODE,
            )
            failed += 1
        else:
            Notification.objects.filter(pk=item.pk).update(
                status='sent', locked_at=None, sent_at=timezone.now(),
                last_error='', delivery_mode=settings.EMAIL_MODE,
            )
            sent += 1
    RateBucket.objects.filter(expires_at__lt=timezone.now()).delete()
    return sent, failed
