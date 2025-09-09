# asr.py
from __future__ import annotations
import time
import threading
from typing import Callable, Optional, Iterable

from google.cloud import speech_v1 as speech

# 说明：输入必须是 16kHz、LINEAR16、单声道 PCM（与扩展发送的数据一致）
ASR_SAMPLE_RATE = 16000
ASR_ENCODING = speech.RecognitionConfig.AudioEncoding.LINEAR16

class GoogleSTTStream:
    """
    双向流封装：
    - push(b: bytes): 投递音频小块（Int16 LE, 16kHz）
    - close(): 结束
    - 后台读 STT 响应，回调 on_partial/on_final
    """
    def __init__(
        self,
        on_partial: Callable[[str], None],
        on_final: Callable[[str], None],
        language: str = "en-US",
        alt_langs: Optional[list[str]] = None,
        max_stream_seconds: int = 230,   # 约 3分50秒，防止被动断流
    ) -> None:
        self._client = speech.SpeechClient()
        self._on_partial = on_partial
        self._on_final = on_final
        self._language = language
        self._alt_langs = alt_langs or []
        self._max_seconds = max_stream_seconds

        self._lock = threading.Lock()
        self._closed = False
        self._bytes_sent = 0
        self._start_ts = time.time()

        # 简单的生产者队列（用 list + lock；负载大可换 queue.Queue）
        self._chunks: list[bytes] = []

        # 启动识别线程
        self._resp_thread = threading.Thread(target=self._run_stream, daemon=True)
        self._resp_thread.start()

    # 供外部调用：投递音频
    def push(self, chunk: bytes) -> None:
        if self._closed:
            return
        with self._lock:
            self._chunks.append(chunk)
            self._bytes_sent += len(chunk)

    # 供外部调用：关闭
    def close(self) -> None:
        self._closed = True
        # 等待线程结束（短等待）
        if self._resp_thread.is_alive():
            self._resp_thread.join(timeout=2.0)

    # 内部：生成 request 流
    def _request_iter(self) -> Iterable[speech.StreamingRecognizeRequest]:
        # 第一个请求：配置
        config = speech.RecognitionConfig(
            encoding=ASR_ENCODING,
            sample_rate_hertz=ASR_SAMPLE_RATE,
            language_code=self._language,
            alternative_language_codes=self._alt_langs,
            enable_automatic_punctuation=True,
            model="latest_long",  # 可改 "default"
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
            single_utterance=False,
        )
        yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)

        # 后续请求：音频块
        last_flush = time.time()
        while not self._closed:
            chunk = None
            with self._lock:
                if self._chunks:
                    chunk = self._chunks.pop(0)

            if chunk:
                yield speech.StreamingRecognizeRequest(audio_content=chunk)

            # 软重置条件：接近上限时结束本次流
            if (time.time() - self._start_ts) > self._max_seconds:
                break

            # 简单节流，避免忙等
            now = time.time()
            if now - last_flush > 0.02:
                time.sleep(0.01)
                last_flush = now

    def _run_stream(self) -> None:
        """建立一次流；若达到时长上限则自然结束（需要外层重建以实现长会）。"""
        try:
            # 创建流配置
            streaming_config = speech.StreamingRecognitionConfig(
                config=speech.RecognitionConfig(
                    encoding=ASR_ENCODING,
                    sample_rate_hertz=ASR_SAMPLE_RATE,
                    language_code=self._language,
                    alternative_language_codes=self._alt_langs,
                    enable_automatic_punctuation=True,
                    model="latest_long",
                ),
                interim_results=True,
                single_utterance=False,
            )
            
            # 创建音频请求迭代器
            def audio_requests():
                # 第一个请求包含配置
                yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)
                
                # 后续请求包含音频数据
                last_flush = time.time()
                while not self._closed:
                    chunk = None
                    with self._lock:
                        if self._chunks:
                            chunk = self._chunks.pop(0)

                    if chunk:
                        yield speech.StreamingRecognizeRequest(audio_content=chunk)

                    # 软重置条件：接近上限时结束本次流
                    if (time.time() - self._start_ts) > self._max_seconds:
                        break

                    # 简单节流，避免忙等
                    now = time.time()
                    if now - last_flush > 0.02:
                        time.sleep(0.01)
                        last_flush = now
            
            # 使用正确的API调用方式
            responses = self._client.streaming_recognize(audio_requests())
            
            for resp in responses:
                if not resp.results:
                    continue
                result = resp.results[0]
                if not result.alternatives:
                    continue
                text = result.alternatives[0].transcript.strip()
                if not text:
                    continue
                if result.is_final:
                    self._on_final(text)
                else:
                    self._on_partial(text)
        except Exception as e:
            # 生产上建议打日志或上报
            print(f"[GoogleSTTStream] error: {e}")
            import traceback
            print(f"[GoogleSTTStream] traceback: {traceback.format_exc()}")
        finally:
            self._closed = True
