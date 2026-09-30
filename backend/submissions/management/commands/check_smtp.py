from django.core.mail.backends.smtp import EmailBackend
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '只验证 SMTP 加密连接与登录，不发送邮件。'

    def handle(self, *args, **options):
        try:
            connection = EmailBackend(fail_silently=False)
            connection.open()
            connection.close()
        except Exception as exc:
            raise CommandError(f'SMTP 验证失败，错误类型：{type(exc).__name__}。请检查私有配置。') from None
        self.stdout.write('SMTP 加密连接与身份验证成功；没有发送邮件。')
