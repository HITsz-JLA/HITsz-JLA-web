# HITsz-JLA-web
这是深圳工业大学日语社的社团网站。

## 新版正式站的构建与发布

新版首页和全部栏目使用仓库内的 Hugo 模板，源码位于 `layouts/partials/site/`、`layouts/_default/`，样式与脚本位于 `static/`。`content/` 和 `static/image/`、`static/music/`、`static/audio/` 仍是内容及资源的唯一来源；不用复制设计稿输出，不需要 Node.js 或字体处理工具参与正式构建。

- 首页歌曲按发布日期倒序生成完整歌单；公告、活动、文章和文法自动使用各栏目的最新已发布内容。
- 搜索索引、栏目、详情、RSS 和站点地图随 Hugo 构建自动更新。
- 首页和 `/participate/` 使用现有 `/community/api/`，真实提交进入审核与邮件任务队列；静态构建不包含留言快照或模拟投稿功能。
- 标题与日文装饰字体自托管。小体积字体优先加载，完整字库用于新增字符回退，发布新文章不需要重新生成字体。
- 旧 `/about/about/`、`/join/`、`/join/join/`、`/feedback/`、`/submit-song/` 入口保留跳转。

本机检查（不上传服务器）：

```powershell
Set-Location D:\HITSZ-JLA\HITsz-JLA-web
hugo --destination .local/launch/public --environment production --minify --cleanDestinationDir
.\.local\community\venv\Scripts\python.exe .\scripts\check_site.py .\.local\launch\public
node .\scripts\test_player.mjs .\.local\launch\public
```

`node` 只用于播放器逻辑测试；页面生成只需要既有的 Hugo Extended 0.152.2。完整的本地留言审核测试仍使用 `scripts/community.ps1`，邮件模式与本地数据目录说明见 `scripts/COMMUNITY.md`。

提交并推送 GitHub **之后**，沿用 `pwsh -NoProfile -File .\scripts\deploy.ps1` 进行正式发布。脚本会先检查推送状态、后台健康状态和构建产物，再增量上传并以硬链接复用未改变的资源。此轮只准备本地代码，不执行服务器安装、上传或切换；服务器测试目录的退役放在正式发布后的独立步骤处理。

## Markdown编写规范

在md文档的最前面需要填写以下信息：

	---
	title: "标题内容" /*写完这个就不要在markdown正文里面用#写标题了*/
	date: 2025-10-24 /*这个是日期规范，千万不要写现实时间以后的日期，会有bug*/
	draft: false /*不是草稿*/
	---

在这个之后写入正文部分，然后正文可能会比较长，在首页上会占据大量篇幅，所以必须要在文档合适的部位加入：

	<!--more-->

然后主页上只能看得到这个节点之前的文本，打开详情之后可以看得到其他内容

如果要添加图片内容，先把图片存在\\static\\image下，然后路径填写\\image\\图片.jpg


## 每日一曲MD文件编写特殊规范

	---
	title: "恋風 - 幾田りら"
	date: 2025-10-26
	draft: false
	---
	![专辑封面](/image/koikaze.jpg)
	<!--more-->
	<center style="font-family: 'Microsoft YaHei', 'Yu Gothic', 'Meiryo', 'MS PGothic', sans-serif;">
	## 恋風 - 幾田りら
	#### 作曲: 幾田りら
	#### 作词: 幾田りら

	<audio controls src="/music/koikaze.mp3"></audio> /*音频播放器*/

	/*跳转按钮*/
	<div class="music-buttons">
	<a href="https://music.163.com/song?id=2690100940">网易云</a>
	<a href="https://y.qq.com/n/ryqq/songDetail/000FE7Xu21Oncj">QQ音乐</a>
	</div>

	/*以下正文*/

	日文部分请用** **粗体表示
	中文翻译不需粗体
	上标使用<sup>1</sup>表序号
	在歌词最后使用1.批注相关内容

请将音频文件存于/static/music/
请将专辑图片存于/static/image/
以上
