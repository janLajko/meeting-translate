# deepgram_asr.py
"""
Deepgram语音识别包装类
实现STTStreamBase接口，提供与GoogleSTTStream兼容的API
使用async WebSocket接口 (SDK 4.7.0+)
"""

import asyncio
import json
import threading
import time
import queue
from typing import Optional, Dict, Any
import logging

try:
    from deepgram import (
        DeepgramClient, 
        DeepgramClientOptions,
        LiveTranscriptionEvents,
        LiveOptions,
        Deepgram
    )
    DEEPGRAM_AVAILABLE = True
except ImportError:
    print("[DeepgramASR] ⚠️ Deepgram SDK未安装，请运行: pip install deepgram-sdk")
    DEEPGRAM_AVAILABLE = False
    # 创建占位符类
    class DeepgramClient:
        pass
    class LiveOptions:
        pass
    class LiveTranscriptionEvents:
        Transcript = "transcript"
        Open = "open"
        Close = "close"
        Error = "error"
        Metadata = "metadata"

from stt_base import STTStreamBase, STTStatus


class DeepgramSTTStream(STTStreamBase):
    """
    Deepgram语音识别流包装类
    
    提供与Google STT相似的接口，支持：
    - 实时流式识别
    - 中英混合语音
    - 部分和最终结果
    - 自动重连
    - 健康检查
    """
    
    def __init__(
        self,
        on_partial: callable,
        on_final: callable,
        api_key: str,
        language: str = "multi",
        model: str = "nova-2",
        smart_format: bool = True,
        interim_results: bool = True,
        endpointing: int = 300,
        sample_rate: int = 16000,
        debug: bool = False
    ):
        """
        初始化Deepgram STT流
        
        Args:
            on_partial: 部分结果回调
            on_final: 最终结果回调
            api_key: Deepgram API密钥
            language: 语言设置 ("multi"支持多语言)
            model: 使用的模型 (默认nova-2)
            smart_format: 是否启用智能格式化
            interim_results: 是否返回部分结果
            endpointing: 停顿检测时间(ms)
            sample_rate: 音频采样率
            debug: 调试模式
        """
        super().__init__(on_partial, on_final, language, sample_rate, debug)
        
        if not DEEPGRAM_AVAILABLE:
            raise ImportError("Deepgram SDK未安装，无法使用DeepgramSTTStream")
        
        self.api_key = api_key
        self.model = model
        self.smart_format = smart_format
        self.interim_results = interim_results
        self.endpointing = endpointing
        
        # Deepgram客户端和连接
        self.client: Optional[DeepgramClient] = None
        self.connection = None
        
        # 异步运行时控制
        self.loop = None
        self.loop_thread = None
        self._audio_queue = queue.Queue()
        self._should_stop = threading.Event()
        
        # 重连控制
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2  # 秒
        self.current_reconnect_attempts = 0
        
        # 健康检查
        self._repeat_count = 0
        self._last_text = ""
        self._max_repeats = 3
        
        # 错误处理
        self._connection_errors = 0
        self._max_connection_errors = 3
        
        if debug:
            print(f"[DeepgramSTT] 初始化: model={model}, language={language}")
    
    def connect(self) -> bool:
        """建立Deepgram连接"""
        try:
            self._set_status(STTStatus.CONNECTING)
            
            # 停止之前的连接
            if self.loop_thread and self.loop_thread.is_alive():
                self._should_stop.set()
                self.loop_thread.join(timeout=3)
            
            # 重置状态
            self._should_stop.clear()
            
            # 启动异步事件循环线程
            self.loop_thread = threading.Thread(target=self._run_async_loop, daemon=True)
            self.loop_thread.start()
            
            # 等待连接建立
            max_wait = 10  # 最多等待10秒
            start_time = time.time()
            
            while time.time() - start_time < max_wait:
                if self.get_status() == STTStatus.CONNECTED:
                    if self.debug:
                        print("[DeepgramSTT] ✅ 连接成功")
                    return True
                elif self.get_status() == STTStatus.ERROR:
                    if self.debug:
                        print("[DeepgramSTT] ❌ 连接失败")
                    return False
                time.sleep(0.1)
            
            # 连接超时
            self._set_status(STTStatus.ERROR)
            self._handle_error(Exception("Deepgram连接超时"), "连接")
            return False
                    
        except Exception as e:
            self._set_status(STTStatus.ERROR)
            self._handle_error(e, "连接")
            self._connection_errors += 1
            return False
    
    def _run_async_loop(self):
        """在独立线程中运行异步事件循环"""
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._async_connect_and_listen())
        except Exception as e:
            self._handle_error(e, "异步循环")
        finally:
            if self.loop:
                self.loop.close()
    
    async def _async_connect_and_listen(self):
        """异步连接和监听Deepgram"""
        try:
            # 创建Deepgram客户端
            self.client = DeepgramClient(self.api_key)
            
            # 创建WebSocket连接 - 使用asyncwebsocket
            self.connection = self.client.listen.asyncwebsocket.v("1")
            
            # 设置事件处理器
            self.connection.on(LiveTranscriptionEvents.Open, self._on_open)
            self.connection.on(LiveTranscriptionEvents.Transcript, self._on_message)
            self.connection.on(LiveTranscriptionEvents.Close, self._on_close) 
            self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.connection.on(LiveTranscriptionEvents.Metadata, self._on_metadata)
            
            # 配置选项
            options = LiveOptions(
                model=self.model,
                language=self.language,
                smart_format=self.smart_format,
                interim_results=self.interim_results,
                endpointing=self.endpointing,
                sample_rate=self.sample_rate,
                encoding="linear16",  # PCM 16位
                channels=1  # 单声道
            )
            
            # 启动连接
            if await self.connection.start(options):
                self._set_status(STTStatus.CONNECTED)
                self._increment_stat("connection_count")
                self._connection_errors = 0
                self.current_reconnect_attempts = 0
                
                with self._stats_lock:
                    if not self._stats["start_time"]:
                        self._stats["start_time"] = time.time()
                
                # 启动音频发送协程
                await asyncio.gather(
                    self._audio_sender(),
                    self._keep_alive()
                )
            else:
                self._set_status(STTStatus.ERROR)
                self._handle_error(Exception("Deepgram连接启动失败"), "连接")
                
        except Exception as e:
            self._set_status(STTStatus.ERROR)
            self._handle_error(e, "异步连接")
    
    async def _audio_sender(self):
        """音频发送协程"""
        while not self._should_stop.is_set():
            try:
                # 从队列获取音频数据，非阻塞
                audio_data = None
                try:
                    audio_data = self._audio_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.01)  # 10ms
                    continue
                
                if audio_data and self.connection:
                    await self.connection.send(audio_data)
                    self._increment_stat("total_bytes_sent", len(audio_data))
                    self._update_activity()
                    
            except Exception as e:
                self._handle_error(e, "音频发送")
                break
    
    async def _keep_alive(self):
        """保持连接活跃"""
        while not self._should_stop.is_set():
            await asyncio.sleep(30)  # 每30秒检查一次
            if self.get_status() == STTStatus.CONNECTED:
                # 可以发送keep-alive消息或检查连接状态
                pass
    
    def push(self, audio_data: bytes) -> bool:
        """推送音频数据到Deepgram"""
        if not audio_data or len(audio_data) == 0:
            return True
            
        try:
            if self.get_status() == STTStatus.ERROR:
                if self.debug:
                    print("[DeepgramSTT] ⚠️ 连接不可用，尝试重连")
                if not self._reconnect():
                    return False
            
            # 将音频数据放入队列，由async协程处理
            try:
                self._audio_queue.put_nowait(audio_data)
                self._set_status(STTStatus.STREAMING)
                return True
            except queue.Full:
                if self.debug:
                    print("[DeepgramSTT] ⚠️ 音频队列已满，丢弃数据")
                return False
                
        except Exception as e:
            self._handle_error(e, "音频推送")
            return False
    
    def close(self) -> None:
        """关闭Deepgram连接"""
        try:
            # 停止异步循环
            self._should_stop.set()
            
            # 关闭连接
            if self.connection and self.loop:
                # 安全关闭异步连接
                def close_connection():
                    if self.connection:
                        asyncio.run_coroutine_threadsafe(
                            self.connection.finish(), self.loop
                        )
                
                try:
                    close_connection()
                except:
                    pass
            
            # 等待线程结束
            if self.loop_thread and self.loop_thread.is_alive():
                self.loop_thread.join(timeout=3)
                    
            self.connection = None
            self.client = None
            self._set_status(STTStatus.CLOSED)
            
            if self.debug:
                print("[DeepgramSTT] 连接已关闭")
                
        except Exception as e:
            self._handle_error(e, "关闭连接")
    
    def _reconnect(self) -> bool:
        """重新连接到Deepgram"""
        if self.current_reconnect_attempts >= self.max_reconnect_attempts:
            if self.debug:
                print(f"[DeepgramSTT] 重连次数达到上限 ({self.max_reconnect_attempts})")
            return False
        
        self.current_reconnect_attempts += 1
        self._increment_stat("reconnection_count")
        
        if self.debug:
            print(f"[DeepgramSTT] 尝试重连 ({self.current_reconnect_attempts}/{self.max_reconnect_attempts})")
        
        # 关闭现有连接
        try:
            if self.connection:
                self.connection.finish()
        except:
            pass
        
        # 等待重连延迟
        time.sleep(self.reconnect_delay)
        
        # 尝试重新连接
        return self.connect()
    
    # Deepgram事件处理器 - 使用正确的SDK 4.7.0签名
    
    async def _on_open(self, connection, open_response, **kwargs):
        """连接打开事件"""
        if self.debug:
            print("[DeepgramSTT] WebSocket连接已打开")
        self._set_status(STTStatus.CONNECTED)
    
    async def _on_close(self, connection, close_response, **kwargs):
        """连接关闭事件"""
        if self.debug:
            print("[DeepgramSTT] WebSocket连接已关闭")
        
        if self.get_status() != STTStatus.CLOSED:
            self._set_status(STTStatus.DISCONNECTED)
    
    async def _on_error(self, connection, error, **kwargs):
        """错误事件"""
        self._handle_error(Exception(f"Deepgram WebSocket错误: {error}"), "WebSocket")
    
    async def _on_metadata(self, connection, metadata, **kwargs):
        """元数据事件"""
        if self.debug:
            print(f"[DeepgramSTT] 收到元数据: {metadata}")
    
    async def _on_message(self, connection, result, **kwargs):
        """转录结果事件"""
        try:
            # 解析结果
            if hasattr(result, 'channel') and result.channel:
                alternatives = result.channel.alternatives
                if alternatives and len(alternatives) > 0:
                    transcript = alternatives[0].transcript
                    is_final = getattr(result, 'is_final', False)
                    speech_final = getattr(result, 'speech_final', False)
                    
                    # 检测语言（Deepgram可能在metadata中提供）
                    detected_language = self._detect_language_from_text(transcript)
                    
                    if transcript and transcript.strip():
                        # 健康检查：避免重复文本
                        if not self._health_check_transcript(transcript, is_final):
                            return
                        
                        if is_final or speech_final:
                            self._handle_final_result(transcript, detected_language)
                        else:
                            self._handle_partial_result(transcript, detected_language)
                    
        except Exception as e:
            self._handle_error(e, "处理转录结果")
    
    def _detect_language_from_text(self, text: str) -> str:
        """
        从文本内容检测语言
        
        Args:
            text: 输入文本
            
        Returns:
            str: 语言代码
        """
        if not text:
            return self.language
        
        # 简单的中文检测
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        total_chars = len([c for c in text if c.isalnum()])
        
        if total_chars == 0:
            return self.language
        
        chinese_ratio = chinese_chars / total_chars
        
        if chinese_ratio > 0.3:  # 30%以上中文字符
            return "zh-CN"
        else:
            return "en-US"
    
    def _health_check_transcript(self, text: str, is_final: bool) -> bool:
        """
        健康检查转录文本，避免重复和异常
        
        Args:
            text: 转录文本
            is_final: 是否为最终结果
            
        Returns:
            bool: 是否应该处理此文本
        """
        # 对于最终结果，总是处理
        if is_final:
            self._repeat_count = 0
            self._last_text = text
            return True
        
        # 检查重复文本
        if text == self._last_text:
            self._repeat_count += 1
            if self._repeat_count > self._max_repeats:
                if self.debug:
                    print(f"[DeepgramSTT] ⚠️ 检测到重复文本，跳过: '{text[:30]}...'")
                return False
        else:
            self._repeat_count = 0
            self._last_text = text
        
        return True
    
    def is_healthy(self) -> bool:
        """
        检查Deepgram连接健康状态
        
        扩展基类检查，添加Deepgram特定的健康指标
        """
        # 基础健康检查
        if not super().is_healthy():
            return False
        
        # 检查连接错误
        if self._connection_errors >= self._max_connection_errors:
            if self.debug:
                print(f"[DeepgramSTT] 不健康：连接错误过多 ({self._connection_errors})")
            return False
        
        # 检查重连次数
        if self.current_reconnect_attempts >= self.max_reconnect_attempts:
            if self.debug:
                print(f"[DeepgramSTT] 不健康：重连次数达到上限")
            return False
        
        return True
    
    def get_deepgram_config(self) -> Dict[str, Any]:
        """获取Deepgram特定配置"""
        return {
            "model": self.model,
            "language": self.language,
            "smart_format": self.smart_format,
            "interim_results": self.interim_results,
            "endpointing": self.endpointing,
            "sample_rate": self.sample_rate,
            "api_key_set": bool(self.api_key),
            "connection_errors": self._connection_errors,
            "reconnect_attempts": self.current_reconnect_attempts,
            "max_reconnect_attempts": self.max_reconnect_attempts
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取扩展统计信息"""
        stats = super().get_stats()
        stats.update({
            "engine": "deepgram",
            "deepgram_config": self.get_deepgram_config(),
            "repeat_count": self._repeat_count,
            "last_text_preview": self._last_text[:50] if self._last_text else None
        })
        return stats


# 创建便捷的工厂函数
def create_deepgram_stt(
    on_partial: callable,
    on_final: callable,
    api_key: str,
    **kwargs
) -> DeepgramSTTStream:
    """
    创建Deepgram STT流的便捷函数
    
    Args:
        on_partial: 部分结果回调
        on_final: 最终结果回调
        api_key: Deepgram API密钥
        **kwargs: 其他配置选项
        
    Returns:
        DeepgramSTTStream: 配置好的Deepgram STT流
    """
    if not DEEPGRAM_AVAILABLE:
        raise ImportError("Deepgram SDK未安装")
    
    if not api_key:
        raise ValueError("必须提供Deepgram API密钥")
    
    return DeepgramSTTStream(
        on_partial=on_partial,
        on_final=on_final,
        api_key=api_key,
        **kwargs
    )


if __name__ == "__main__":
    # 测试代码
    import os
    
    def test_partial(text: str, lang: str):
        print(f"[Test] 部分结果: {text} ({lang})")
    
    def test_final(text: str, lang: str):
        print(f"[Test] 最终结果: {text} ({lang})")
    
    # 检查API密钥
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("请设置DEEPGRAM_API_KEY环境变量进行测试")
        exit(1)
    
    print("=== Deepgram STT测试 ===")
    
    if not DEEPGRAM_AVAILABLE:
        print("❌ Deepgram SDK未安装，跳过测试")
        exit(1)
    
    # 创建Deepgram STT流
    deepgram_stt = create_deepgram_stt(
        on_partial=test_partial,
        on_final=test_final,
        api_key=api_key,
        language="multi",
        debug=True
    )
    
    # 测试连接
    print("\n1. 测试连接:")
    success = deepgram_stt.connect()
    print(f"连接结果: {success}")
    print(f"状态: {deepgram_stt.get_status()}")
    print(f"健康: {deepgram_stt.is_healthy()}")
    
    if success:
        print("\n2. 配置信息:")
        config = deepgram_stt.get_deepgram_config()
        for key, value in config.items():
            print(f"  {key}: {value}")
        
        print("\n3. 等待5秒以保持连接...")
        time.sleep(5)
        
        # 显示统计
        print("\n4. 统计信息:")
        deepgram_stt.print_stats()
    
    # 测试关闭
    print("\n5. 测试关闭:")
    deepgram_stt.close()
    print(f"最终状态: {deepgram_stt.get_status()}")