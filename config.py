# config.py
"""
配置管理模块
支持环境变量和默认配置
用于管理STT引擎、翻译服务和其他系统配置
"""

import os
from typing import Optional, Dict, Any
from enum import Enum

# 尝试导入dotenv，如果未安装则忽略
try:
    from dotenv import load_dotenv
    load_dotenv()
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("[Config] python-dotenv not available, using environment variables only")


class STTEngine(Enum):
    """语音识别引擎枚举"""
    GOOGLE = "google"
    DEEPGRAM = "deepgram"
    IFLYTEK = "iflytek"


class Config:
    """系统配置类"""
    
    # STT引擎配置
    STT_ENGINE: str = os.getenv("STT_ENGINE", STTEngine.GOOGLE.value)
    
    # Google STT配置
    GOOGLE_APPLICATION_CREDENTIALS: Optional[str] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # Deepgram配置
    DEEPGRAM_API_KEY: Optional[str] = os.getenv("DEEPGRAM_API_KEY")
    DEEPGRAM_MODEL: str = os.getenv("DEEPGRAM_MODEL", "nova-3")
    DEEPGRAM_LANGUAGE: str = os.getenv("DEEPGRAM_LANGUAGE", "multi")
    DEEPGRAM_SMART_FORMAT: bool = os.getenv("DEEPGRAM_SMART_FORMAT", "true").lower() == "true"
    DEEPGRAM_INTERIM_RESULTS: bool = os.getenv("DEEPGRAM_INTERIM_RESULTS", "true").lower() == "true"
    DEEPGRAM_ENDPOINTING: int = int(os.getenv("DEEPGRAM_ENDPOINTING", "300"))

    # iFlytek（讯飞）配置
    # 去除环境变量中的意外空格/换行，避免鉴权签名失败
    def _env_strip(name: str, default: Optional[str] = None) -> Optional[str]:
        val = os.getenv(name, default)
        return val.strip() if isinstance(val, str) else val

    IFLYTEK_APPID: Optional[str] = _env_strip("IFLYTEK_APPID")
    IFLYTEK_API_KEY: Optional[str] = _env_strip("IFLYTEK_API_KEY")
    IFLYTEK_API_SECRET: Optional[str] = _env_strip("IFLYTEK_API_SECRET")
    # 官方示例与文档推荐使用 ws-api.xfyun.cn
    IFLYTEK_HOSTURL: str = _env_strip("IFLYTEK_HOSTURL", "wss://ws-api.xfyun.cn/v2/iat")
    # 业务参数：默认中文普通话，开启中英混合（rlang=en_us）
    IFLYTEK_LANGUAGE: str = os.getenv("IFLYTEK_LANGUAGE", "zh_cn")
    IFLYTEK_ACCENT: str = os.getenv("IFLYTEK_ACCENT", "mandarin")
    IFLYTEK_PTT: int = int(os.getenv("IFLYTEK_PTT", "1"))
    IFLYTEK_RLANG: str = os.getenv("IFLYTEK_RLANG", "en_us")
    
    # 音频配置
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
    AUDIO_CHUNK_SIZE: int = int(os.getenv("AUDIO_CHUNK_SIZE", "1024"))
    
    # 翻译配置
    TRANSLATION_CACHE_SIZE: int = int(os.getenv("TRANSLATION_CACHE_SIZE", "1000"))
    TRANSLATION_MAX_RETRIES: int = int(os.getenv("TRANSLATION_MAX_RETRIES", "2"))
    
    # WebSocket配置
    WEBSOCKET_HOST: str = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
    WEBSOCKET_PORT: int = int(os.getenv("WEBSOCKET_PORT", "8080"))
    
    # 调试配置
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    
    @classmethod
    def get_stt_engine(cls) -> STTEngine:
        """获取当前配置的STT引擎"""
        try:
            return STTEngine(cls.STT_ENGINE.lower())
        except ValueError:
            print(f"[Config] ⚠️ 未知的STT引擎: {cls.STT_ENGINE}, 使用默认: Google")
            return STTEngine.GOOGLE
    
    @classmethod
    def validate_config(cls) -> Dict[str, Any]:
        """验证配置并返回验证结果"""
        results = {
            "valid": True,
            "warnings": [],
            "errors": [],
            "engine": cls.get_stt_engine()
        }
        
        # 验证STT引擎配置
        if cls.get_stt_engine() == STTEngine.GOOGLE:
            # 在Google Cloud Run环境中，不需要显式设置GOOGLE_APPLICATION_CREDENTIALS
            # Google Client Libraries会自动使用默认服务账号凭据
            # 只有在本地开发且未设置凭据时才提示
            if not cls.GOOGLE_APPLICATION_CREDENTIALS and not cls._is_running_on_gcp():
                results["warnings"].append("GOOGLE_APPLICATION_CREDENTIALS未设置，在本地开发时可能需要设置")
        
        elif cls.get_stt_engine() == STTEngine.DEEPGRAM:
            if not cls.DEEPGRAM_API_KEY:
                results["errors"].append("DEEPGRAM_API_KEY必须设置才能使用Deepgram STT")
                results["valid"] = False
        elif cls.get_stt_engine() == STTEngine.IFLYTEK:
            missing = []
            if not cls.IFLYTEK_APPID:
                missing.append("IFLYTEK_APPID")
            if not cls.IFLYTEK_API_KEY:
                missing.append("IFLYTEK_API_KEY")
            if not cls.IFLYTEK_API_SECRET:
                missing.append("IFLYTEK_API_SECRET")
            if missing:
                results["errors"].append("缺少讯飞配置: " + ", ".join(missing))
                results["valid"] = False
        
        # 验证音频参数
        if cls.AUDIO_SAMPLE_RATE not in [8000, 16000, 22050, 44100, 48000]:
            results["warnings"].append(f"不常见的采样率: {cls.AUDIO_SAMPLE_RATE}Hz")
        
        if cls.AUDIO_CHUNK_SIZE < 512 or cls.AUDIO_CHUNK_SIZE > 8192:
            results["warnings"].append(f"不推荐的音频块大小: {cls.AUDIO_CHUNK_SIZE}")
        
        return results
    
    @classmethod
    def get_stt_config(cls) -> Dict[str, Any]:
        """获取当前STT引擎的配置"""
        engine = cls.get_stt_engine()
        
        base_config = {
            "engine": engine.value,
            "sample_rate": cls.AUDIO_SAMPLE_RATE,
            "chunk_size": cls.AUDIO_CHUNK_SIZE,
            "debug": cls.DEBUG_MODE
        }
        
        if engine == STTEngine.GOOGLE:
            config = {
                **base_config,
                "language": "en-US",
                "alternative_languages": ["zh-CN"],
                "audio_channel_count": 1,
                "running_on_gcp": cls._is_running_on_gcp()
            }
            
            # 只在有显式凭据文件时才设置 credentials_path
            if cls.GOOGLE_APPLICATION_CREDENTIALS:
                config["credentials_path"] = cls.GOOGLE_APPLICATION_CREDENTIALS
            
            return config
        
        elif engine == STTEngine.DEEPGRAM:
            return {
                **base_config,
                "api_key": cls.DEEPGRAM_API_KEY,
                "model": cls.DEEPGRAM_MODEL,
                "language": cls.DEEPGRAM_LANGUAGE,
                "smart_format": cls.DEEPGRAM_SMART_FORMAT,
                "interim_results": cls.DEEPGRAM_INTERIM_RESULTS,
                "endpointing": cls.DEEPGRAM_ENDPOINTING
            }
        elif engine == STTEngine.IFLYTEK:
            return {
                **base_config,
                # 再次strip防御
                "appid": cls._env_strip("IFLYTEK_APPID") or cls.IFLYTEK_APPID,
                "api_key": cls._env_strip("IFLYTEK_API_KEY") or cls.IFLYTEK_API_KEY,
                "api_secret": cls._env_strip("IFLYTEK_API_SECRET") or cls.IFLYTEK_API_SECRET,
                "hosturl": cls.IFLYTEK_HOSTURL,
                "language": cls.IFLYTEK_LANGUAGE,
                "accent": cls.IFLYTEK_ACCENT,
                "ptt": cls.IFLYTEK_PTT,
                "rlang": cls.IFLYTEK_RLANG,
            }
        
        return base_config
    
    @classmethod
    def print_config_summary(cls):
        """打印配置摘要"""
        print("\n[Config] 🔧 系统配置摘要:")
        print(f"  STT引擎: {cls.get_stt_engine().value}")
        print(f"  音频采样率: {cls.AUDIO_SAMPLE_RATE}Hz")
        print(f"  WebSocket: {cls.WEBSOCKET_HOST}:{cls.WEBSOCKET_PORT}")
        print(f"  调试模式: {'开启' if cls.DEBUG_MODE else '关闭'}")
        
        # 验证配置
        validation = cls.validate_config()
        if not validation["valid"]:
            print(f"  ❌ 配置错误: {', '.join(validation['errors'])}")
        elif validation["warnings"]:
            print(f"  ⚠️  配置警告: {', '.join(validation['warnings'])}")
        else:
            print("  ✅ 配置验证通过")
        
        # 显示引擎特定配置
        if cls.get_stt_engine() == STTEngine.DEEPGRAM:
            print(f"  Deepgram模型: {cls.DEEPGRAM_MODEL}")
            print(f"  Deepgram语言: {cls.DEEPGRAM_LANGUAGE}")
        
        print()
    
    @classmethod
    def _is_running_on_gcp(cls) -> bool:
        """
        检测是否运行在Google Cloud Platform上
        
        Returns:
            bool: 如果在GCP上运行返回True，否则返回False
        """
        # 检查常见的GCP环境变量
        gcp_indicators = [
            "GOOGLE_CLOUD_PROJECT",  # 项目ID
            "K_SERVICE",             # Cloud Run服务名
            "GAE_APPLICATION",       # App Engine应用ID
            "FUNCTION_NAME"          # Cloud Functions函数名
        ]
        
        for indicator in gcp_indicators:
            if os.getenv(indicator):
                return True
        
        # 检查GCP元数据服务器
        try:
            import urllib.request
            import urllib.error
            
            # GCP实例都有这个元数据端点
            metadata_url = "http://metadata.google.internal/computeMetadata/v1/"
            req = urllib.request.Request(metadata_url, headers={"Metadata-Flavor": "Google"})
            
            # 设置短超时，避免在非GCP环境中等待太久
            with urllib.request.urlopen(req, timeout=1) as response:
                return response.getcode() == 200
        except (urllib.error.URLError, OSError, Exception):
            # 无法访问元数据服务器，可能不在GCP上
            pass
        
        return False


# 创建全局配置实例
config = Config()

# 如果直接运行此文件，显示配置摘要
if __name__ == "__main__":
    print("=== Meeting Translate 配置管理 ===")
    config.print_config_summary()
    
    # 显示详细配置
    stt_config = config.get_stt_config()
    print("详细STT配置:")
    for key, value in stt_config.items():
        # 隐藏敏感信息
        if "key" in key.lower() or "credentials" in key.lower():
            display_value = "***已设置***" if value else "未设置"
        else:
            display_value = value
        print(f"  {key}: {display_value}")
