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
