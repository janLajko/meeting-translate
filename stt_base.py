# stt_base.py
"""
语音识别(STT)抽象基类
定义统一的接口供不同的STT引擎实现
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Dict, Any, List
import time
import threading
from enum import Enum


class STTStatus(Enum):
    """STT流状态枚举"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STREAMING = "streaming"
    ERROR = "error"
    CLOSED = "closed"


class STTStreamBase(ABC):
    """
    语音识别流抽象基类
    
    定义了所有STT引擎必须实现的接口，包括：
    - 连接管理
    - 音频数据推送
    - 结果回调
    - 健康检查
    - 统计信息
    """
    
    def __init__(
        self, 
        on_partial: Callable[[str, str], None],
        on_final: Callable[[str, str], None],
        language: str = "en-US",
        sample_rate: int = 16000,
        debug: bool = False
    ):
        """
        初始化STT流
        
        Args:
            on_partial: 部分结果回调函数 (text: str, language_code: str)
            on_final: 最终结果回调函数 (text: str, language_code: str)
            language: 主要语言代码
            sample_rate: 音频采样率
            debug: 是否启用调试模式
        """
        self.on_partial = on_partial
        self.on_final = on_final
        self.language = language
        self.sample_rate = sample_rate
        self.debug = debug
        
        # 状态管理
        self._status = STTStatus.DISCONNECTED
        self._status_lock = threading.Lock()
        
        # 统计信息
        self._stats = {
            "start_time": None,
            "total_bytes_sent": 0,
            "total_partial_results": 0,
            "total_final_results": 0,
            "total_errors": 0,
            "last_activity_time": None,
            "connection_count": 0,
            "reconnection_count": 0
        }
        self._stats_lock = threading.Lock()
        
        # 健康检查
        self._last_heartbeat = time.time()
        self._health_check_interval = 30  # 30秒
        self._max_idle_time = 120  # 2分钟无活动视为不健康
        
        if debug:
            print(f"[STTBase] 初始化STT流: language={language}, sample_rate={sample_rate}")
    
    # 抽象方法 - 子类必须实现
    
    @abstractmethod
    def connect(self) -> bool:
        """
        建立STT连接
        
        Returns:
            bool: 连接是否成功
        """
        pass
    
    @abstractmethod
    def push(self, audio_data: bytes) -> bool:
        """
        推送音频数据
        
        Args:
            audio_data: PCM音频数据
            
        Returns:
            bool: 是否成功推送
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """关闭STT连接"""
        pass
    
    @abstractmethod
    def _reconnect(self) -> bool:
        """
        重新连接（内部方法）
        
        Returns:
            bool: 重连是否成功
        """
        pass
    
    # 状态管理方法
    
    def get_status(self) -> STTStatus:
        """获取当前状态"""
        with self._status_lock:
            return self._status
    
    def _set_status(self, status: STTStatus) -> None:
        """设置状态（内部方法）"""
        with self._status_lock:
            old_status = self._status
            self._status = status
            if self.debug and old_status != status:
                print(f"[STTBase] 状态变化: {old_status.value} -> {status.value}")
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.get_status() in [STTStatus.CONNECTED, STTStatus.STREAMING]
    
    def is_healthy(self) -> bool:
        """
        检查STT流是否健康
        
        健康标准：
        1. 状态为连接或流式传输
        2. 最近有活动（接收数据或结果）
        3. 没有频繁错误
        """
        status = self.get_status()
        
        # 检查连接状态
        if status in [STTStatus.DISCONNECTED, STTStatus.ERROR, STTStatus.CLOSED]:
            return False
        
        # 检查活动时间
        with self._stats_lock:
            if self._stats["last_activity_time"]:
                idle_time = time.time() - self._stats["last_activity_time"]
                if idle_time > self._max_idle_time:
                    if self.debug:
                        print(f"[STTBase] 不健康：空闲时间过长 ({idle_time:.1f}s)")
                    return False
            
            # 检查错误率（如果有大量错误）
            total_requests = self._stats["total_partial_results"] + self._stats["total_final_results"]
            if total_requests > 10:  # 至少有10个请求才检查错误率
                error_rate = self._stats["total_errors"] / total_requests
                if error_rate > 0.5:  # 错误率超过50%
                    if self.debug:
                        print(f"[STTBase] 不健康：错误率过高 ({error_rate:.1%})")
                    return False
        
        return True
    
    # 统计信息方法
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._stats_lock:
            stats = self._stats.copy()
            
        # 计算运行时间
        if stats["start_time"]:
            stats["runtime"] = time.time() - stats["start_time"]
        else:
            stats["runtime"] = 0
            
        # 计算活动状态
        if stats["last_activity_time"]:
            stats["idle_time"] = time.time() - stats["last_activity_time"]
        else:
            stats["idle_time"] = None
            
        stats["status"] = self.get_status().value
        stats["is_healthy"] = self.is_healthy()
        
        return stats
    
    def reset_stats(self) -> None:
        """重置统计信息"""
        with self._stats_lock:
            self._stats = {
                "start_time": time.time(),
                "total_bytes_sent": 0,
                "total_partial_results": 0,
                "total_final_results": 0,
                "total_errors": 0,
                "last_activity_time": time.time(),
                "connection_count": 0,
                "reconnection_count": 0
            }
        
        if self.debug:
            print("[STTBase] 统计信息已重置")
    
    # 内部辅助方法
    
    def _update_activity(self) -> None:
        """更新最后活动时间"""
        with self._stats_lock:
            self._stats["last_activity_time"] = time.time()
    
    def _increment_stat(self, stat_name: str, increment: int = 1) -> None:
        """增加统计计数"""
        with self._stats_lock:
            if stat_name in self._stats:
                self._stats[stat_name] += increment
    
    def _handle_partial_result(self, text: str, language_code: str = None) -> None:
        """
        处理部分结果的通用逻辑
        
        Args:
            text: 识别文本
            language_code: 语言代码，如果为None则使用默认语言
        """
        if not text or not text.strip():
            return
            
        language_code = language_code or self.language
        self._update_activity()
        self._increment_stat("total_partial_results")
        
        if self.debug:
            print(f"[STTBase] 部分结果: '{text[:50]}...' ({language_code})")
        
        try:
            self.on_partial(text, language_code)
        except Exception as e:
            print(f"[STTBase] ❌ 部分结果回调错误: {e}")
            self._increment_stat("total_errors")
    
    def _handle_final_result(self, text: str, language_code: str = None) -> None:
        """
        处理最终结果的通用逻辑
        
        Args:
            text: 识别文本
            language_code: 语言代码，如果为None则使用默认语言
        """
        if not text or not text.strip():
            return
            
        language_code = language_code or self.language
        self._update_activity()
        self._increment_stat("total_final_results")
        
        if self.debug:
            print(f"[STTBase] 最终结果: '{text[:50]}...' ({language_code})")
        
        try:
            self.on_final(text, language_code)
        except Exception as e:
            print(f"[STTBase] ❌ 最终结果回调错误: {e}")
            self._increment_stat("total_errors")
    
    def _handle_error(self, error: Exception, context: str = "") -> None:
        """
        处理错误的通用逻辑
        
        Args:
            error: 异常对象
            context: 错误上下文描述
        """
        self._increment_stat("total_errors")
        error_msg = f"[STTBase] ❌ {context}错误: {error}"
        
        if self.debug:
            print(error_msg)
        
        # 如果是严重错误，更新状态
        if "connection" in str(error).lower() or "timeout" in str(error).lower():
            self._set_status(STTStatus.ERROR)
    
    # 工具方法
    
    def print_stats(self) -> None:
        """打印统计信息"""
        stats = self.get_stats()
        print(f"\n[STTBase] 📊 统计信息:")
        print(f"  状态: {stats['status']}")
        print(f"  运行时间: {stats['runtime']:.1f}s")
        print(f"  发送字节数: {stats['total_bytes_sent']:,}")
        print(f"  部分结果: {stats['total_partial_results']}")
        print(f"  最终结果: {stats['total_final_results']}")
        print(f"  错误次数: {stats['total_errors']}")
        print(f"  连接次数: {stats['connection_count']}")
        print(f"  重连次数: {stats['reconnection_count']}")
        
        if stats['idle_time'] is not None:
            print(f"  空闲时间: {stats['idle_time']:.1f}s")
            
        print(f"  健康状态: {'✅ 健康' if stats['is_healthy'] else '❌ 不健康'}")
        print()


# 用于测试的模拟STT实现
class MockSTTStream(STTStreamBase):
    """模拟STT流，用于测试和开发"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connected = False
    
    def connect(self) -> bool:
        """模拟连接"""
        self._set_status(STTStatus.CONNECTING)
        time.sleep(0.1)  # 模拟连接延迟
        
        self._connected = True
        self._set_status(STTStatus.CONNECTED)
        self._increment_stat("connection_count")
        
        with self._stats_lock:
            self._stats["start_time"] = time.time()
            
        if self.debug:
            print("[MockSTT] 模拟连接成功")
        return True
    
    def push(self, audio_data: bytes) -> bool:
        """模拟音频推送"""
        if not self._connected:
            return False
        
        self._set_status(STTStatus.STREAMING)
        self._increment_stat("total_bytes_sent", len(audio_data))
        self._update_activity()
        
        # 模拟识别结果
        if len(audio_data) > 1000:  # 较大的音频块
            # 随机生成一些测试文本
            import random
            texts = [
                "这是一个测试结果",
                "Hello this is a test",
                "你好世界",
                "How are you today"
            ]
            text = random.choice(texts)
            
            # 随机决定是部分结果还是最终结果
            if random.random() < 0.3:  # 30%概率为最终结果
                self._handle_final_result(text, "zh-CN" if "你好" in text or "测试" in text else "en-US")
            else:
                self._handle_partial_result(text, "zh-CN" if "你好" in text or "测试" in text else "en-US")
        
        return True
    
    def close(self) -> None:
        """模拟关闭连接"""
        self._connected = False
        self._set_status(STTStatus.CLOSED)
        
        if self.debug:
            print("[MockSTT] 模拟连接已关闭")
    
    def _reconnect(self) -> bool:
        """模拟重连"""
        if self.debug:
            print("[MockSTT] 尝试重连...")
        
        self._increment_stat("reconnection_count")
        self.close()
        time.sleep(0.5)  # 模拟重连延迟
        return self.connect()


if __name__ == "__main__":
    # 测试代码
    def test_partial(text: str, lang: str):
        print(f"[Test] 部分结果: {text} ({lang})")
    
    def test_final(text: str, lang: str):
        print(f"[Test] 最终结果: {text} ({lang})")
    
    print("=== STT抽象基类测试 ===")
    
    # 创建模拟STT流
    mock_stt = MockSTTStream(
        on_partial=test_partial,
        on_final=test_final,
        language="zh-CN",
        debug=True
    )
    
    # 测试连接
    print("\n1. 测试连接:")
    success = mock_stt.connect()
    print(f"连接结果: {success}")
    print(f"状态: {mock_stt.get_status()}")
    print(f"健康: {mock_stt.is_healthy()}")
    
    # 测试音频推送
    print("\n2. 测试音频推送:")
    for i in range(3):
        data = b"x" * 2000  # 模拟音频数据
        result = mock_stt.push(data)
        print(f"推送 {i+1}: {result}")
        time.sleep(0.5)
    
    # 显示统计
    print("\n3. 统计信息:")
    mock_stt.print_stats()
    
    # 测试关闭
    print("\n4. 测试关闭:")
    mock_stt.close()
    print(f"最终状态: {mock_stt.get_status()}")