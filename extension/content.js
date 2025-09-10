// 检测页面音频元素
function detectAudioSources() {
  console.log('[Content] Detecting audio sources...');
  
  // 查找所有audio和video元素
  const audioElements = document.querySelectorAll('audio, video');
  console.log(`[Content] Found ${audioElements.length} audio/video elements`);
  
  audioElements.forEach((el, i) => {
    console.log(`[Content] Element ${i}:`, {
      tagName: el.tagName,
      src: el.src,
      autoplay: el.autoplay,
      muted: el.muted,
      paused: el.paused,
      volume: el.volume,
      currentTime: el.currentTime,
      duration: el.duration
    });
  });
  
  // 查找Gather特有的音频相关元素
  const gatherAudio = document.querySelectorAll('[id*="audio"], [class*="audio"], [data-testid*="audio"]');
  console.log(`[Content] Found ${gatherAudio.length} Gather audio-related elements`);
  
  // 检查WebRTC相关
  if (window.RTCPeerConnection) {
    console.log('[Content] WebRTC is available');
  }
  
  return { audioElements, gatherAudio };
}

// 页面加载后检测音频
setTimeout(() => {
  detectAudioSources();
  
  // YouTube特殊处理
  if (location.hostname.includes('youtube.com')) {
    console.log('[Content] YouTube page detected');
    const videoElement = document.querySelector('video');
    if (videoElement) {
      console.log('[Content] YouTube video found:', {
        paused: videoElement.paused,
        muted: videoElement.muted,
        volume: videoElement.volume,
        currentTime: videoElement.currentTime
      });
    }
  }
}, 3000);

// 创建字幕容器
const containerId = "__gather_subtitles_container__";
let container = document.getElementById(containerId);
if (!container) {
  container = document.createElement("div");
  container.id = containerId;
  document.body.appendChild(container);
}

// 接收后台推送的字幕消息
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "SUBTITLE_UPDATE") {
    renderLine(msg.payload);
  }
});

function renderLine({ en, zh, isFinal }) {
  const line = document.createElement("div");
  line.className = "subtitle-line" + (isFinal ? " final" : "");
  line.innerHTML = `
    <div class="zh">${escapeHtml(zh || "")}</div>
    <div class="en">${escapeHtml(en || "")}</div>
  `;
  container.appendChild(line);
  container.scrollTop = container.scrollHeight;

  // 临时字幕自动消失
  if (!isFinal) {
    setTimeout(() => line.remove(), 8000);
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}
