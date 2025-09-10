# asr.py
from __future__ import annotations
import time
import threading
import asyncio
import queue as sync_queue
from typing import Callable, Optional

from google.cloud import speech_v1 as speech

# 说明：输入必须是 16kHz、LINEAR16、单声道 PCM（与扩展发送的数据一致）
ASR_SAMPLE_RATE = 16000
ASR_ENCODING = speech.RecognitionConfig.AudioEncoding.LINEAR16

class GoogleSTTStream:
    """
    改进的Google STT流实现：
    - 使用队列架构避免阻塞
    - 异步结果处理
    - 智能健康检查
    - 优雅的错误处理和资源清理
    """
    def __init__(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
        language: str = "en-US",
        alt_langs: Optional[list[str]] = None,
    ) -> None:
        self._client = speech.SpeechClient()
        self._on_partial = on_partial
        self._on_final = on_final
        self._language = language
        self._alt_langs = alt_langs or []

        # 状态管理
        self._closed = False
        self._bytes_sent = 0
        self._start_ts = time.time()
        
        # 健康检查相关
        self._last_response_time = time.time()
        self._last_transcript = ""
        self._repeat_count = 0
        self._max_repeat_threshold = 5
        self._response_timeout = 30
        
        # 队列系统 - 参考优秀实现
        self._audio_queue = sync_queue.Queue(maxsize=100)  # 音频数据队列
        self._result_queue = sync_queue.Queue()  # 结果队列
        
        # 线程管理
        self._recognition_thread = None
        self._result_thread = None
        
        # 配置Google STT
        self._streaming_config = self._create_streaming_config()
        
        print(f"[GoogleSTTStream] 🚀 Initializing STT - Language: {self._language}, Alt: {self._alt_langs}")
        self._start_threads()
        print(f"[GoogleSTTStream] ✅ STT stream initialized successfully")

    def _create_streaming_config(self):
        """创建Google STT配置"""
        config = speech.RecognitionConfig(
            encoding=ASR_ENCODING,
            sample_rate_hertz=ASR_SAMPLE_RATE,
            language_code=self._language,
            alternative_language_codes=self._alt_langs,
            enable_automatic_punctuation=True,
            model="latest_long",
            use_enhanced=True,
            enable_word_time_offsets=True,
            enable_word_confidence=True,
            max_alternatives=1,
        )
        
        return speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
            single_utterance=False,
        )
    
    def _start_threads(self):
        """启动处理线程"""
        # 启动识别线程
        self._recognition_thread = threading.Thread(target=self._recognition_worker, daemon=True)
        self._recognition_thread.start()
        
        # 启动结果处理线程
        self._result_thread = threading.Thread(target=self._result_worker, daemon=True)
        self._result_thread.start()
    
    def push(self, chunk: bytes) -> bool:
        """投递音频数据"""
        if self._closed:
            print(f"[GoogleSTTStream] ⚠️ Stream closed, ignoring {len(chunk)} bytes")
            return False
            
        try:
            self._audio_queue.put(chunk, timeout=1.0)
            self._bytes_sent += len(chunk)
            
            # 减少日志频率
            if self._bytes_sent % 50000 == 0:  # 每50KB记录一次
                print(f"[GoogleSTTStream] 📊 Processed {self._bytes_sent} bytes, queue size: {self._audio_queue.qsize()}")
                
            return True
            
        except sync_queue.Full:
            print(f"[GoogleSTTStream] ⚠️ Audio queue full, dropping {len(chunk)} bytes")
            return False
        except Exception as e:
            print(f"[GoogleSTTStream] ❌ Error pushing audio: {e}")
            return False

    def close(self) -> None:
        """关闭STT流并清理资源"""
        if self._closed:
            return
            
        print(f"[GoogleSTTStream] 🔚 Closing STT stream...")
        self._closed = True
        
        # 发送结束信号到队列
        try:
            self._audio_queue.put(None, timeout=1.0)
        except sync_queue.Full:
            pass
        
        # 等待线程结束
        if self._recognition_thread and self._recognition_thread.is_alive():
            self._recognition_thread.join(timeout=3.0)
            
        if self._result_thread and self._result_thread.is_alive():
            self._result_thread.join(timeout=3.0)
            
        # 清理队列
        self._clear_queues()
        
        runtime = time.time() - self._start_ts
        print(f"[GoogleSTTStream] ✅ STT stream closed after {runtime:.1f}s, processed {self._bytes_sent} bytes")
    
    def _check_stream_health(self) -> bool:
        """检查STT流健康状态"""
        now = time.time()
        
        # 检查响应超时
        if now - self._last_response_time > self._response_timeout:
            print(f"[GoogleSTTStream] ⚠️ Response timeout: {now - self._last_response_time:.1f}s since last response")
            return False
            
        # 检查重复输出
        if self._repeat_count >= self._max_repeat_threshold:
            print(f"[GoogleSTTStream] ⚠️ Too many repeats: {self._repeat_count} consecutive identical results")
            return False
            
        return True
    
    def _handle_transcript(self, text: str, is_final: bool) -> bool:
        """处理transcript并检查重复"""
        self._last_response_time = time.time()
        
        # 检查重复
        if text == self._last_transcript:
            self._repeat_count += 1
            print(f"[GoogleSTTStream] Repeat detected #{self._repeat_count}: '{text}'")
        else:
            self._repeat_count = 0
            self._last_transcript = text
            
        # 检查是否需要重建流
        if not self._check_stream_health():
            print(f"[GoogleSTTStream] Stream health check failed, needs rebuild")
            return False  # 表示需要重建
            
        return True  # 流健康，继续处理
    
    def _recognition_worker(self):
        """识别工作线程"""
        print(f"[GoogleSTTStream] 🎯 Recognition worker started")
        
        try:
            def audio_generator():
                """音频数据生成器"""
                while not self._closed:
                    try:
                        chunk = self._audio_queue.get(timeout=1.0)
                        if chunk is None:  # 结束信号
                            break
                        yield speech.StreamingRecognizeRequest(audio_content=chunk)
                    except sync_queue.Empty:
                        continue
                    except Exception as e:
                        print(f"[GoogleSTTStream] ❌ Audio generator error: {e}")
                        break
            
            print(f"[GoogleSTTStream] 🔄 Starting streaming recognition...")
            requests = audio_generator()
            responses = self._client.streaming_recognize(self._streaming_config, requests)
            
            for response in responses:
                if self._closed:
                    break
                    
                if not response.results:
                    continue
                    
                result = response.results[0]
                if not result.alternatives:
                    continue
                    
                transcript = result.alternatives[0].transcript.strip()
                confidence = getattr(result.alternatives[0], 'confidence', 0.0)
                is_final = result.is_final
                
                if transcript:
                    # 发送结果到结果队列
                    result_data = {
                        'transcript': transcript,
                        'confidence': confidence,
                        'is_final': is_final,
                        'timestamp': time.time()
                    }
                    
                    try:
                        self._result_queue.put(result_data, timeout=1.0)
                    except sync_queue.Full:
                        print(f"[GoogleSTTStream] ⚠️ Result queue full, dropping result")
                        
        except Exception as e:
            error_type = type(e).__name__
            print(f"[GoogleSTTStream] ❌ Recognition worker error ({error_type}): {e}")
            
            # 发送错误到结果队列
            try:
                self._result_queue.put({'error': str(e), 'error_type': error_type}, timeout=1.0)
            except sync_queue.Full:
                pass
                
            # 根据错误类型提供建议
            if "DEADLINE_EXCEEDED" in str(e) or "timeout" in str(e).lower():
                print(f"[GoogleSTTStream] 💡 Timeout error - connection may need retry")
            elif "RESOURCE_EXHAUSTED" in str(e):
                print(f"[GoogleSTTStream] 💡 Resource exhausted - may need backoff")
            elif "UNAUTHENTICATED" in str(e):
                print(f"[GoogleSTTStream] 💡 Auth error - check credentials")
                
        finally:
            print(f"[GoogleSTTStream] 🏁 Recognition worker finished")
    
    def _result_worker(self):
        """结果处理工作线程"""
        print(f"[GoogleSTTStream] 📝 Result worker started")
        
        try:
            while not self._closed:
                try:
                    result_data = self._result_queue.get(timeout=1.0)
                    
                    # 处理错误
                    if 'error' in result_data:
                        print(f"[GoogleSTTStream] ❌ Received error: {result_data.get('error_type', 'Unknown')}: {result_data['error']}")
                        # 错误处理可以在这里触发重建逻辑
                        break
                    
                    # 处理正常结果
                    transcript = result_data['transcript']
                    confidence = result_data['confidence']
                    is_final = result_data['is_final']
                    
                    # 健康检查
                    if not self._handle_transcript(transcript, is_final):
                        print(f"[GoogleSTTStream] ⚠️ Health check failed, stopping result worker")
                        break
                    
                    # 调用回调
                    try:
                        if is_final:
                            self._on_final(transcript)
                            print(f"[GoogleSTTStream] ✅ Final: '{transcript}' (conf: {confidence:.2f})")
                        else:
                            self._on_partial(transcript)
                            print(f"[GoogleSTTStream] 📋 Partial: '{transcript}' (conf: {confidence:.2f})")
                    except Exception as callback_error:
                        print(f"[GoogleSTTStream] ❌ Callback error: {callback_error}")
                    
                except sync_queue.Empty:
                    continue
                except Exception as e:
                    print(f"[GoogleSTTStream] ❌ Result worker error: {e}")
                    break
                    
        except Exception as e:
            print(f"[GoogleSTTStream] ❌ Result worker exception: {e}")
        finally:
            print(f"[GoogleSTTStream] 🏁 Result worker finished")
    
    def _clear_queues(self):
        """清理所有队列"""
        try:
            # 清空音频队列
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except sync_queue.Empty:
                    break
                    
            # 清空结果队列
            while not self._result_queue.empty():
                try:
                    self._result_queue.get_nowait()
                except sync_queue.Empty:
                    break
                    
        except Exception as e:
            print(f"[GoogleSTTStream] ⚠️ Error clearing queues: {e}")

    def is_healthy(self) -> bool:
        """检查流是否健康 - 供外部调用"""
        return not self._closed and self._check_stream_health()
    
    def get_stats(self) -> dict:
        """获取流统计信息"""
        runtime = time.time() - self._start_ts
        return {
            'runtime': runtime,
            'bytes_sent': self._bytes_sent,
            'queue_size': self._audio_queue.qsize(),
            'result_queue_size': self._result_queue.qsize(),
            'repeat_count': self._repeat_count,
            'last_response_age': time.time() - self._last_response_time,
            'is_healthy': self.is_healthy(),
            'is_closed': self._closed
        }