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
            if (ws && ws.readyState === 1) {
              ws.send(e.data);
            } else {
              sendLog('warn', 'WebSocket not ready, readyState:', ws?.readyState);
            }
          };
          
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