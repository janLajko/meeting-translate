let ws = null;
let audioCtx, workletNode;

// 辅助函数：发送日志到background
function sendLog(level, message, data = null) {
  console.log(`[Offscreen] ${message}`, data || '');
  chrome.runtime.sendMessage({ 
    type: 'OFFSCREEN_LOG', 
    level, 
    message,
    data: data ? JSON.stringify(data) : null
  });
}

chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  sendLog('info', 'Received message:', message);
  
  if (message.type === 'START_CAPTURE') {
    try {
      sendLog('info', 'Starting audio capture with streamId:', message.streamId);
      
      // 检查navigator.mediaDevices支持
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('getUserMedia not supported');
      }
      sendLog('info', 'getUserMedia is supported');
      
      const constraints = {
        audio: {
          mandatory: {
            chromeMediaSource: 'tab',
            chromeMediaSourceId: message.streamId
          }
        }
      };
      sendLog('info', 'Attempting getUserMedia with constraints:', constraints);
      
      // 获取音频流
      const audioStream = await navigator.mediaDevices.getUserMedia(constraints);
      sendLog('success', 'Audio capture successful!');
      
      const audioTracks = audioStream.getAudioTracks();
      sendLog('info', `Got ${audioTracks.length} audio tracks`);
      if (audioTracks.length > 0) {
        sendLog('info', 'First audio track settings:', audioTracks[0].getSettings());
      }
      
      // 连接WebSocket - 支持本地和Cloud Run部署
      const wsUrl = location.hostname === 'localhost' 
        ? "ws://localhost:8080/stream"
        : "wss://meeting-translate-1019079553349.asia-east2.run.app/stream";
      sendLog('info', 'Connecting to WebSocket:', wsUrl);
      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      
      ws.onopen = async () => {
        sendLog('success', 'WebSocket connected successfully!');
        
        try {
          sendLog('info', 'Creating AudioContext...');
          audioCtx = new AudioContext({ sampleRate: 48000 });
          sendLog('info', 'AudioContext created, state:', audioCtx.state);
          
          sendLog('info', 'Loading AudioWorklet module...');
          const workletUrl = chrome.runtime.getURL('pcm-worklet.js');
          sendLog('info', 'AudioWorklet URL:', workletUrl);
          await audioCtx.audioWorklet.addModule(workletUrl);
          sendLog('success', 'AudioWorklet module loaded successfully');
          
          sendLog('info', 'Creating audio processing pipeline...');
          const src = audioCtx.createMediaStreamSource(audioStream);
          workletNode = new AudioWorkletNode(audioCtx, "pcm16k-writer");
          
          let audioDataCount = 0;
          workletNode.port.onmessage = (e) => {
            audioDataCount++;
            if (audioDataCount <= 5 || audioDataCount % 50 === 0) {
              sendLog('info', `Sending audio data #${audioDataCount}, size: ${e.data.byteLength} bytes`);
            }
            if (ws && ws.readyState === 1) {
              ws.send(e.data);
            } else {
              sendLog('warn', 'WebSocket not ready, readyState:', ws?.readyState);
            }
          };
          
          src.connect(workletNode).connect(audioCtx.destination);
          sendLog('success', 'Audio pipeline connected successfully!');
          
          // 通知background script启动成功
          sendLog('info', 'Sending CAPTURE_STARTED message');
          chrome.runtime.sendMessage({ type: 'CAPTURE_STARTED' });
          
        } catch (audioError) {
          sendLog('error', 'Audio setup failed:', audioError.message);
          chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: audioError.message });
        }
      };
      
      ws.onmessage = (evt) => {
        sendLog('info', 'Received message from server:', evt.data);
        // 转发到background script
        chrome.runtime.sendMessage({ 
          type: 'SUBTITLE_DATA', 
          data: evt.data, 
          tabId: message.tabId 
        });
      };
      
      ws.onclose = (evt) => {
        sendLog('warn', 'WebSocket closed, code:', evt.code, 'reason:', evt.reason);
        chrome.runtime.sendMessage({ type: 'CAPTURE_STOPPED' });
      };
      
      ws.onerror = (error) => {
        sendLog('error', 'WebSocket error:', error);
        chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: 'WebSocket connection failed' });
      };
      
    } catch (error) {
      sendLog('error', 'Failed to start capture:', error.message);
      chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: error.message });
    }
  } else if (message.type === 'STOP_CAPTURE') {
    console.log('[Offscreen] Stopping capture');
    if (workletNode) {
      workletNode.disconnect();
      workletNode = null;
    }
    if (audioCtx) {
      await audioCtx.close();
      audioCtx = null;
    }
    if (ws) {
      ws.close();
      ws = null;
    }
  }
});