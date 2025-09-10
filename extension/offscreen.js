let ws = null;
let audioCtx, workletNode;
let reconnectTimer = null;
let reconnectAttempts = 0;
let maxReconnectAttempts = 10;
let reconnectDelay = 1000; // 开始1秒
let audioBuffer = []; // 音频数据缓冲
let maxBufferSize = 100; // 最大缓冲100个音频块
let heartbeatTimer = null;
let wsUrl = null;
let currentStreamId = null;

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

// WebSocket连接管理
function connectWebSocket() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    sendLog('warn', 'WebSocket already connecting or connected');
    return;
  }
  
  sendLog('info', `Connecting to WebSocket (attempt ${reconnectAttempts + 1}): ${wsUrl}`);
  
  try {
    ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    
    ws.onopen = () => {
      sendLog('success', 'WebSocket connected successfully!');
      reconnectAttempts = 0;
      reconnectDelay = 1000;
      
      // 清空重连定时器
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      
      // 开始心跳
      startHeartbeat();
      
      // 发送缓冲的音频数据
      flushAudioBuffer();
      
      chrome.runtime.sendMessage({ type: 'CAPTURE_STARTED' });
    };
    
    ws.onmessage = (evt) => {
      if (evt.data === 'PONG') {
        sendLog('info', 'Received heartbeat PONG');
        return;
      }
      
      sendLog('info', 'Received message from server:', evt.data);
      chrome.runtime.sendMessage({ 
        type: 'SUBTITLE_DATA', 
        data: evt.data, 
        tabId: currentStreamId 
      });
    };
    
    ws.onclose = (evt) => {
      sendLog('warn', `WebSocket closed, code: ${evt.code}, reason: ${evt.reason}`);
      stopHeartbeat();
      
      if (evt.code !== 1000) { // 非正常关闭才重连
        scheduleReconnect();
      } else {
        chrome.runtime.sendMessage({ type: 'CAPTURE_STOPPED' });
      }
    };
    
    ws.onerror = (error) => {
      sendLog('error', 'WebSocket error:', error);
      chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: 'WebSocket connection failed' });
    };
    
  } catch (error) {
    sendLog('error', 'Failed to create WebSocket:', error.message);
    scheduleReconnect();
  }
}

// 安排重连
function scheduleReconnect() {
  if (reconnectAttempts >= maxReconnectAttempts) {
    sendLog('error', `Max reconnect attempts (${maxReconnectAttempts}) reached`);
    chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: 'Connection failed after multiple attempts' });
    return;
  }
  
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
  }
  
  reconnectAttempts++;
  sendLog('warn', `Scheduling reconnect in ${reconnectDelay}ms (attempt ${reconnectAttempts}/${maxReconnectAttempts})`);
  
  reconnectTimer = setTimeout(() => {
    connectWebSocket();
  }, reconnectDelay);
  
  // 指数退避，最大30秒
  reconnectDelay = Math.min(reconnectDelay * 2, 30000);
}

// 心跳机制
function startHeartbeat() {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send('PING');
      sendLog('info', 'Sent heartbeat PING');
    }
  }, 30000); // 每30秒发送心跳
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

// 音频数据缓冲管理
function sendAudioData(audioData) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(audioData);
      return true;
    } catch (error) {
      sendLog('error', 'Failed to send audio data:', error.message);
      return false;
    }
  } else {
    // 连接不可用时缓冲数据
    if (audioBuffer.length >= maxBufferSize) {
      audioBuffer.shift(); // 移除最老的数据
    }
    audioBuffer.push(audioData);
    sendLog('warn', `WebSocket not ready (state: ${ws?.readyState}), buffered audio data (${audioBuffer.length}/${maxBufferSize})`);
    return false;
  }
}

function flushAudioBuffer() {
  if (audioBuffer.length > 0) {
    sendLog('info', `Flushing ${audioBuffer.length} buffered audio packets`);
    while (audioBuffer.length > 0 && ws && ws.readyState === WebSocket.OPEN) {
      const data = audioBuffer.shift();
      try {
        ws.send(data);
      } catch (error) {
        sendLog('error', 'Failed to send buffered audio data:', error.message);
        break;
      }
    }
  }
}

chrome.runtime.onMessage.addListener(async (message) => {
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
          chromeMediaSource: 'tab',
          chromeMediaSourceId: message.streamId
        }
      };
      sendLog('info', 'Attempting getUserMedia with constraints:', constraints);
      
      // 获取音频流 - 添加更详细的错误处理
      let audioStream;
      try {
        audioStream = await navigator.mediaDevices.getUserMedia(constraints);
      } catch (getUserMediaError) {
        sendLog('error', 'getUserMedia failed:', {
          name: getUserMediaError.name,
          message: getUserMediaError.message,
          constraint: getUserMediaError.constraint
        });
        
        // 尝试使用更简单的约束  
        sendLog('info', 'Trying with mandatory constraints...');
        const simpleConstraints = {
          audio: {
            mandatory: {
              chromeMediaSource: 'tab',
              chromeMediaSourceId: message.streamId
            }
          }
        };
        
        try {
          audioStream = await navigator.mediaDevices.getUserMedia(simpleConstraints);
          sendLog('success', 'Audio capture successful with simplified constraints!');
        } catch (retryError) {
          sendLog('error', 'Retry also failed:', retryError.message);
          throw retryError;
        }
      }
      sendLog('success', 'Audio capture successful!');
      
      // 详细检查音频流
      sendLog('info', 'Audio stream details:', {
        id: audioStream.id,
        active: audioStream.active
      });
      
      const audioTracks = audioStream.getAudioTracks();
      sendLog('info', `Got ${audioTracks.length} audio tracks`);
      if (audioTracks.length > 0) {
        const track = audioTracks[0];
        const settings = track.getSettings();
        const constraints = track.getConstraints();
        sendLog('info', 'First audio track details:', {
          label: track.label,
          kind: track.kind,
          enabled: track.enabled,
          muted: track.muted,
          readyState: track.readyState,
          settings: settings,
          constraints: constraints
        });
        
        // 监听音频轨道状态变化
        track.onended = () => sendLog('warn', 'Audio track ended');
        track.onmute = () => sendLog('warn', 'Audio track muted');
        track.onunmute = () => sendLog('info', 'Audio track unmuted');
      }
      
      // 设置WebSocket URL和流ID
      wsUrl = location.hostname === 'localhost' 
        ? "ws://localhost:8080/stream"
        : "wss://meeting-translate-1019079553349.asia-east2.run.app/stream";
      currentStreamId = message.streamId;
      
      // 重置重连状态
      reconnectAttempts = 0;
      reconnectDelay = 1000;
      
      // 连接WebSocket
      connectWebSocket();
      
      // 等待WebSocket连接建立后再设置音频处理
      const waitForConnection = () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          setupAudioProcessing();
        } else {
          setTimeout(waitForConnection, 100);
        }
      };
      waitForConnection();
      
      async function setupAudioProcessing() {
        sendLog('success', 'Setting up audio processing pipeline...');
        
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
          
          // 添加音频分析器来监控原始音频级别
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 2048;
          const dataArray = new Uint8Array(analyser.frequencyBinCount);
          
          src.connect(analyser);
          
          // 每秒检查一次原始音频级别
          const checkAudioLevel = () => {
            analyser.getByteFrequencyData(dataArray);
            const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length;
            sendLog('info', `Raw audio level from tab: ${average.toFixed(2)} (0-255 scale)`);
            
            if (average < 1) {
              sendLog('warn', 'No audio detected from tab - check if Gather has audio enabled');
            }
            
            setTimeout(checkAudioLevel, 1000);
          };
          checkAudioLevel();
          
          workletNode = new AudioWorkletNode(audioCtx, "pcm16k-writer");
          
          // 创建音频分支：一路给worklet处理，一路输出到扬声器
          const splitter = audioCtx.createChannelSplitter(1);
          const merger = audioCtx.createChannelMerger(1);
          
          // 音频流：源 -> 分析器 -> 分离器 -> (worklet + 输出)
          src.connect(splitter);
          splitter.connect(workletNode, 0);  // 发送到worklet处理
          splitter.connect(merger, 0, 0);    // 发送到输出
          merger.connect(audioCtx.destination);  // 输出到扬声器
          
          let audioDataCount = 0;
          workletNode.port.onmessage = (e) => {
            if (e.data.type === 'audio_level') {
              // 处理音频级别消息
              sendLog('info', `Audio level - RMS: ${e.data.rms.toFixed(4)}, Chunk: ${e.data.chunkCount}`);
              if (e.data.rms < 0.001) {
                sendLog('warn', 'Very low audio level detected - possible silence');
              }
              return;
            }
            
            // 处理音频数据消息
            audioDataCount++;
            if (audioDataCount <= 5 || audioDataCount % 50 === 0) {
              sendLog('info', `Sending audio data #${audioDataCount}, size: ${e.data.byteLength} bytes`);
            }
            
            // 使用新的音频数据发送函数
            const success = sendAudioData(e.data);
            if (!success && audioDataCount % 10 === 0) {
              sendLog('warn', `Failed to send audio data #${audioDataCount} - connection issues`);
            }
          };
          
          sendLog('success', 'Audio pipeline connected successfully!');
          
        } catch (audioError) {
          sendLog('error', 'Audio setup failed:', audioError.message);
          chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: audioError.message });
        }
      }
      
    } catch (error) {
      sendLog('error', 'Failed to start capture:', error.message);
      chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: error.message });
    }
  } else if (message.type === 'STOP_CAPTURE') {
    sendLog('info', 'Stopping capture');
    
    // 停止心跳
    stopHeartbeat();
    
    // 清除重连定时器
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    
    // 断开音频处理
    if (workletNode) {
      workletNode.disconnect();
      workletNode = null;
    }
    if (audioCtx) {
      await audioCtx.close();
      audioCtx = null;
    }
    
    // 正常关闭WebSocket (code 1000)
    if (ws) {
      ws.close(1000, 'User stopped capture');
      ws = null;
    }
    
    // 清空缓冲
    audioBuffer = [];
    
    // 重置状态
    reconnectAttempts = 0;
    reconnectDelay = 1000;
    wsUrl = null;
    currentStreamId = null;
    
    sendLog('info', 'Capture stopped successfully');
  }
});