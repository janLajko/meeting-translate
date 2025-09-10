// AudioWorklet: 重采样到16kHz，输出Int16 PCM
class PCM16KWriter extends AudioWorkletProcessor {
  constructor() {
    super();
    this._ratio = sampleRate / 16000;
    this._samplesPerChunk = Math.round(16000 * 0.2); // 200ms
    this._acc = [];
    this._chunkCount = 0;
    this._totalRMS = 0;
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
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buf;
  }
  
  _calculateRMS(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      sum += samples[i] * samples[i];
    }
    return Math.sqrt(sum / samples.length);
  }
  
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    
    const resampled = this._resample(ch);
    this._acc.push(...resampled);
    
    while (this._acc.length >= this._samplesPerChunk) {
      const chunk = this._acc.slice(0, this._samplesPerChunk);
      this._acc = this._acc.slice(this._samplesPerChunk);
      
      // 计算音频级别
      const rms = this._calculateRMS(chunk);
      this._totalRMS += rms;
      this._chunkCount++;
      
      const buf = this._floatTo16BitPCM(Float32Array.from(chunk));
      
      // 每50个chunk报告一次音频级别
      if (this._chunkCount % 50 === 0) {
        const avgRMS = this._totalRMS / 50;
        this.port.postMessage({
          type: 'audio_level',
          rms: avgRMS,
          chunkCount: this._chunkCount
        });
        this._totalRMS = 0; // 重置
      }
      
      this.port.postMessage(buf, [buf]);
    }
    
    return true;
  }
}

registerProcessor('pcm16k-writer', PCM16KWriter);