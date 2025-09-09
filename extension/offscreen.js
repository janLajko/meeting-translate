let ws = null;
let audioCtx, workletNode;

// AudioWorklet：重采样到16k，输出Int16 PCM
const WORKLET_PROCESSOR_CODE = `
class PCM16KWriter extends AudioWorkletProcessor {
  constructor() {
    super();
    this._ratio = sampleRate / 16000;
    this._samplesPerChunk = Math.round(16000 * 0.2); // 200ms
    this._acc = [];
  }
  _resample(input) {
    const outLen = Math.floor(input.length / this._ratio);
    const out = new Float32Array(outLen);
    let idx = 0, pos = 0;
    while (idx < outLen) {
      out[idx++] = input[Math.floor(pos)];
      pos += this._ratio;
    }
    return out;
  }
  _floatTo16BitPCM(float32) {
    const buf = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < float32.length; i++) {
      let s = Math.max(-1, Math.min(1, float32[i]));
      view.setInt16(i*2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buf;
  }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    const resampled = this._resample(ch);
    this._acc.push(...resampled);
    while (this._acc.length >= this._samplesPerChunk) {
      const chunk = this._acc.slice(0, this._samplesPerChunk);
      this._acc = this._acc.slice(this._samplesPerChunk);
      const buf = this._floatTo16BitPCM(Float32Array.from(chunk));
      this.port.postMessage(buf, [buf]);
    }
    return true;
  }
}
registerProcessor('pcm16k-writer', PCM16KWriter);
`;

chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  console.log('[Offscreen] Received message:', message);
  
  if (message.type === 'START_CAPTURE') {
    try {
      console.log('[Offscreen] Starting audio capture with streamId:', message.streamId);
      
      // 获取音频流
      const audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          mandatory: {
            chromeMediaSource: 'tab',
            chromeMediaSourceId: message.streamId
          }
        }
      });
      console.log('[Offscreen] Audio capture successful');
      
      // 连接WebSocket - 支持本地和Cloud Run部署
      const wsUrl = location.hostname === 'localhost' 
        ? "ws://localhost:8080/stream"
        : "wss://your-cloud-run-url.run.app/stream";  // 替换为你的Cloud Run URL
      ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      
      ws.onopen = async () => {
        console.log('[Offscreen] WebSocket connected');
        
        audioCtx = new AudioContext({ sampleRate: 48000 });
        await audioCtx.audioWorklet.addModule(URL.createObjectURL(new Blob([WORKLET_PROCESSOR_CODE], {type:"application/javascript"})));
        
        const src = audioCtx.createMediaStreamSource(audioStream);
        workletNode = new AudioWorkletNode(audioCtx, "pcm16k-writer");
        workletNode.port.onmessage = (e) => {
          console.log('[Offscreen] Sending audio data, size:', e.data.byteLength);
          if (ws && ws.readyState === 1) ws.send(e.data);
        };
        src.connect(workletNode).connect(audioCtx.destination);
        
        // 通知background script启动成功
        chrome.runtime.sendMessage({ type: 'CAPTURE_STARTED' });
      };
      
      ws.onmessage = (evt) => {
        console.log('[Offscreen] Received message from server:', evt.data);
        // 转发到background script
        chrome.runtime.sendMessage({ 
          type: 'SUBTITLE_DATA', 
          data: evt.data, 
          tabId: message.tabId 
        });
      };
      
      ws.onclose = () => {
        console.log('[Offscreen] WebSocket closed');
        chrome.runtime.sendMessage({ type: 'CAPTURE_STOPPED' });
      };
      
      ws.onerror = (error) => {
        console.error('[Offscreen] WebSocket error:', error);
        chrome.runtime.sendMessage({ type: 'CAPTURE_ERROR', error: error.message });
      };
      
    } catch (error) {
      console.error('[Offscreen] Failed to start capture:', error);
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