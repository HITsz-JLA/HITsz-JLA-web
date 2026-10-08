# 网站发布与回滚

> 新增留言与投稿功能后，首次上线先按 [COMMUNITY.md](COMMUNITY.md) 安装后端并配置 Nginx，再运行本文的静态发布命令。发布脚本会先检查 `/community/api/health/`；日常审核留言不需要重新发布静态页面。

`deploy.ps1` 只发布 Hugo 生成的静态页面，不会安装或更新 Django 后端，也不会上传邮箱配置或重启邮件服务。仅修改文章、图片、样式或页面模板时，提交并推送 GitHub 后可直接运行本文命令。修改后端表单校验（例如将歌曲字段设为选填）时，须先更新后端；修改邮箱或抄送地址时，须另行同步生产配置并重启服务。具体步骤见 [COMMUNITY.md](COMMUNITY.md)。

新版上线候选已改为仓库内的原生 Hugo 模板，不再依赖 `JLA-HOMEPAGE-DRAFT` 目录。发布前会用 Python 3 标准库执行 `scripts/check_site.py`，拒绝测试路径、模拟表单、缺失资源和备份文件进入产物。脚本优先使用本地社团后端虚拟环境中的 Python，其次使用系统 Python。默认上线检查包括首页、歌曲、文章、文法、留言投稿、搜索页和搜索索引。

本次准备阶段仅修改本机仓库，**没有上传、切换网站或改动 Nginx**。请先提交并推送代码，之后再进行正式发布。`/homepage_draft/` 目前仍是独立测试站；待正式站验收成功后，再单独决定将它重定向到正式网址或撤下，保留上一版本的回滚记录。

## 推送 GitHub 后，一条命令发布

在本机 PowerShell 中执行：

```powershell
cd D:\HITSZ-JLA\HITsz-JLA-web
pwsh -NoProfile -File .\scripts\deploy.ps1
```

发布某篇文章时，可额外指定上线后必须检查的页面：

```powershell
pwsh -NoProfile -File .\scripts\deploy.ps1 -CheckPath /events/20260926recruit/
```

该命令会正式切换线上网站。它自动完成：

1. 检查本机 HEAD 等于 GitHub `origin/main`，拒绝未提交的已跟踪修改及未跟踪的网站内容。
2. 从已提交的 Git 快照提取源码和固定版本的 PaperMod 子模块，不把电脑中的其他未跟踪文件带入构建。
3. 使用 Hugo Extended 0.152.2，以 `https://hitszjla.club/` 为地址构建整站。
4. 检查静态产物的内部链接、真实投稿表单、歌单和测试残留，再生成全部输出文件的 SHA-256 清单，与服务器当前版本逐文件比较。
5. 仅打包和上传新增或变化的文件。使用 .NET PAX 压缩包处理中文、日文路径，不依赖外部 tar 命令。
6. 在服务器的新目录中保存变化文件，并硬链接复用同路径、同内容的已有文件。
7. 检查每个文件的大小、内容校验值和完整文件列表，保留发布状态与原版本信息。
8. 原子切换 `current`，通过 HTTPS 检查首页及指定文章的实际内容。如果健康检查失败，自动切回原版本并返回错误。
9. 准备完成时自动清理服务器增量压缩包、上传清单及临时目录，保留正式版本和回滚记录。

服务器只需 Python 3 标准库；硬链接使用 `os.link` 实现，不需要 rsync 或额外 Python 包。网站文件名改变后视为新文件，不按内容跨路径去重。

## 分开准备与上线

```powershell
# 构建、上传、校验、准备新版本，但不切换线上网站。
pwsh -NoProfile -File .\scripts\deploy.ps1 -PrepareOnly -CheckPath /events/20260926recruit/

# 把下面的编号换成准备步骤输出的完整发布编号。
pwsh -NoProfile -File .\scripts\deploy.ps1 -Action Publish -ReleaseId 20260928-160619-355-a5defca
```

发布编号格式为 `年月日-时分秒-毫秒-提交短编号`。准备后如果其他人先发布了另一个版本，脚本会拒绝覆盖；重新执行 Deploy 即可基于新版本生成候选版本。

## 查询状态与回滚

```powershell
pwsh -NoProfile -File .\scripts\deploy.ps1 -Action Status
pwsh -NoProfile -File .\scripts\deploy.ps1 -Action Status -ReleaseId 20260928-160619-355-a5defca
pwsh -NoProfile -File .\scripts\deploy.ps1 -Action Rollback -ReleaseId 20260928-160619-355-a5defca
```

回滚只允许针对当前在线的、由此脚本发布且记录了上一版本的版本。回滚不修改 GitHub，不删除新旧版本。若服务中断于切换期间，也可以先查询状态，再对当前版本执行 Rollback。

上传或准备失败后，可清理该次操作的临时资源：

```powershell
pwsh -NoProfile -File .\scripts\deploy.ps1 -Action Cleanup -ReleaseId 20260928-160619-355-a5defca
```

Cleanup 只删除该编号的上传临时目录和临时构建目录，不删除正式版本或发布状态。重试 Deploy 会生成新编号。

## 直接在服务器操作

服务器命令安装位置：`/usr/local/sbin/jla-web-deploy`。

```bash
jla-web-deploy status
jla-web-deploy status 20260928-160619-355-a5defca
jla-web-deploy publish 20260928-160619-355-a5defca
jla-web-deploy rollback 20260928-160619-355-a5defca
jla-web-deploy cleanup 20260928-160619-355-a5defca
```

在服务器只需要使用 status、publish、rollback、cleanup；begin、plan、prepare 是本机脚本自动调用的上传协议。

## 文件位置

| 内容 | 位置 |
| --- | --- |
| 本机入口脚本 | `D:\HITSZ-JLA\HITsz-JLA-web\scripts\deploy.ps1` |
| 服务器脚本源码 | `D:\HITSZ-JLA\HITsz-JLA-web\scripts\server_deploy.py` |
| 本机每次构建、清单及操作记录 | `D:\HITSZ-JLA\HITsz-JLA-web\.local\deploy\发布编号\` |
| 服务器正式版本 | `/var/www/HITsz-JLA-web/releases/发布编号/` |
| 线上版本指针 | `/var/www/HITsz-JLA-web/current` |
| 服务器发布状态、清单及回滚记录 | `/var/www/HITsz-JLA-web/.deploy/state/发布编号/` |

本机 `.local` 缓存被 Git 忽略，可在不再需要检查该次构建时清理。服务器历史正式版本不会自动删除，避免丢失回滚目标。旧的完整复制版本不会因新增脚本而自动去重。

## 环境与脚本更新

- 本机：PowerShell 7.4 以上（使用 `pwsh`）、Git、Hugo Extended 0.152.2、OpenSSH。
- 本机脚本使用现有 SSH 私钥，并按已保存的 `111.228.7.90` 主机密钥验证服务器。
- 服务器：Python 3、支持硬链接的同一文件系统。本服务器当前环境满足要求。
- 本次已经安装服务器脚本。以后修改 `server_deploy.py`，执行下面的命令更新；原服务器脚本会备份到 `.deploy/tool-backups/`，不会切换网站。

```powershell
pwsh -NoProfile -File .\scripts\deploy.ps1 -Action Install
```

将 `scripts/` 中的脚本和说明提交到 GitHub，可以让后续维护者复用；不要提交 `.local` 中的构建文件。

## 硬链接使用约定

已经准备或发布的 `releases` 目录应保持不变。不要直接编辑其中的文件、覆盖解压、执行递归 chmod/chown，或使用原地覆盖写入。对硬链接文件的原地修改可能同时影响其他版本；所有更新应通过新发布版本完成。

## 测试

在 Linux 环境、包含两个 Python 文件的目录中运行：

```bash
python3 test_server_deploy.py
```

测试使用独立临时目录和本地 HTTP 服务，涵盖硬链接复用、变化文件隔离、删除文件、中日文路径、校验失败、路径穿越/符号链接拒绝、并发版本冲突、零变化发布、上线检查失败自动回滚及手动回滚；不会操作真实线上网站。
