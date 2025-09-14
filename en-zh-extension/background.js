let portOpen = false;
let currentTabId = null;
let contentScriptReady = false;
let messageQueue = []; // 缓存等待发送的字幕消息

// 点击扩展图标启停
chrome.action.onClicked.addListener(async (tab) => {
  console.log('[Background] Icon clicked, tab URL:', tab.url);
  
  // 支持Gather.town、YouTube、Zep.us和Google Meet
  const supportedSites = /gather\.town|youtube\.com|youtu\.be|zep\.us|meet\.google\.com/;
  if (!supportedSites.test(tab.url)) {
    console.log('[Background] Not a supported page, ignoring');
    console.log('[Background] Supported: Gather.town, YouTube, Zep.us, Google Meet');
    return;
  }
  if (!portOpen) {
    console.log('[Background] Starting capture...');
    await start(tab.id);
  } else {
    console.log('[Background] Stopping capture...');
    await stop();
  }
});

// 检查content script是否就绪
async function checkContentScript(tabId) {
  console.log('[Background] Checking content script readiness for tab:', tabId);
  
  try {
    const response = await chrome.tabs.sendMessage(tabId, { 
      type: "PING" 
    });
    
    if (response && response.type === "PONG") {
      console.log('[Background] ✅ Content script is ready');
      contentScriptReady = true;
      return true;
    }
  } catch (error) {
    console.log('[Background] ❌ Content script not ready:', error.message);
    contentScriptReady = false;
  }
  
  return false;
}

// 注入content script
async function injectContentScript(tabId) {
  console.log('[Background] Injecting content script into tab:', tabId);
  
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tabId },
      files: ['content.js']
    });
    
    // 等待一秒让content script初始化
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    const isReady = await checkContentScript(tabId);
    if (isReady) {
      console.log('[Background] ✅ Content script injected and ready');
      return true;
    }
  } catch (error) {
    console.error('[Background] ❌ Failed to inject content script:', error);
  }
  
  return false;
}

async function start(tabId) {
  console.log('[Background] Starting capture for tab:', tabId);
  
  try {
    // 首先检查标签页的URL和状态
    const tab = await chrome.tabs.get(tabId);
    console.log('[Background] Tab info:', {
      url: tab.url,
      audible: tab.audible,
      mutedInfo: tab.mutedInfo,
      status: tab.status
    });
    
    // 检查并确保content script就绪
    console.log('[Background] 🔍 Ensuring content script is ready...');
    let isContentReady = await checkContentScript(tabId);
    
    if (!isContentReady) {
      console.log('[Background] 💉 Content script not ready, attempting injection...');
      isContentReady = await injectContentScript(tabId);
      
      if (!isContentReady) {
        console.error('[Background] ❌ Failed to prepare content script');
        chrome.action.setBadgeText({ text: "ERR" });
        chrome.action.setBadgeBackgroundColor({ color: "#d73a49" });
        return;
      }
    }
    
    // 获取stream ID
    const streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tabId
    });
    console.log('[Background] Got stream ID:', streamId);
    
    // 先尝试关闭现有的 offscreen document（如果存在）
    try {
      await chrome.offscreen.closeDocument();
      console.log('[Background] Closed existing offscreen document');
    } catch (error) {
      // 如果没有现有的 document，这个错误是预期的
      console.log('[Background] No existing offscreen document to close');
    }
    
    // 创建offscreen document
    await chrome.offscreen.createDocument({
      url: 'offscreen.html',
      reasons: ['USER_MEDIA'],
      justification: 'Capture and process audio for real-time translation'
    });
    console.log('[Background] Offscreen document created');
    
    // 发送消息到offscreen document开始捕获
    chrome.runtime.sendMessage({
      type: 'START_CAPTURE',
      streamId: streamId,
      tabId: tabId
    });
    
    currentTabId = tabId;
    
  } catch (error) {
    console.error('[Background] Failed to start capture:', error);
  }
}

// 发送字幕消息到content script
async function sendSubtitleMessage(data) {
  console.log('[Background] 📤 Preparing to send subtitle:', data);
  
  if (!currentTabId) {
    console.warn('[Background] ⚠️ No current tab ID, caching message');
    messageQueue.push(data);
    return;
  }
  
  if (!contentScriptReady) {
    console.log('[Background] 📦 Content script not ready, checking and caching message');
    messageQueue.push(data);
    
    // 尝试重新建立连接
    const isReady = await checkContentScript(currentTabId);
    if (isReady) {
      console.log('[Background] 🔄 Content script reconnected, processing queue');
      await processMessageQueue();
    }
    return;
  }
  
  try {
    await chrome.tabs.sendMessage(currentTabId, { 
      type: "SUBTITLE_UPDATE", 
      payload: data 
    });
    console.log('[Background] ✅ Subtitle message sent successfully');
  } catch (error) {
    console.error('[Background] ❌ Failed to send subtitle message:', error);
    console.error('[Background] Tab ID:', currentTabId);
    
    // 标记content script为未就绪
    contentScriptReady = false;
    
    // 缓存消息并尝试重新建立连接
    messageQueue.push(data);
    console.log('[Background] 📦 Message cached, attempting reconnection...');
    
    setTimeout(async () => {
      if (await checkContentScript(currentTabId) || await injectContentScript(currentTabId)) {
        await processMessageQueue();
      }
    }, 1000);
  }
}

// 处理消息队列
async function processMessageQueue() {
  if (messageQueue.length === 0 || !contentScriptReady) return;
  
  console.log('[Background] 🔄 Processing message queue, items:', messageQueue.length);
  
  const queue = [...messageQueue]; // 创建副本
  messageQueue = []; // 清空队列
  
  for (const data of queue) {
    try {
      await chrome.tabs.sendMessage(currentTabId, { 
        type: "SUBTITLE_UPDATE", 
        payload: data 
      });
      console.log('[Background] ✅ Queued message sent:', data.en?.substring(0, 30) + '...');
    } catch (error) {
      console.error('[Background] ❌ Failed to send queued message:', error);
      // 重新添加到队列
      messageQueue.unshift(data);
      break;
    }
  }
}

async function stop() {
  console.log('[Background] Stopping capture');
  
  try {
    // 发送停止消息
    chrome.runtime.sendMessage({
      type: 'STOP_CAPTURE'
    });
    
    // 关闭offscreen document
    await chrome.offscreen.closeDocument();
    console.log('[Background] Offscreen document closed');
    
  } catch (error) {
    console.error('[Background] Error during stop:', error);
  }
  
  portOpen = false;
  currentTabId = null;
  contentScriptReady = false;
  messageQueue = []; // 清空消息队列
  chrome.action.setBadgeText({ text: "" });
}

// 处理来自offscreen document的消息
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'OFFSCREEN_LOG') {
    // 显示来自offscreen的日志
    const logPrefix = `[Background->Offscreen] [${message.level.toUpperCase()}]`;
    if (message.level === 'error') {
      console.error(logPrefix, message.message, message.data || '');
    } else if (message.level === 'warn') {
      console.warn(logPrefix, message.message, message.data || '');
    } else if (message.level === 'success') {
      console.log(`%c${logPrefix} ${message.message}`, 'color: green', message.data || '');
    } else {
      console.log(logPrefix, message.message, message.data || '');
    }
    return;
  }
  
  console.log('[Background] Received message:', message);
  
  if (message.type === 'CAPTURE_STARTED') {
    console.log('[Background] ✅ Capture started successfully!');
    portOpen = true;
    chrome.action.setBadgeText({ text: "ON" });
    chrome.action.setBadgeBackgroundColor({ color: "#2ea043" });
  } else if (message.type === 'CAPTURE_STOPPED') {
    console.log('[Background] ⚠️ Capture stopped');
    portOpen = false;
    chrome.action.setBadgeText({ text: "" });
  } else if (message.type === 'CAPTURE_ERROR') {
    console.error('[Background] ❌ Capture error:', message.error);
    portOpen = false;
    chrome.action.setBadgeText({ text: "ERR" });
    chrome.action.setBadgeBackgroundColor({ color: "#d73a49" });
  } else if (message.type === 'SUBTITLE_DATA') {
    // 转发字幕数据到content script
    console.log('[Background] 📝 Received subtitle data:', message.data);
    
    try {
      const data = JSON.parse(message.data);
      sendSubtitleMessage(data);
    } catch (error) {
      console.error('[Background] ❌ Failed to parse subtitle data:', error);
      console.error('[Background] Raw data:', message.data);
    }
  } else if (message.type === 'DEBUG_PING') {
    // 处理来自content script的调试ping
    console.log('[Background] 🐛 Received debug ping from content script');
    return Promise.resolve({
      type: 'DEBUG_PONG',
      status: 'background_ready',
      currentTabId: currentTabId,
      contentScriptReady: contentScriptReady,
      portOpen: portOpen,
      messageQueueLength: messageQueue.length,
      timestamp: Date.now()
    });
  }
});