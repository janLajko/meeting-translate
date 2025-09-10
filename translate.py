# translate.py
from __future__ import annotations
import json
import aiohttp
import asyncio
import requests
from typing import Optional
from google.cloud import translate_v2 as translate

def translate_en_to_zh(text: str) -> str:
    """
    使用Google Cloud Translate API进行英译中，如果不可用则降级到MyMemory API
    """
    if not text:
        return ""
    
    # 首先尝试Google Translate
    try:
        translate_client = translate.Client()
        result = translate_client.translate(
            values=[text],
            target_language='zh-CN',
            source_language='en'
        )
        
        if result and len(result) > 0:
            translation = result[0]['translatedText']
            print(f"[Translate] ✅ Google Translate: '{text}' -> '{translation}'")
            return translation
            
    except Exception as e:
        print(f"[Translate] Google API failed ({e}), trying fallback...")
        
        # 降级到MyMemory API
        try:
            url = "https://api.mymemory.translated.net/get"
            params = {
                'q': text,
                'langpair': 'en|zh-CN'
            }
            
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('responseStatus') == 200:
                    translation = data['responseData']['translatedText']
                    print(f"[Translate] ✅ MyMemory fallback: '{text}' -> '{translation}'")
                    return translation
        except Exception as fallback_error:
            print(f"[Translate] Fallback API also failed: {fallback_error}")
    
    # 如果所有API都失败，返回原文
    print(f"[Translate] All APIs failed, returning original text: {text}")
    return text


# 翻译缓存
_translation_cache = {}
_max_cache_size = 100

async def translate_en_to_zh_async(text: str) -> str:
    """
    异步翻译函数 - 不阻塞识别流程，首选Google API，降级到MyMemory API
    """
    if not text:
        return ""
    
    # 检查缓存
    if text in _translation_cache:
        print(f"[TranslateAsync] Cache hit: '{text}'")
        return _translation_cache[text]
    
    # 首先尝试Google Translate（异步调用）
    try:
        def _sync_google_translate(text: str) -> str:
            translate_client = translate.Client()
            result = translate_client.translate(
                values=[text],
                target_language='zh-CN',
                source_language='en'
            )
            if result and len(result) > 0:
                return result[0]['translatedText']
            raise Exception("No translation result")
        
        translation = await asyncio.to_thread(_sync_google_translate, text)
        
        # 更新缓存
        if len(_translation_cache) >= _max_cache_size:
            first_key = next(iter(_translation_cache))
            del _translation_cache[first_key]
        
        _translation_cache[text] = translation
        print(f"[TranslateAsync] ✅ Google Translate: '{text}' -> '{translation}'")
        return translation
        
    except Exception as google_error:
        print(f"[TranslateAsync] Google API failed ({google_error}), trying fallback...")
        
        # 降级到MyMemory API（异步）
        try:
            url = "https://api.mymemory.translated.net/get"
            params = {
                'q': text,
                'langpair': 'en|zh-CN'
            }
            
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('responseStatus') == 200:
                            translation = data['responseData']['translatedText']
                            
                            # 更新缓存
                            if len(_translation_cache) >= _max_cache_size:
                                first_key = next(iter(_translation_cache))
                                del _translation_cache[first_key]
                            
                            _translation_cache[text] = translation
                            print(f"[TranslateAsync] ✅ MyMemory fallback: '{text}' -> '{translation}'")
                            return translation
                            
        except Exception as fallback_error:
            print(f"[TranslateAsync] Fallback API also failed: {fallback_error}")
    
    # 如果所有API都失败，返回原文
    print(f"[TranslateAsync] All APIs failed, returning original text: {text}")
    return text


def get_translation_stats() -> dict:
    """获取翻译缓存统计信息"""
    return {
        'cache_size': len(_translation_cache),
        'max_cache_size': _max_cache_size,
        'cache_keys': list(_translation_cache.keys())[-5:]  # 最近5个缓存项
    }
