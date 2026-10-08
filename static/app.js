const record=document.getElementById('record'),toggle=document.getElementById('toggle'),glyph=document.getElementById('play-icon');
const featuredAudio=document.getElementById('featured-audio'),playbackStatus=document.getElementById('playback-status');
const playlist=[...(document.getElementById('featured-playlist')?.querySelectorAll('a')||[])].map(item=>({...item.dataset,url:item.getAttribute('href')}));
const seek=document.getElementById('track-seek'),elapsed=document.getElementById('track-elapsed'),duration=document.getElementById('track-duration');
let playing=false,playPending=false,playAttempt=0,trackIndex=0,seeking=false;
function updatePlayer(message,error=false){
  const active=playPending||(featuredAudio&&!featuredAudio.paused&&!featuredAudio.ended);
  if(record){record.style.animationPlayState=playing&&!document.hidden?'running':'paused';record.dataset.playing=String(playing);}
  if(toggle){toggle.setAttribute('aria-pressed',String(Boolean(active)));toggle.setAttribute('aria-label',active?'暂停歌曲':'播放歌曲');toggle.setAttribute('aria-busy',String(playPending));}
  if(glyph)glyph.setAttribute('d',active?'M7 6h4v12H7zM14 6h4v12h-4z':'M8 5.5v13l10-6.5z');
  if(message&&playbackStatus){playbackStatus.textContent=message;playbackStatus.dataset.error=String(error);}
}
function formatTime(value){const seconds=Math.max(0,Math.floor(Number.isFinite(value)?value:0));return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;}
function updateProgress(reset=false){
  if(!seek)return;
  const total=reset?0:featuredAudio.duration;
  const ready=Number.isFinite(total)&&total>0;
  seek.disabled=!ready;seek.max=ready?String(total):'0';
  if(!seeking||reset)seek.value=ready?String(Math.min(featuredAudio.currentTime||0,total)):'0';
  const position=Number(seek.value)||0;
  elapsed.textContent=formatTime(position);duration.textContent=ready?formatTime(total):'--:--';
  seek.style.setProperty('--played',ready?`${position/total*100}%`:'0%');
  seek.setAttribute('aria-valuetext',ready?`${formatTime(position)} / ${formatTime(total)}`:'音频加载中');
}
async function startPlayback(){
  const attempt=++playAttempt;
  playPending=true;updatePlayer('正在加载音频…');
  try{await featuredAudio.play();}
  catch(error){if(attempt!==playAttempt)return;playPending=false;playing=false;featuredAudio.pause();updatePlayer(error.name==='NotAllowedError'?'请再次点击播放按钮':'音频加载失败，请重试或进入歌曲详情',true);}
}
async function selectTrack(offset){
  if(!playlist.length)return;
  const resume=playPending||(!featuredAudio.paused&&!featuredAudio.ended);
  ++playAttempt;playPending=false;playing=false;seeking=false;featuredAudio.pause();
  trackIndex=(trackIndex+offset+playlist.length)%playlist.length;
  const track=playlist[trackIndex];
  document.getElementById('track-counter').textContent=`${trackIndex+1}/${playlist.length} ${track.date}`;
  document.getElementById('track-title').textContent=track.title;
  document.getElementById('track-artist').textContent=track.artist;
  document.getElementById('track-album').textContent=`专辑：${track.album}`;
  const cover=document.getElementById('track-cover');cover.src=track.cover;cover.alt=`${track.title} 专辑封面`;
  document.getElementById('track-detail').href=track.url;
  featuredAudio.src=track.src;featuredAudio.load();updateProgress(true);
  updatePlayer(`已切换到 ${track.title}`);
  if(resume)await startPlayback();
}
if(toggle&&featuredAudio){
  toggle.addEventListener('click',async()=>{
    if(playPending||!featuredAudio.paused){++playAttempt;playPending=false;playing=false;featuredAudio.pause();updatePlayer('已暂停');return;}
    await startPlayback();
  });
  document.getElementById('previous-track')?.addEventListener('click',()=>selectTrack(-1));
  document.getElementById('next-track')?.addEventListener('click',()=>selectTrack(1));
  featuredAudio.addEventListener('playing',()=>{if(featuredAudio.paused)return;playPending=false;playing=true;updatePlayer('正在播放');});
  featuredAudio.addEventListener('waiting',()=>{if(featuredAudio.paused)return;playing=false;updatePlayer('正在缓冲…');});
  featuredAudio.addEventListener('pause',()=>{if(!featuredAudio.paused)return;playPending=false;playing=false;updatePlayer('已暂停');});
  featuredAudio.addEventListener('ended',()=>{playPending=false;playing=false;updateProgress();updatePlayer('播放结束，点击重听');});
  featuredAudio.addEventListener('error',()=>{if(!featuredAudio.error)return;playPending=false;playing=false;featuredAudio.pause();updatePlayer('音频加载失败，请重试或进入歌曲详情',true);});
  for(const event of ['loadedmetadata','durationchange','timeupdate','seeked'])featuredAudio.addEventListener(event,()=>updateProgress());
  featuredAudio.addEventListener('emptied',()=>{seeking=false;updateProgress(true);});
  seek?.addEventListener('input',()=>{
    if(seek.disabled)return;
    seeking=true;
    featuredAudio.currentTime=Math.max(0,Math.min(Number(seek.value),featuredAudio.duration));
    updateProgress();
  });
  for(const event of ['change','blur','pointercancel'])seek?.addEventListener(event,()=>{seeking=false;updateProgress();});
  updateProgress();
}
// Keep the animation tied to actual playback, and freeze it in background tabs.
document.addEventListener('visibilitychange',()=>{if(record)record.style.animationPlayState=playing&&!document.hidden?'running':'paused';});
