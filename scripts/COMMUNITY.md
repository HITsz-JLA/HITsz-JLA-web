# 留言、每周一曲投稿与邮件审核

## 已实现的行为

- 顶部导航采用等宽、整格可点击的入口：宽屏电脑显示单行，手机及窄窗口显示双行。“关于&加入”合并展示社团介绍和加入方式，“留言&投稿”统一入口位于 `/participate/`。首页中间不再单独放置留言、投稿入口。
- `/participate/` 上方是“匿名留言”和“歌曲投稿”两个按钮，下方展示公开留言；点击按钮打开填写弹窗，提交成功后关闭并显示提示。
- 留言无需账号和分类选择，可不署名，通过审核后才出现在公开留言区。管理员可回复、拒绝、下架，操作保留审核记录。
- 歌曲投稿必填歌名与歌手，试听链接、“推荐理由和日语语言知识点”及署名均为选填；填写链接时须使用 HTTPS。只收链接，不上传音频。关闭弹窗会暂时保留填写内容，刷新或离开页面后不保留。
- 原 `/feedback/`、`/submit-song/` 链接会跳转到统一页面，并打开对应弹窗。
- 每份投稿在同一数据库事务中生成一条通知任务；邮件由独立进程发送到配置的管理员邮箱，并抄送邮箱信息文件中指定的收件人。
- 后台 `/community/admin/` 需要账号密码；邮件只提供后台链接，不能直接通过点击邮件完成审批。
- 歌曲审核通过后进入候选，不会自动替换首页歌曲。可以从后台导出 Markdown 草稿，编辑后按原流程发布到 `content/lyrics/`。
- 邮箱授权码、后台密码、数据库均不进入 Git，也不进入 Hugo 静态输出。

## 本机启动和验收

工作目录：`D:\HITSZ-JLA\HITsz-JLA-web`。Python 虚拟环境和初始管理员已在本机准备好。

在 PowerShell 7 中执行：

```powershell
Set-Location D:\HITSZ-JLA\HITsz-JLA-web
pwsh -NoProfile -File .\scripts\community.ps1 -Action Start
```

这个窗口保持运行，Ctrl+C 停止。启动会重新生成 Hugo 页面，同时启动本地网站和通知进程；修改静态页面后重新启动即可。

| 用途 | 地址或路径 |
| --- | --- |
| 本地首页 | http://127.0.0.1:8790/ |
| 留言与投稿统一入口 | http://127.0.0.1:8790/participate/ |
| 直接打开留言弹窗 | http://127.0.0.1:8790/participate/?compose=feedback |
| 直接打开投稿弹窗 | http://127.0.0.1:8790/participate/?compose=song |
| 审核后台 | http://127.0.0.1:8790/community/admin/ |
| 初始管理员 | 用户名 `moderator`，随机密码在 `.local/community/admin-credentials.txt` |
| 本地配置 | `.local/community/config.json` |
| 本地数据 | `.local/community/data/community.sqlite3` |
| 邮件预览 | `.local/community/data/mail-preview/` 中的文件 |

**本地默认使用文件邮件模式，不向真实邮箱发送测试留言。** 通知进程通常在 15 秒内生成邮件文件；后台的发送方式显示 `file`。SMTP 加密连接和授权验证已成功，实际投递仍需上线后验证。

推荐验收顺序：提交留言 → 后台看到“待审核” → 查看本地邮件预览 → 后台改为“已通过”并填写“公开回复” → 刷新留言板 → 下架并再次刷新。歌曲投稿可单独测试，通过后选中并执行“导出已通过歌曲的 Markdown 草稿”。本机可能留有带“本地验收测试”字样的示例；不上传本机数据库。

常用指令：

```powershell
# 后端测试，使用独立临时数据库，不发送真实邮件
pwsh -File .\scripts\community.ps1 -Action Test
# 只验证 SMTP 加密连接、登录，不发送邮件
pwsh -File .\scripts\community.ps1 -Action CheckSmtp
# 数据库一致性备份，输出到 .local/community/backups/
pwsh -File .\scripts\community.ps1 -Action Backup
# 在终端交互修改后台密码
pwsh -File .\scripts\community.ps1 -Action SetPassword -Username moderator
# 更新 Python 依赖、迁移数据库、刷新配置；保留已有管理员密码
pwsh -File .\scripts\community.ps1 -Action Setup
```

另一台电脑首次安装需先准备 Python 3.12、PowerShell 7.4+、Hugo Extended 0.152.2 和主题子模块，然后执行：

```powershell
pwsh -File .\scripts\community.ps1 -Action Setup -PythonExecutable 'C:\实际路径\python.exe'
```

`Setup` 从 `email/emailinfo.txt` 导入邮箱信息。本机发件账号也用作主要通知收件人，文件中“需要抄送的邮箱”作为 CC。如需不同的主收件人，修改私有配置的 `notify_to` 数组；再次 Setup / ExportProductionConfig 会按邮箱文件重新导入收件设置。

## 结构与硬链接发布的关系

静态页面仍由 Hugo 生成，由原 `scripts/deploy.ps1` 做增量、硬链接发布。动态功能是独立 Django 服务：

```text
访问者 → Nginx
          ├─ /participate/、原页面 → 原 Hugo current
          └─ /community/ → 127.0.0.1:8790 → Django + SQLite
                                              └─ 通知任务 → 独立邮件进程 → SMTP
```

现有歌牌程序使用的 `/api/`、`/karuta/` 和 WebSocket 路由保留。新服务使用独立 `/community/` 前缀。

| 服务器路径 | 内容 |
| --- | --- |
| `/opt/jla-community/releases/` | 后端代码与虚拟环境版本 |
| `/opt/jla-community/current` | 当前后端版本的软链接 |
| `/etc/jla-community/config.json` | 私有配置、密钥与 SMTP 授权码 |
| `/var/lib/jla-community/community.sqlite3` | 投稿、账号、审核记录、通知任务 |
| `/var/www/jla-community-admin-static/` | 后台 CSS、JavaScript 等 |
| `/var/backups/jla-community/` | 数据库一致性备份 |
| `/var/www/HITsz-JLA-web/releases/` | 原静态发布版本，继续硬链接复用图片和音频 |

**数据库不能硬链接到每个发布版本中，也不要直接复制正在使用的 SQLite 文件作为备份。** 代码回滚不回滚留言；备份命令使用 SQLite 的在线备份接口，包含 WAL 中已提交的内容。

## 首次上线：先后端，再发布静态页面

以下是待执行的上线步骤。本次开发未修改服务器配置、未启动线上新服务、未推送 GitHub。

### 1. 本机检查并推送 GitHub

```powershell
Set-Location D:\HITSZ-JLA\HITsz-JLA-web
pwsh -File .\scripts\community.ps1 -Action Test
git status --short
git add .gitignore .gitattributes config.toml layouts assets/css/extended/community.css assets/css/extended/navigation.css assets/css/extended/herocard.css content/about/_index.md content/participate content/feedback content/submit-song static/js/community.js backend scripts/community.ps1 scripts/COMMUNITY.md scripts/deploy.ps1 scripts/DEPLOY.md
git diff --cached --stat
git commit -m "Add moderated community feedback and weekly song submissions"
git push origin main
```

不要强制添加 `email/`、`.local/`、密码文件或数据库。检查暂存变更时应确认没有把其他未完成内容混入提交。

### 2. 本机生成生产配置并上传代码

生产配置有独立随机密钥，只导入邮箱设置，不导入本地账号、测试留言或数据库。下面的 SSH 选项沿用已有部署脚本。

```powershell
pwsh -File .\scripts\community.ps1 -Action ExportProductionConfig
$sshOptions = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlias=111.228.7.90')
ssh @sshOptions root@hitszjla.club 'install -d -m 700 /root/jla-community-upload /etc/jla-community'
git archive --format=tar.gz --output=.local/community/backend.tar.gz HEAD backend
scp @sshOptions .local/community/backend.tar.gz root@hitszjla.club:/root/jla-community-upload/backend.tar.gz
scp @sshOptions .local/community/production-config.json root@hitszjla.club:/root/jla-community-upload/config.json
ssh @sshOptions root@hitszjla.club
```

### 3. 在服务器终端安装后端

以下命令在 SSH 登录后的 Linux 终端执行。

```bash
apt-get update
apt-get install -y python3-venv curl
cd /root/jla-community-upload
tar -xzf backend.tar.gz
install -m 600 config.json /etc/jla-community/config.json
bash backend/deploy/install.sh
```

安装脚本创建独立服务账号，安装依赖、迁移数据库、收集后台资源、注册网站进程和邮件进程，并启用每日备份。安装期间会建立独立后端版本，不修改 Nginx 站点文件。

创建线上审核账号（与本地密码不同），再交互设置自己的密码：

```bash
export JLA_CONFIG_FILE=/etc/jla-community/config.json
/opt/jla-community/current/.venv/bin/python /opt/jla-community/current/backend/manage.py init_moderator --username moderator --credentials-file /root/jla-community-admin.txt
/opt/jla-community/current/.venv/bin/python /opt/jla-community/current/backend/manage.py changepassword moderator
/opt/jla-community/current/.venv/bin/python /opt/jla-community/current/backend/manage.py check_smtp
```

`moderator` 可以审核、回复、下架、导出歌曲、查看通知并重试失败通知，不具有管理其他账号的超级权限。以后需要管理账号时可在服务器执行 Django 的 `createsuperuser`。

### 4. 在服务器接通 Nginx 路由

当前启用站点是 `/etc/nginx/sites-available/hitszjla`。

```bash
cp -a /etc/nginx/sites-available/hitszjla /root/hitszjla-nginx-before-community.conf
nano /etc/nginx/sites-available/hitszjla
```

该文件有多个 `server` 块，其中两个监听 443。请找到同时包含 **`listen 443 ssl;` 和 `server_name hitszjla.club;`** 的主域名配置块，在 `server_name hitszjla.club;` 下一行添加 include，与已有 `location` 同级。

**不要加到 `server_name www.hitszjla.club;` 的配置块中**：它用于将 www 跳转到主域名。加错块时，`nginx -t` 仍会通过，但主域名的 `/community/api/health/` 会返回 404。也不要放进某个 `location` 中或替换其他路由。

```nginx
include /etc/nginx/snippets/jla-community.conf;
```

添加后的主域名配置块应包含以下内容（其他原有配置保持不变）：

```nginx
server {
    listen 443 ssl;
    # 原有 IPv6、证书等配置……
    server_name hitszjla.club;
    include /etc/nginx/snippets/jla-community.conf;

    root /var/www/HITsz-JLA-web/current;
    # 原有 location 等配置……
}
```

保存后检查并重载：

```bash
nginx -t && systemctl reload nginx
curl --fail https://hitszjla.club/community/api/health/
systemctl status jla-community jla-community-mail --no-pager
```

健康检查应包含 `"ok": true`、`"service": "jla-community"`、`"api_version": 1`。此时可以登录 `https://hitszjla.club/community/admin/`。

### 5. 回到本机发布静态页面

```powershell
Set-Location D:\HITSZ-JLA\HITsz-JLA-web
pwsh -File .\scripts\deploy.ps1 -CheckPath /participate/
```

部署脚本已增加后端健康检查；后端没接通时会拒绝发布新前端。`-Action Publish` 也会检查；查询、回滚和清理不会依赖后端可用性。原有资源复用、发布校验和回滚逻辑保留。

用线上表单提交一条明确标注为测试的留言，确认管理员主邮箱与抄送邮箱都收到通知，再从后台审核、刷新留言墙。这一步会真实发邮件。验收后可下架测试留言。检查垃圾邮件箱，并区分“SMTP 接受”与“最终进入收件箱”。

## 以后如何使用和更新

**日常审核留言：** 邮件进入后台 → 登录 → 打开投稿 → 状态改为“已通过”/“已拒绝” → 可填写公开回复、内部备注 → 保存。留言的公开与下架立即作用于接口，访问者刷新留言板即可看到；无需运行 Hugo、推送 GitHub 或重启服务。

**发表每周一曲：** 后台筛选歌曲并审核 → 勾选已通过歌曲 → 导出 Markdown 草稿 → 解压至本机 `content/lyrics/` → 补齐封面、栏目字段和正文 → 将 `draft: true` 改为 `false` → 本地预览 → Git 提交推送 → 原部署脚本发布。原有首页每周一曲选取规则保持不变。后台“已选为每周一曲”是编辑记录，不能代替 Git 发布。

**更新页面/文章：** Git 提交推送后继续执行原 `scripts/deploy.ps1`。无需重装后端。

**更新后端代码：** 提交推送后按第 2 步只生成并上传 `backend.tar.gz`（不重新上传私有配置）；服务器解压后再次 `bash backend/deploy/install.sh`。不重复创建账号、不重复添加 Nginx include。脚本会先备份已有数据库。未来若有不兼容数据库迁移，应先安排停机和专门的数据迁移方案；自动回退代码不撤销数据库迁移。

## 运维、邮件重试与恢复

```bash
# 网站与邮件进程日志（SMTP 授权码不会由应用输出）
journalctl -u jla-community -u jla-community-mail -n 100 --no-pager
# 重启两个进程
systemctl restart jla-community jla-community-mail
# 查看每日备份计划；按服务器时区约 04:20 执行，带最多 5 分钟随机延迟
systemctl list-timers jla-community-backup.timer
# 立即生成一次一致性备份
systemctl start jla-community-backup.service
ls -lh /var/backups/jla-community/
```

通知失败会延迟重试，最多自动尝试 8 次，之后可在后台“邮件通知”中选择失败项重新排队。不要对已发送通知手工反复重发。SMTP 成功之后进程恰好崩溃的极端情况下可能重复通知，因此邮件投递是“至少一次”，不是严格的“仅一次”；投稿本身有重复提交保护。

每日备份暂不自动删除，请定期将备份和私有配置另存到可信位置，并按实际空间制定保留周期。旧后端版本包含虚拟环境，也需在确认回滚窗口结束后手工整理；不要把运行中的 `current` 目标删掉。

数据恢复应在维护窗口由管理员执行：停止 `jla-community`、`jla-community-mail` 和备份定时器，保留当前数据库及 `-wal`/`-shm` 文件作为事故副本，将选定的一致性备份恢复成 `/var/lib/jla-community/community.sqlite3`，确保文件属主为 `jla-community:jla-community`，再启动服务。恢复备份会丢失备份之后的投稿，不应作为普通代码回滚步骤。

## 开发文件导航

- `layouts/index.html`、`config.toml`：首页入口与导航。
- `layouts/participate/`、`layouts/partials/community-dialog.html`：统一页面与弹窗表单；`layouts/feedback/`、`layouts/submit-song/` 保留旧地址跳转。
- `assets/css/extended/community.css`、`static/js/community.js`：样式与表单交互。
- `backend/submissions/`：数据模型、接口、审核与邮件通知。
- `backend/deploy/`：服务器安装脚本、Nginx 片段、systemd 服务和备份定时器。
- `scripts/community.ps1`：本机启动、测试、备份、配置导出。

本地普通 `hugo server` 只提供静态页面，不能处理留言接口；联调请用 `community.ps1 -Action Start`。Windows PowerShell 5 的 `powershell` 与 PowerShell 7 的 `pwsh` 不同，这两个部署脚本需要后者。

## 本次验证范围

已通过 14 项后端测试、Hugo 整站构建、浏览器中的留言与歌曲提交、审核公开与回复展示、桌面及窄屏布局检查、SMTP 加密登录验证、数据库备份完整性检查、配置与脚本语法检查。测试通知使用内存或文件模式，没有真实邮件投递。

服务器安装脚本尚未在线上执行；systemd、Nginx 对接及真实投递需按首次上线步骤验收。原 `test_server_deploy.py` 依赖 Linux 的 `fcntl`，本机 Windows 无法运行该用例；本次没有修改其服务器硬链接发布实现。
