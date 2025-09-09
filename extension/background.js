let portOpen = false;
let currentTabId = null;

// 点击扩展图标启停
chrome.action.onClicked.addListener(async (tab) => {
  console.log('[Background] Icon clicked, tab URL:', tab.url);
  if (!/gather\.town/.test(tab.url)) {
    console.log('[Background] Not a Gather.town page, ignoring');
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

async function start(tabId) {
  console.log('[Background] Starting capture for tab:', tabId);
  
  try {
    // 获取stream ID
    const streamId = await chrome.tabCapture.getMediaStreamId({
      targetTabId: tabId
    });
    console.log('[Background] Got stream ID:', streamId);
    
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
    console.log('[Background] 📝 Received subtitle data');
    if (currentTabId) {
      try {
        const data = JSON.parse(message.data);
        chrome.tabs.sendMessage(currentTabId, { 
          type: "SUBTITLE_UPDATE", 
          payload: data 
        });
      } catch (error) {
        console.error('[Background] Failed to parse subtitle data:', error);
      }
    }
  }
});