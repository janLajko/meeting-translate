# stt_factory.py
"""
语音识别(STT)工厂模式
统一创建和管理不同的STT引擎实例
"""

from typing import Optional, Dict, Any, Callable
import logging

from stt_base import STTStreamBase
from config import Config, STTEngine


class STTFactory:
    """
    STT工厂类
    
    负责创建和配置不同的STT引擎实例
    支持Google Speech-to-Text和Deepgram
    """
    
    @staticmethod
    def create_stt_stream(
        on_partial: Callable[[str, str], None],
        on_final: Callable[[str, str], None],
        engine: Optional[STTEngine] = None,
        config_override: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> STTStreamBase:
        """
        创建STT流实例
        
        Args:
            on_partial: 部分结果回调函数
            on_final: 最终结果回调函数
            engine: STT引擎类型，如果为None则使用配置中的默认引擎
            config_override: 覆盖默认配置的参数
            **kwargs: 额外的引擎特定参数
            
        Returns:
            STTStreamBase: 创建的STT流实例
            
        Raises:
            ValueError: 不支持的引擎类型
            ImportError: 缺少必要的依赖
            Exception: 配置错误
        """
        # 确定使用的引擎
        if engine is None:
            engine = Config.get_stt_engine()
        
        # 获取基础配置
        base_config = Config.get_stt_config()
        
        # 应用覆盖配置
        if config_override:
            base_config.update(config_override)
        
        # 合并额外参数
        base_config.update(kwargs)
        
        print(f"[STTFactory] 创建STT流: engine={engine.value}")
        
        # 根据引擎类型创建实例
        if engine == STTEngine.GOOGLE:
            return STTFactory._create_google_stt(on_partial, on_final, base_config)
        elif engine == STTEngine.DEEPGRAM:
            return STTFactory._create_deepgram_stt(on_partial, on_final, base_config)
        else:
            raise ValueError(f"不支持的STT引擎: {engine}")
    
    @staticmethod
    def _create_google_stt(
        on_partial: Callable,
        on_final: Callable,
        config: Dict[str, Any]
    ) -> STTStreamBase:
        """创建Google STT流实例"""
        try:
            # 导入Google STT类（需要先适配为符合抽象接口）
            from asr import GoogleSTTStream
            
            # 提取Google STT特定参数
            language = config.get("language", "en-US")
            alt_langs = config.get("alternative_languages", ["zh-CN"])
            sample_rate = config.get("sample_rate", 16000)
            debug = config.get("debug", False)
            
            # 创建Google STT实例
            # 注意：这里可能需要适配器模式，因为原始GoogleSTTStream可能不完全符合接口
            google_stt = GoogleSTTStream(
                on_partial=on_partial,
                on_final=on_final,
                language=language,
                alt_langs=alt_langs
            )
            
            # 如果GoogleSTTStream没有继承STTStreamBase，需要创建适配器
            if not isinstance(google_stt, STTStreamBase):
                return GoogleSTTAdapter(google_stt, on_partial, on_final, language, sample_rate, debug)
            
            return google_stt
            
        except ImportError as e:
            raise ImportError(f"Google STT依赖缺失: {e}")
        except Exception as e:
            raise Exception(f"创建Google STT失败: {e}")
    
    @staticmethod
    def _create_deepgram_stt(
        on_partial: Callable,
        on_final: Callable,
        config: Dict[str, Any]
    ) -> STTStreamBase:
        """创建Deepgram STT流实例"""
        try:
            from deepgram_asr import DeepgramSTTStream
            
            # 验证API密钥
            api_key = config.get("api_key")
            if not api_key:
                raise ValueError("Deepgram API密钥未设置")
            
            # 提取Deepgram特定参数
            deepgram_config = {
                "api_key": api_key,
                "language": config.get("language", "multi"),
                "model": config.get("model", "nova-2"),
                "smart_format": config.get("smart_format", True),
                "interim_results": config.get("interim_results", True),
                "endpointing": config.get("endpointing", 300),
                "sample_rate": config.get("sample_rate", 16000),
                "debug": config.get("debug", False)
            }
            
            # 创建Deepgram STT实例
            return DeepgramSTTStream(
                on_partial=on_partial,
                on_final=on_final,
                **deepgram_config
            )
            
        except ImportError as e:
            raise ImportError(f"Deepgram STT依赖缺失: {e}")
        except Exception as e:
            raise Exception(f"创建Deepgram STT失败: {e}")
    
    @staticmethod
    def get_available_engines() -> Dict[STTEngine, Dict[str, Any]]:
        """
        获取可用的STT引擎及其状态
        
        Returns:
            Dict[STTEngine, Dict[str, Any]]: 引擎状态信息
        """
        engines = {}
        
        # 检查Google STT
        try:
            from asr import GoogleSTTStream
            import google.cloud.speech
            engines[STTEngine.GOOGLE] = {
                "available": True,
                "version": getattr(google.cloud.speech, "__version__", "unknown"),
                "config_valid": bool(Config.GOOGLE_APPLICATION_CREDENTIALS),
                "description": "Google Cloud Speech-to-Text"
            }
        except ImportError:
            engines[STTEngine.GOOGLE] = {
                "available": False,
                "error": "Google Cloud Speech SDK未安装",
                "description": "Google Cloud Speech-to-Text"
            }
        
        # 检查Deepgram STT
        try:
            from deepgram_asr import DEEPGRAM_AVAILABLE, DeepgramSTTStream
            if DEEPGRAM_AVAILABLE:
                engines[STTEngine.DEEPGRAM] = {
                    "available": True,
                    "version": "3.0+",
                    "config_valid": bool(Config.DEEPGRAM_API_KEY),
                    "description": "Deepgram Speech-to-Text"
                }
            else:
                engines[STTEngine.DEEPGRAM] = {
                    "available": False,
                    "error": "Deepgram SDK未安装",
                    "description": "Deepgram Speech-to-Text"
                }
        except ImportError:
            engines[STTEngine.DEEPGRAM] = {
                "available": False,
                "error": "Deepgram模块导入失败",
                "description": "Deepgram Speech-to-Text"
            }
        
        return engines
    
    @staticmethod
    def validate_engine_config(engine: STTEngine) -> Dict[str, Any]:
        """
        验证指定引擎的配置
        
        Args:
            engine: 要验证的引擎
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        result = {
            "engine": engine.value,
            "valid": False,
            "errors": [],
            "warnings": [],
            "config": {}
        }
        
        if engine == STTEngine.GOOGLE:
            # 验证Google STT配置
            if not Config.GOOGLE_APPLICATION_CREDENTIALS:
                result["warnings"].append("GOOGLE_APPLICATION_CREDENTIALS未设置")
            else:
                result["valid"] = True
                result["config"] = {
                    "credentials_path": Config.GOOGLE_APPLICATION_CREDENTIALS,
                    "language": "en-US",
                    "alternative_languages": ["zh-CN"]
                }
        
        elif engine == STTEngine.DEEPGRAM:
            # 验证Deepgram STT配置
            if not Config.DEEPGRAM_API_KEY:
                result["errors"].append("DEEPGRAM_API_KEY必须设置")
            else:
                result["valid"] = True
                result["config"] = {
                    "api_key_set": True,
                    "model": Config.DEEPGRAM_MODEL,
                    "language": Config.DEEPGRAM_LANGUAGE,
                    "smart_format": Config.DEEPGRAM_SMART_FORMAT
                }
        
        return result
    
    @staticmethod
    def print_engine_status():
        """打印所有引擎状态信息"""
        print("\n[STTFactory] 📊 STT引擎状态:")
        
        engines = STTFactory.get_available_engines()
        
        for engine, info in engines.items():
            status = "✅ 可用" if info["available"] else "❌ 不可用"
            print(f"  {engine.value}: {status}")
            print(f"    描述: {info['description']}")
            
            if info["available"]:
                print(f"    版本: {info.get('version', '未知')}")
                config_status = "✅ 有效" if info.get("config_valid", False) else "⚠️ 配置缺失"
                print(f"    配置: {config_status}")
            else:
                print(f"    错误: {info.get('error', '未知错误')}")
            
            print()
        
        # 显示当前默认引擎
        current_engine = Config.get_stt_engine()
        print(f"当前默认引擎: {current_engine.value}")
        
        # 验证当前引擎配置
        validation = STTFactory.validate_engine_config(current_engine)
        if validation["valid"]:
            print("✅ 当前引擎配置有效")
        else:
            print("❌ 当前引擎配置无效:")
            for error in validation["errors"]:
                print(f"  - {error}")
            for warning in validation["warnings"]:
                print(f"  - ⚠️ {warning}")


class GoogleSTTAdapter(STTStreamBase):
    """
    Google STT适配器
    
    如果现有的GoogleSTTStream不符合STTStreamBase接口，
    使用此适配器进行包装
    """
    
    def __init__(self, google_stt_instance, on_partial, on_final, language, sample_rate, debug):
        super().__init__(on_partial, on_final, language, sample_rate, debug)
        self.google_stt = google_stt_instance
        self._connected = False
    
    def connect(self) -> bool:
        """适配连接方法"""
        try:
            # GoogleSTTStream可能没有显式的connect方法
            # 在这种情况下，我们假设创建实例时已经准备好连接
            self._connected = True
            self._set_status(STTStatus.CONNECTED)
            self._increment_stat("connection_count")
            
            with self._stats_lock:
                self._stats["start_time"] = time.time()
            
            return True
        except Exception as e:
            self._handle_error(e, "Google STT连接")
            return False
    
    def push(self, audio_data: bytes) -> bool:
        """适配音频推送方法"""
        if not self._connected:
            return False
        
        try:
            # 调用Google STT的推送方法
            success = self.google_stt.push(audio_data)
            if success:
                self._increment_stat("total_bytes_sent", len(audio_data))
                self._update_activity()
                self._set_status(STTStatus.STREAMING)
            return success
        except Exception as e:
            self._handle_error(e, "Google STT音频推送")
            return False
    
    def close(self) -> None:
        """适配关闭方法"""
        try:
            if hasattr(self.google_stt, 'close'):
                self.google_stt.close()
            self._connected = False
            self._set_status(STTStatus.CLOSED)
        except Exception as e:
            self._handle_error(e, "Google STT关闭")
    
    def _reconnect(self) -> bool:
        """适配重连方法"""
        # Google STT的重连逻辑可能需要重新创建实例
        # 这里简化处理
        self.close()
        time.sleep(1)
        return self.connect()
    
    def is_healthy(self) -> bool:
        """适配健康检查"""
        # 调用基类检查并添加Google STT特定检查
        if not super().is_healthy():
            return False
        
        # 检查Google STT实例状态
        if hasattr(self.google_stt, 'is_healthy'):
            return self.google_stt.is_healthy()
        
        return self._connected


# 便捷函数
def create_stt_stream(
    on_partial: Callable[[str, str], None],
    on_final: Callable[[str, str], None],
    engine: Optional[str] = None,
    **kwargs
) -> STTStreamBase:
    """
    创建STT流的便捷函数
    
    Args:
        on_partial: 部分结果回调
        on_final: 最终结果回调
        engine: 引擎名称字符串 ("google" 或 "deepgram")
        **kwargs: 其他配置参数
        
    Returns:
        STTStreamBase: STT流实例
    """
    if engine:
        try:
            engine_enum = STTEngine(engine.lower())
        except ValueError:
            raise ValueError(f"不支持的引擎: {engine}")
    else:
        engine_enum = None
    
    return STTFactory.create_stt_stream(on_partial, on_final, engine_enum, **kwargs)


if __name__ == "__main__":
    # 测试代码
    def test_partial(text: str, lang: str):
        print(f"[Test] 部分结果: {text} ({lang})")
    
    def test_final(text: str, lang: str):
        print(f"[Test] 最终结果: {text} ({lang})")
    
    print("=== STT工厂模式测试 ===")
    
    # 显示引擎状态
    STTFactory.print_engine_status()
    
    # 测试创建默认引擎
    try:
        print("\n1. 测试创建默认引擎:")
        stt = create_stt_stream(test_partial, test_final, debug=True)
        print(f"创建成功: {type(stt).__name__}")
        print(f"状态: {stt.get_status()}")
        
        # 尝试连接
        if hasattr(stt, 'connect'):
            success = stt.connect()
            print(f"连接结果: {success}")
        
        stt.close()
        
    except Exception as e:
        print(f"创建默认引擎失败: {e}")
    
    # 测试Deepgram引擎（如果可用）
    available_engines = STTFactory.get_available_engines()
    if STTEngine.DEEPGRAM in available_engines and available_engines[STTEngine.DEEPGRAM]["available"]:
        try:
            print("\n2. 测试创建Deepgram引擎:")
            deepgram_stt = create_stt_stream(
                test_partial, 
                test_final, 
                engine="deepgram",
                debug=True
            )
            print(f"创建成功: {type(deepgram_stt).__name__}")
            deepgram_stt.close()
            
        except Exception as e:
            print(f"创建Deepgram引擎失败: {e}")
    
    print("\n测试完成")