import secrets
from pathlib import Path
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = '创建最小权限审核账户；随机密码只写入指定的私有文件，不打印。'

    def add_arguments(self, parser):
        parser.add_argument('--username', default='moderator')
        parser.add_argument('--credentials-file', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        user_model = get_user_model()
        if user_model.objects.filter(username=options['username']).exists():
            self.stdout.write('审核账户已存在，密码保持不变。')
            return
        path = Path(options['credentials_file']).resolve()
        if path.exists():
            raise CommandError('凭据文件已存在，请指定新的私有路径。')
        group, _ = Group.objects.get_or_create(name='社团内容审核员')
        permissions = Permission.objects.filter(content_type__app_label='submissions', codename__in=[
            'view_submission', 'change_submission', 'moderate_submission',
            'view_notification', 'change_notification', 'view_moderationlog',
        ])
        group.permissions.set(permissions)
        password = secrets.token_urlsafe(24)
        user = user_model.objects.create_user(options['username'], password=password, is_staff=True)
        user.groups.add(group)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as file:
            file.write(f'管理员用户名：{user.username}\n初始密码：{password}\n登录后请修改密码。\n')
        path.chmod(0o600)
        self.stdout.write('审核账户已创建；初始凭据已写入指定私有文件。')
