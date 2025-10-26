# HITsz-JLA-web
这是深圳工业大学日语社的社团网站。

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
