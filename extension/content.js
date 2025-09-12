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
    bottom: 3% !important;
    transform: translateX(-50%) !important;
    max-width: 55vw !important;
    max-height: 20vh !important;
    overflow-y: auto !important;
    scroll-behavior: smooth !important;
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
    /* 自定义滚动条 */
    scrollbar-width: thin !important;
    scrollbar-color: rgba(255, 255, 255, 0.4) rgba(255, 255, 255, 0.1) !important;
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
      // 清理新的字幕状态
      if (currentSubtitle) {
        currentSubtitle = null;
      }
      if (subtitleTimeout) {
        clearTimeout(subtitleTimeout);
        subtitleTimeout = null;
      }
      lastSubtitleText = '';
      lastPartialText = '';
      currentPartialSubtitle = null;
      subtitleHistory = []; // 清空历史缓存
      console.log('[Debug] Cleared subtitle state variables and history');
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
        localStorage: localStorage.getItem('gather_subtitles_visible'),
        // 新增状态信息
        currentSubtitle: !!currentSubtitle,
        lastSubtitleText: lastSubtitleText,
        hasTimeout: !!subtitleTimeout,
        containerChildrenCount: container ? container.children.length : 0,
        subtitleHistoryCount: subtitleHistory.length,
        subtitleHistory: subtitleHistory.map(s => s.text.substring(0, 30) + '...')
      };
    },
    
    // 新增：测试单一字幕显示
    testSingleSubtitle: function(text = "单一字幕测试") {
      console.log('[Debug] Testing single subtitle display...');
      renderLine({
        en: "Single subtitle test",
        zh: text,
        isFinal: true
      });
      return { success: true, message: `Displayed: ${text}` };
    },
    
    // 新增：连续测试多条字幕（现在会显示历史缓存）
    testMultipleSubtitles: function() {
      console.log('[Debug] Testing multiple subtitles with history cache...');
      const subtitles = [
        "第一条字幕测试 - 历史最旧",
        "第二条字幕测试 - 历史中间", 
        "第三条字幕测试 - 当前最新",
        "第四条字幕测试 - 新的当前",
        "第五条字幕测试 - 最终当前"
      ];
      
      subtitles.forEach((text, index) => {
        setTimeout(() => {
          renderLine({
            en: `Test subtitle ${index + 1}`,
            zh: text,
            isFinal: true
          });
          console.log(`[Debug] Displayed subtitle ${index + 1}: ${text}`);
          console.log(`[Debug] History now has ${subtitleHistory.length} items`);
        }, index * 3000); // 3秒间隔，给更多时间观察
      });
      
      return { success: true, message: `Will display ${subtitles.length} subtitles with 3s interval, showing history cache` };
    },
    
    // 新增：测试字幕历史功能
    testSubtitleHistory: function() {
      console.log('[Debug] Testing subtitle history functionality...');
      
      // 清空当前历史
      subtitleHistory = [];
      if (container) container.innerHTML = '';
      
      // 快速添加3条字幕来测试历史显示
      const testSubtitles = [
        "第一条字幕 - 最旧历史",
        "第二条字幕 - 中间历史",
        "第三条字幕 - 当前最新"
      ];
      
      testSubtitles.forEach((text, index) => {
        setTimeout(() => {
          renderLine({
            en: `History test ${index + 1}`,
            zh: text,
            isFinal: true
          });
        }, index * 1000); // 1秒间隔
      });
      
      return { success: true, message: "Testing 3-subtitle history display" };
    },
    
    // 新增：显示当前字幕历史状态
    getSubtitleHistory: function() {
      console.log('[Debug] Current subtitle history:');
      subtitleHistory.forEach((subtitle, index) => {
        console.log(`${index + 1}. ${subtitle.text} (${new Date(subtitle.timestamp).toLocaleTimeString()})`);
      });
      return {
        count: subtitleHistory.length,
        history: subtitleHistory,
        maxSize: 3
      };
    },
    
    // 新增：清空字幕历史
    clearSubtitleHistory: function() {
      console.log('[Debug] Clearing subtitle history...');
      subtitleHistory = [];
      if (container) container.innerHTML = '';
      lastSubtitleText = '';
      lastPartialText = '';
      currentPartialSubtitle = null;
      return { success: true, message: 'Subtitle history cleared' };
    },
    
    // 新增：测试部分结果显示
    testPartialResults: function() {
      console.log('[Debug] Testing partial results display...');
      
      const testSequence = [
        { text: "Hello wo", isFinal: false, delay: 0 },
        { text: "Hello world", isFinal: false, delay: 1000 },
        { text: "Hello world how", isFinal: false, delay: 2000 },
        { text: "Hello world how are", isFinal: false, delay: 3000 },
        { text: "Hello world how are you", isFinal: true, delay: 4000 }
      ];
      
      testSequence.forEach((item, index) => {
        setTimeout(() => {
          renderLine({
            en: item.text,
            zh: item.text + " (测试)",
            isFinal: item.isFinal
          });
          console.log(`[Debug] ${item.isFinal ? 'Final' : 'Partial'}: "${item.text}"`);
        }, item.delay);
      });
      
      return { success: true, message: 'Testing partial->final sequence over 5 seconds' };
    },
    
    // 新增：测试多轮部分结果
    testMultiplePartialSequences: function() {
      console.log('[Debug] Testing multiple partial sequences...');
      
      const sequences = [
        [
          { text: "第一句开始", isFinal: false, delay: 0 },
          { text: "第一句开始了", isFinal: false, delay: 500 },
          { text: "第一句开始了测试", isFinal: true, delay: 1000 }
        ],
        [
          { text: "第二句正在", isFinal: false, delay: 2000 },
          { text: "第二句正在进行", isFinal: false, delay: 2500 },
          { text: "第二句正在进行中", isFinal: true, delay: 3000 }
        ],
        [
          { text: "第三句最后", isFinal: false, delay: 4000 },
          { text: "第三句最后的", isFinal: false, delay: 4500 },
          { text: "第三句最后的测试", isFinal: true, delay: 5000 }
        ]
      ];
      
      sequences.forEach((sequence, seqIndex) => {
        sequence.forEach((item, itemIndex) => {
          setTimeout(() => {
            renderLine({
              en: `Sequence ${seqIndex + 1}`,
              zh: item.text,
              isFinal: item.isFinal
            });
            console.log(`[Debug] Seq${seqIndex + 1} ${item.isFinal ? 'Final' : 'Partial'}: "${item.text}"`);
          }, item.delay);
        });
      });
      
      return { success: true, message: 'Testing 3 sequences of partial->final over 6 seconds' };
    },
    
    // 新增：获取当前字幕状态（包括部分结果）
    getCurrentSubtitleState: function() {
      console.log('[Debug] Current subtitle state:');
      console.log('- History count:', subtitleHistory.length);
      console.log('- Last final text:', lastSubtitleText);
      console.log('- Last partial text:', lastPartialText);
      console.log('- Has partial subtitle:', !!currentPartialSubtitle);
      
      return {
        historyCount: subtitleHistory.length,
        history: subtitleHistory.map(s => ({ text: s.text.substring(0, 30), isFinal: s.isFinal })),
        lastFinalText: lastSubtitleText,
        lastPartialText: lastPartialText,
        hasPartialSubtitle: !!currentPartialSubtitle,
        containerChildren: container ? container.children.length : 0
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
  
  console.log('[Content] 💡 Debug tools available (with partial results support):');
  console.log('- window.debugSubtitles.testSubtitle() - Test subtitle display');
  console.log('- window.debugSubtitles.testSingleSubtitle() - Test single subtitle');
  console.log('- window.debugSubtitles.testMultipleSubtitles() - Test multiple subtitles with history cache');
  console.log('- window.debugSubtitles.testSubtitleHistory() - Test 3-subtitle history display');
  console.log('- window.debugSubtitles.testPartialResults() - Test partial->final sequence (NEW)');
  console.log('- window.debugSubtitles.testMultiplePartialSequences() - Test multiple partial sequences (NEW)');
  console.log('- window.debugSubtitles.getSubtitleHistory() - Show current subtitle history');
  console.log('- window.debugSubtitles.getCurrentSubtitleState() - Get current state including partials (NEW)');
  console.log('- window.debugSubtitles.clearSubtitleHistory() - Clear subtitle history');
  console.log('- window.debugSubtitles.showContainer() - Show container info');  
  console.log('- window.debugSubtitles.recreateContainer() - Recreate container');
  console.log('- window.debugSubtitles.clearSubtitles() - Clear all subtitles');
  console.log('- window.debugSubtitles.checkConnection() - Check background connection');
  console.log('- window.debugSubtitles.showStatus() - Show content script status');
  console.log('- window.debugSubtitles.simulateMessage() - Simulate subtitle message');
  console.log('- window.debugSubtitles.toggleSubtitles() - Toggle subtitle visibility');
  console.log('- window.debugSubtitles.showSubtitles() - Force show subtitles');
  console.log('- window.debugSubtitles.hideSubtitles() - Force hide subtitles');
  console.log('- window.debugSubtitles.getSubtitleState() - Get subtitle system state (with history)');
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

// 用于记录字幕状态和历史缓存
let currentSubtitle = null;
let subtitleTimeout = null;
let lastSubtitleText = '';
let subtitleHistory = []; // 缓存最近3条 isFinal=true 的字幕
let currentPartialSubtitle = null; // 当前显示的部分结果
let lastPartialText = ''; // 最后的部分结果文本

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
  
  const subtitleText = zh || en || "";
  
  if (isFinal) {
    // 处理最终结果
    console.log('[Content] ✅ Processing final result:', subtitleText.substring(0, 30));
    
    // 防止重复显示相同内容
    if (subtitleText === lastSubtitleText) {
      console.log('[Content] 🔄 Skipping duplicate final subtitle:', subtitleText);
      return;
    }
    
    // 添加到历史缓存
    subtitleHistory.push({
      text: subtitleText,
      timestamp: Date.now(),
      en: en || "",
      zh: zh || "",
      isFinal: true
    });
    
    // 保持历史缓存最多3条
    if (subtitleHistory.length > 3) {
      subtitleHistory.shift(); // 移除最旧的
    }
    
    console.log(`[Content] 📚 Updated subtitle history (${subtitleHistory.length}/3):`, 
                subtitleHistory.map(s => s.text.substring(0, 20) + '...'));
    
    // 清除当前的部分结果
    currentPartialSubtitle = null;
    lastPartialText = '';
    
    // 更新状态
    lastSubtitleText = subtitleText;
    
  } else {
    // 处理部分结果
    console.log('[Content] ⏳ Processing partial result:', subtitleText.substring(0, 30));
    
    // 防止重复显示相同的部分结果
    if (subtitleText === lastPartialText) {
      console.log('[Content] 🔄 Skipping duplicate partial subtitle:', subtitleText);
      return;
    }
    
    // 更新部分结果状态
    lastPartialText = subtitleText;
  }
  
  // 清除现有的定时器
  if (subtitleTimeout) {
    clearTimeout(subtitleTimeout);
  }
  
  // 渲染所有字幕（历史 + 当前）
  renderSubtitlesWithCurrent(subtitleText, isFinal);
  
  // 自动滚动到底部显示最新内容 - 改进版本
  if (container) {
    setTimeout(() => {
      // 检查是否需要滚动指示器
      const isScrollable = container.scrollHeight > container.clientHeight;
      if (isScrollable) {
        container.classList.add('scrollable');
      } else {
        container.classList.remove('scrollable');
      }
      
      // 平滑滚动到底部
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
      console.log(`[Content] 📜 Auto-scrolled to bottom - scrollHeight: ${container.scrollHeight}, clientHeight: ${container.clientHeight}, scrollable: ${isScrollable}`);
    }, 50); // 短暂延迟确保内容已渲染
  }
  
  console.log(`[Content] 📍 Rendered subtitles - Final: ${isFinal}, Current: ${subtitleText.substring(0, 50)}`);
  
  // 设置字幕自动消失（15秒后）
  subtitleTimeout = setTimeout(() => {
    clearAllSubtitles();
  }, 15000);
}

// 新函数：渲染字幕历史和当前字幕
function renderSubtitlesWithCurrent(currentText, isFinal) {
  if (!container) return;
  
  // 清空容器
  container.innerHTML = '';
  
  // 1. 渲染历史字幕（只显示前面的，不包括最新的最终结果）
  const displayHistory = isFinal ? subtitleHistory.slice(0, -1) : subtitleHistory;
  
  displayHistory.forEach((subtitle, index) => {
    const line = document.createElement("div");
    const isOldest = index === 0 && displayHistory.length > 1;
    
    // 历史字幕样式
    let opacity, fontSize, fontWeight;
    if (displayHistory.length === 1) {
      opacity = '0.8';
      fontSize = '18px';
      fontWeight = '450';
    } else if (isOldest) {
      opacity = '0.6';
      fontSize = '16px';
      fontWeight = '400';
    } else {
      opacity = '0.8';
      fontSize = '18px';
      fontWeight = '450';
    }
    
    line.className = `subtitle-line history ${isOldest ? 'first' : ''}`;
    line.style.cssText = `
      margin: 2px 0 !important;
      line-height: 1.3 !important;
      color: #fff !important;
      text-shadow: 0 1px 2px rgba(0,0,0,0.7) !important;
      background: rgba(0,0,0,${isOldest ? '0.4' : '0.5'}) !important;
      padding: ${isOldest ? '4px 8px' : '6px 10px'} !important;
      border-radius: 8px !important;
      border: 1px solid rgba(255,255,255,0.08) !important;
      opacity: ${opacity} !important;
      transition: all 0.3s ease !important;
    `;
    
    line.innerHTML = `
      <div class="zh" style="
        font-size: ${fontSize} !important; 
        font-weight: ${fontWeight} !important; 
        margin: 0 !important; 
        line-height: 1.5 !important; 
        text-align: center !important; 
        letter-spacing: 0.5px !important;
        color: rgba(255,255,255,0.9) !important;
      ">${escapeHtml(subtitle.text)}</div>
    `;
    
    container.appendChild(line);
  });
  
  // 2. 渲染当前字幕（最终结果或部分结果）
  if (currentText && currentText.trim()) {
    const currentLine = document.createElement("div");
    const isPartial = !isFinal;
    
    currentLine.className = `subtitle-line ${isPartial ? 'partial' : 'current'}`;
    currentLine.style.cssText = `
      margin: ${isPartial ? '4px 0' : '8px 0'} !important;
      line-height: 1.3 !important;
      color: #fff !important;
      text-shadow: 0 1px 2px rgba(0,0,0,0.7) !important;
      background: rgba(0,0,0,${isPartial ? '0.65' : '0.7'}) !important;
      padding: ${isPartial ? '8px 12px' : '12px 16px'} !important;
      border-radius: 8px !important;
      border: ${isPartial ? '2px dashed rgba(255,255,255,0.3)' : '1px solid rgba(255,255,255,0.15)'} !important;
      opacity: 1 !important;
      animation: ${isPartial ? 'pulse 1.5s ease-in-out infinite alternate' : 'fadeIn 0.3s ease-in'} !important;
      transition: all 0.3s ease !important;
      box-shadow: ${isPartial ? '0 0 10px rgba(255,255,255,0.1)' : '0 2px 8px rgba(0,0,0,0.3)'} !important;
    `;
    
    currentLine.innerHTML = `
      <div class="zh" style="
        font-size: 22px !important; 
        font-weight: ${isPartial ? '500' : '600'} !important; 
        margin: 0 !important; 
        line-height: 1.5 !important; 
        text-align: center !important; 
        letter-spacing: 0.5px !important;
        color: ${isPartial ? 'rgba(255,255,255,0.95)' : '#fff'} !important;
      ">${escapeHtml(currentText)}</div>
    `;
    
    container.appendChild(currentLine);
    currentPartialSubtitle = currentLine;
  }
}

// 保留原有的渲染函数作为备用
function renderSubtitleHistory() {
  if (!container) return;
  
  // 清空容器
  container.innerHTML = '';
  
  // 渲染所有历史字幕
  subtitleHistory.forEach((subtitle, index) => {
    const line = document.createElement("div");
    const isLatest = index === subtitleHistory.length - 1;
    const isFirst = index === 0;
    
    // 根据位置设置不同的样式
    let opacity, fontSize, fontWeight;
    if (subtitleHistory.length === 1) {
      // 只有一条字幕
      opacity = '1';
      fontSize = '22px';
      fontWeight = '500';
    } else if (isLatest) {
      // 最新字幕 - 高亮显示
      opacity = '1';
      fontSize = '22px';
      fontWeight = '600';
    } else if (subtitleHistory.length === 3 && isFirst) {
      // 最旧字幕 - 较暗
      opacity = '0.6';
      fontSize = '18px';
      fontWeight = '400';
    } else {
      // 中间字幕
      opacity = '0.8';
      fontSize = '20px';
      fontWeight = '450';
    }
    
    line.className = `subtitle-line ${isLatest ? 'current' : 'history'}`;
    line.style.cssText = `
      margin: ${isLatest ? '8px 0' : '4px 0'} !important;
      line-height: 1.3 !important;
      color: #fff !important;
      text-shadow: 0 1px 2px rgba(0,0,0,0.7) !important;
      background: rgba(0,0,0,${isLatest ? '0.7' : '0.5'}) !important;
      padding: ${isLatest ? '12px 16px' : '8px 12px'} !important;
      border-radius: 8px !important;
      border: 1px solid rgba(255,255,255,${isLatest ? '0.15' : '0.08'}) !important;
      opacity: ${opacity} !important;
      animation: ${isLatest ? 'fadeIn 0.3s ease-in' : 'none'} !important;
      transition: all 0.3s ease !important;
    `;
    
    // 显示字幕文本
    line.innerHTML = `
      <div class="zh" style="
        font-size: ${fontSize} !important; 
        font-weight: ${fontWeight} !important; 
        margin: 0 !important; 
        line-height: 1.5 !important; 
        text-align: center !important; 
        letter-spacing: 0.5px !important;
        color: ${isLatest ? '#fff' : 'rgba(255,255,255,0.9)'} !important;
      ">${escapeHtml(subtitle.text)}</div>
    `;
    
    container.appendChild(line);
  });
}

// 新函数：清空所有字幕
function clearAllSubtitles() {
  if (container) {
    // 添加淡出动画
    const lines = container.querySelectorAll('.subtitle-line');
    lines.forEach(line => {
      line.style.animation = 'fadeOut 0.3s ease-out';
    });
    
    setTimeout(() => {
      container.innerHTML = '';
      console.log('[Content] 🗑️ All subtitles auto-removed after timeout');
    }, 300);
  }
  
  // 清理所有状态
  currentSubtitle = null;
  currentPartialSubtitle = null;
  lastSubtitleText = '';
  lastPartialText = '';
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
}
