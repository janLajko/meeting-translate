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
  
  // Zep.us特殊处理
  if (location.hostname.includes('zep.us')) {
    console.log('[Content] Zep.us page detected');
    // 检查Zep.us页面的音频元素
    const audioElements = document.querySelectorAll('audio, video');
    console.log(`[Content] Found ${audioElements.length} audio/video elements in Zep.us`);
    
    // 检查是否在游戏房间页面
    if (location.pathname.includes('/play/')) {
      console.log('[Content] Zep.us game room detected:', location.pathname);
    }
  }
  
  // Google Meet特殊处理
  if (location.hostname.includes('meet.google.com')) {
    console.log('[Content] Google Meet page detected');
    // 检查Google Meet页面的音频元素
    const audioElements = document.querySelectorAll('audio, video');
    console.log(`[Content] Found ${audioElements.length} audio/video elements in Google Meet`);
    
    // 检查Meet相关元素
    const meetElements = document.querySelectorAll('[data-meeting-title], [jsname], .google-material-icons');
    console.log(`[Content] Found ${meetElements.length} Meet-specific elements`);
    
    // 检查会议状态
    const joinButton = document.querySelector('[aria-label*="join"], [aria-label*="Join"]');
    const leaveButton = document.querySelector('[aria-label*="leave"], [aria-label*="Leave"]');
    console.log('[Content] Meet status:', {
      hasJoinButton: !!joinButton,
      hasLeaveButton: !!leaveButton,
      inMeeting: !!leaveButton
    });
  }
}, 3000);

// 字幕系统状态管理
const containerId = "__gather_subtitles_container__";
const toggleButtonId = "__gather_subtitles_toggle__";
let container = document.getElementById(containerId);
let toggleButton = null;
let subtitlesVisible = localStorage.getItem('gather_subtitles_visible') !== 'false'; // 默认显示

function createSubtitleContainer() {
  console.log('[Content] Creating subtitle container...');
  
  if (container) {
    console.log('[Content] Container already exists, removing old one');
    container.remove();
  }
  
  container = document.createElement("div");
  container.id = containerId;
  container.style.cssText = `
    position: fixed !important;
    left: 50% !important;
    bottom: 8% !important;
    transform: translateX(-50%) !important;
    max-width: 70vw !important;
    max-height: 40vh !important;
    overflow-y: auto !important;
    font-family: system-ui, -apple-system, Segoe UI, Roboto, "PingFang SC", "Noto Sans CJK", Arial, sans-serif !important;
    z-index: 2147483647 !important;
    padding: 8px 12px !important;
    background: rgba(0,0,0,0.8) !important;
    border-radius: 10px !important;
    backdrop-filter: saturate(150%) blur(6px) !important;
    pointer-events: none !important;
    border: 2px solid rgba(255,255,255,0.1) !important;
    transition: opacity 0.3s ease !important;
    opacity: ${subtitlesVisible ? '1' : '0'} !important;
    display: ${subtitlesVisible ? 'block' : 'none'} !important;
  `;
  
  document.body.appendChild(container);
  console.log('[Content] ✅ Subtitle container created and added to body');
  console.log('[Content] Container element:', container);
  console.log('[Content] Container computed style:', getComputedStyle(container));
  
  return container;
}

// 创建字幕开关按钮
function createToggleButton() {
  console.log('[Content] Creating subtitle toggle button...');
  
  // 移除现有按钮
  if (toggleButton) {
    toggleButton.remove();
  }
  
  toggleButton = document.createElement("div");
  toggleButton.id = toggleButtonId;
  toggleButton.style.cssText = `
    position: fixed !important;
    right: 20px !important;
    bottom: 20px !important;
    width: 50px !important;
    height: 50px !important;
    background: rgba(0, 0, 0, 0.8) !important;
    border-radius: 25px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    cursor: pointer !important;
    z-index: 2147483648 !important;
    border: 2px solid rgba(255, 255, 255, 0.2) !important;
    backdrop-filter: saturate(150%) blur(6px) !important;
    transition: all 0.3s ease !important;
    font-size: 24px !important;
    user-select: none !important;
    pointer-events: auto !important;
  `;
  
  // 设置按钮图标和标题
  updateToggleButtonState();
  
  // 鼠标悬停效果
  toggleButton.addEventListener('mouseenter', () => {
    toggleButton.style.background = 'rgba(0, 0, 0, 0.9)';
    toggleButton.style.borderColor = 'rgba(255, 255, 255, 0.4)';
    toggleButton.style.transform = 'scale(1.1)';
  });
  
  toggleButton.addEventListener('mouseleave', () => {
    toggleButton.style.background = 'rgba(0, 0, 0, 0.8)';
    toggleButton.style.borderColor = 'rgba(255, 255, 255, 0.2)';
    toggleButton.style.transform = 'scale(1)';
  });
  
  // 点击事件
  toggleButton.addEventListener('click', toggleSubtitles);
  
  document.body.appendChild(toggleButton);
  console.log('[Content] ✅ Toggle button created and added to body');
  
  return toggleButton;
}

// 更新开关按钮状态
function updateToggleButtonState() {
  if (!toggleButton) return;
  
  if (subtitlesVisible) {
    toggleButton.innerHTML = '👁️';
    toggleButton.title = '点击隐藏字幕 (Ctrl+H)';
  } else {
    toggleButton.innerHTML = '👁️‍🗨️';
    toggleButton.title = '点击显示字幕 (Ctrl+H)';
  }
}

// 切换字幕显示状态
function toggleSubtitles() {
  subtitlesVisible = !subtitlesVisible;
  console.log(`[Content] 🔄 Toggling subtitles: ${subtitlesVisible ? 'visible' : 'hidden'}`);
  
  // 保存状态到 localStorage
  localStorage.setItem('gather_subtitles_visible', subtitlesVisible.toString());
  
  // 更新容器显示状态
  if (container) {
    if (subtitlesVisible) {
      container.style.display = 'block';
      container.style.opacity = '1';
    } else {
      container.style.opacity = '0';
      setTimeout(() => {
        if (!subtitlesVisible) { // 确认状态没有被再次改变
          container.style.display = 'none';
        }
      }, 300); // 等待淡出动画完成
    }
  }
  
  // 更新按钮状态
  updateToggleButtonState();
  
  console.log(`[Content] ✅ Subtitles ${subtitlesVisible ? 'shown' : 'hidden'}`);
}

// 添加键盘快捷键支持
document.addEventListener('keydown', (e) => {
  // Ctrl+H 或 Escape 切换字幕
  if ((e.ctrlKey && e.key === 'h') || e.key === 'Escape') {
    e.preventDefault();
    console.log('[Content] ⌨️ Keyboard shortcut triggered:', e.key);
    toggleSubtitles();
  }
});

// 初始化容器和按钮
createSubtitleContainer();
createToggleButton();

// YouTube和Google Meet特殊处理
if (location.hostname.includes('youtube.com') || location.hostname.includes('meet.google.com')) {
  const platform = location.hostname.includes('youtube.com') ? 'YouTube' : 'Google Meet';
  console.log(`[Content] 🎥 ${platform} page detected, adding special handling`);
  
  // 添加调试工具到window对象
  window.debugSubtitles = {
    testSubtitle: function(text = "测试字幕") {
      console.log('[Debug] Testing subtitle display...');
      renderLine({
        en: text,
        zh: text,
        isFinal: true
      });
    },
    
    showContainer: function() {
      console.log('[Debug] Container info:');
      console.log('Container element:', container);
      console.log('Container ID:', container ? container.id : 'NO CONTAINER');
      console.log('Container parent:', container ? container.parentNode : 'NO PARENT');
      console.log('Container children:', container ? container.children.length : 'NO CHILDREN');
      if (container) {
        const rect = container.getBoundingClientRect();
        console.log('Container position:', rect);
        console.log('Container styles:', getComputedStyle(container));
      }
      return container;
    },
    
    recreateContainer: function() {
      console.log('[Debug] Recreating container...');
      createSubtitleContainer();
      return container;
    },
    
    clearSubtitles: function() {
      if (container) {
        container.innerHTML = '';
        console.log('[Debug] Cleared all subtitles');
      }
    },
    
    // 新增调试工具
    checkConnection: async function() {
      console.log('[Debug] Checking background connection...');
      try {
        const response = await chrome.runtime.sendMessage({ type: "DEBUG_PING" });
        console.log('[Debug] Background response:', response);
        return response;
      } catch (error) {
        console.error('[Debug] Connection failed:', error);
        return { error: error.message };
      }
    },
    
    showStatus: function() {
      console.log('[Debug] Content Script Status:');
      console.log('- isActive:', isActive);
      console.log('- heartbeatInterval:', !!heartbeatInterval);
      console.log('- container exists:', !!container);
      console.log('- container in DOM:', container ? document.contains(container) : false);
      console.log('- page URL:', location.href);
      console.log('- page title:', document.title);
      return {
        isActive,
        hasHeartbeat: !!heartbeatInterval,
        hasContainer: !!container,
        containerInDOM: container ? document.contains(container) : false,
        url: location.href,
        title: document.title
      };
    },
    
    simulateMessage: function(text = "模拟中文字幕") {
      console.log('[Debug] Simulating background message...');
      const msg = {
        type: "SUBTITLE_UPDATE",
        payload: {
          en: "Simulated English text",
          zh: text,
          isFinal: true
        }
      };
      
      // 模拟消息处理
      try {
        renderLine(msg.payload);
        console.log('[Debug] ✅ Message simulation successful');
        return { success: true };
      } catch (error) {
        console.error('[Debug] ❌ Message simulation failed:', error);
        return { success: false, error: error.message };
      }
    },
    
    // 字幕开关相关调试工具
    toggleSubtitles: function() {
      console.log('[Debug] Toggling subtitles via debug tool');
      toggleSubtitles();
      return { 
        subtitlesVisible, 
        message: `Subtitles ${subtitlesVisible ? 'shown' : 'hidden'}` 
      };
    },
    
    showSubtitles: function() {
      console.log('[Debug] Showing subtitles via debug tool');
      if (!subtitlesVisible) {
        toggleSubtitles();
      }
      return { subtitlesVisible: true, message: 'Subtitles shown' };
    },
    
    hideSubtitles: function() {
      console.log('[Debug] Hiding subtitles via debug tool');
      if (subtitlesVisible) {
        toggleSubtitles();
      }
      return { subtitlesVisible: false, message: 'Subtitles hidden' };
    },
    
    getSubtitleState: function() {
      return {
        subtitlesVisible,
        containerExists: !!container,
        containerInDOM: container ? document.contains(container) : false,
        toggleButtonExists: !!toggleButton,
        toggleButtonInDOM: toggleButton ? document.contains(toggleButton) : false,
        localStorage: localStorage.getItem('gather_subtitles_visible')
      };
    }
  };
  
  // 在页面切换时重新初始化
  let lastUrl = location.href;
  const observer = new MutationObserver(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      console.log(`[Content] 🔄 ${platform} page changed, reinitializing subtitles`);
      setTimeout(() => {
        createSubtitleContainer();
        createToggleButton();
      }, 1000);
    }
  });
  
  observer.observe(document, { subtree: true, childList: true });
  console.log(`[Content] 👀 ${platform} navigation observer activated`);
  
  // 添加快捷键测试
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'T') {
      e.preventDefault();
      console.log(`[Content] 🧪 Testing subtitle with hotkey Ctrl+Shift+T on ${platform}`);
      window.debugSubtitles.testSubtitle();
    }
  });
  
  console.log('[Content] 💡 Debug tools available:');
  console.log('- window.debugSubtitles.testSubtitle() - Test subtitle display');
  console.log('- window.debugSubtitles.showContainer() - Show container info');  
  console.log('- window.debugSubtitles.recreateContainer() - Recreate container');
  console.log('- window.debugSubtitles.clearSubtitles() - Clear all subtitles');
  console.log('- window.debugSubtitles.checkConnection() - Check background connection');
  console.log('- window.debugSubtitles.showStatus() - Show content script status');
  console.log('- window.debugSubtitles.simulateMessage() - Simulate subtitle message');
  console.log('- window.debugSubtitles.toggleSubtitles() - Toggle subtitle visibility');
  console.log('- window.debugSubtitles.showSubtitles() - Force show subtitles');
  console.log('- window.debugSubtitles.hideSubtitles() - Force hide subtitles');
  console.log('- window.debugSubtitles.getSubtitleState() - Get subtitle system state');
  console.log('- Ctrl+Shift+T - Quick test subtitle');
  console.log('- Ctrl+H or Escape - Toggle subtitle visibility');
}

// 心跳状态
let heartbeatInterval = null;
let isActive = true;

// 启动心跳
function startHeartbeat() {
  if (heartbeatInterval) return;
  
  heartbeatInterval = setInterval(() => {
    if (isActive) {
      console.log('[Content] 💓 Heartbeat active');
    }
  }, 30000); // 每30秒心跳
  
  console.log('[Content] ❤️ Heartbeat started');
}

// 停止心跳
function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
    console.log('[Content] 💔 Heartbeat stopped');
  }
}

// 接收后台推送的字幕消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  console.log('[Content] 📨 Received message:', msg);
  
  if (msg.type === "PING") {
    console.log('[Content] 🏓 Received PING, sending PONG');
    sendResponse({ type: "PONG", status: "ready", timestamp: Date.now() });
    return true;
  }
  
  if (msg.type === "SUBTITLE_UPDATE") {
    console.log('[Content] 📝 Processing subtitle update:', msg.payload);
    try {
      renderLine(msg.payload);
      sendResponse({ success: true, timestamp: Date.now() });
      console.log('[Content] ✅ Subtitle rendered successfully');
    } catch (error) {
      console.error('[Content] ❌ Failed to render subtitle:', error);
      sendResponse({ success: false, error: error.message, timestamp: Date.now() });
    }
    return true;
  }
  
  // 其他消息类型
  sendResponse({ type: "unknown", message: "Unknown message type" });
  return true;
});

// 监听页面卸载
window.addEventListener('beforeunload', () => {
  console.log('[Content] 🚪 Page unloading, stopping heartbeat');
  isActive = false;
  stopHeartbeat();
});

// 启动心跳
startHeartbeat();

// 通知background script content script已就绪
console.log('[Content] 🚀 Content script initialized and ready');

function renderLine({ en, zh, isFinal }) {
  console.log('[Content] 🎨 Rendering subtitle line:', { en, zh, isFinal });
  
  if (!container) {
    console.warn('[Content] ⚠️ Container not found, recreating...');
    createSubtitleContainer();
  }
  
  // 如果字幕被隐藏，则不渲染新的字幕行
  if (!subtitlesVisible) {
    console.log('[Content] 🙈 Subtitles are hidden, skipping render');
    return;
  }
  
  // 添加测试可见性
  const line = document.createElement("div");
  line.className = "subtitle-line" + (isFinal ? " final" : "");
  line.style.cssText = `
    margin: 6px 0 !important;
    line-height: 1.3 !important;
    color: #fff !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.7) !important;
    background: rgba(255,0,0,0.2) !important;
    padding: 4px !important;
    border-radius: 4px !important;
  `;
  
  // 只显示中文字幕，不显示英文
  line.innerHTML = `
    <div class="zh" style="font-size: 20px !important; font-weight: 600 !important; margin: 0 !important; line-height: 1.4 !important; text-align: center !important;">${escapeHtml(zh || en || "")}</div>
  `;
  
  container.appendChild(line);
  container.scrollTop = container.scrollHeight;
  
  console.log('[Content] 📍 Subtitle line added to container');
  console.log('[Content] Container children count:', container.children.length);
  console.log('[Content] Container visibility:', getComputedStyle(container).visibility);
  console.log('[Content] Container display:', getComputedStyle(container).display);
  
  // 临时字幕自动消失
  if (!isFinal) {
    setTimeout(() => {
      if (line.parentNode) {
        line.remove();
        console.log('[Content] 🗑️ Temporary subtitle removed');
      }
    }, 8000);
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}
