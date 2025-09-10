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


# 翻译缓存和统计
_translation_cache = {}
_max_cache_size = 100
_translation_stats = {
    'total_requests': 0,
    'cache_hits': 0,
    'google_success': 0,
    'mymemory_success': 0,
    'failures': 0,
    'retries': 0
}

async def translate_en_to_zh_async(text: str, max_retries: int = 2) -> str:
    """
    改进的异步翻译函数 - 增加重试机制和更好的错误处理
    """
    if not text or len(text.strip()) == 0:
        return ""
    
    text = text.strip()
    _translation_stats['total_requests'] += 1
    
    # 检查缓存
    if text in _translation_cache:
        _translation_stats['cache_hits'] += 1
        print(f"[TranslateAsync] 💡 Cache hit: '{text[:30]}{'...' if len(text) > 30 else ''}'")
        return _translation_cache[text]
    
    # 尝试Google Translate（带重试机制）
    for attempt in range(max_retries + 1):
        try:
            print(f"[TranslateAsync] 🔄 Google Translate attempt {attempt + 1}/{max_retries + 1}: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            def _sync_google_translate(text: str) -> str:
                translate_client = translate.Client()
                result = translate_client.translate(
                    values=[text],
                    target_language='zh-CN',
                    source_language='en'
                )
                if result and len(result) > 0:
                    return result[0]['translatedText']
                raise Exception("No translation result from Google API")
            
            # 使用超时控制
            translation = await asyncio.wait_for(
                asyncio.to_thread(_sync_google_translate, text), 
                timeout=5.0  # 5秒超时
            )
            
            # 成功获取翻译
            _translation_stats['google_success'] += 1
            _update_cache(text, translation)
            print(f"[TranslateAsync] ✅ Google Translate success: '{text}' -> '{translation}'")
            return translation
            
        except asyncio.TimeoutError:
            _translation_stats['retries'] += 1
            error_msg = f"Google API timeout (attempt {attempt + 1})"
            print(f"[TranslateAsync] ⏰ {error_msg}")
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避
            else:
                print(f"[TranslateAsync] Google API timeout after {max_retries + 1} attempts, trying fallback...")
                break
        except Exception as google_error:
            _translation_stats['retries'] += 1
            error_msg = f"Google API error: {google_error}"
            print(f"[TranslateAsync] ❌ {error_msg} (attempt {attempt + 1})")
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避
            else:
                print(f"[TranslateAsync] Google API failed after {max_retries + 1} attempts, trying fallback...")
                break
    
    # 降级到MyMemory API（带重试机制）
    for attempt in range(max_retries + 1):
        try:
            print(f"[TranslateAsync] 🔄 MyMemory fallback attempt {attempt + 1}/{max_retries + 1}")
            
            url = "https://api.mymemory.translated.net/get"
            params = {
                'q': text,
                'langpair': 'en|zh-CN'
            }
            
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('responseStatus') == 200:
                            translation = data['responseData']['translatedText']
                            
                            _translation_stats['mymemory_success'] += 1
                            _update_cache(text, translation)
                            print(f"[TranslateAsync] ✅ MyMemory success: '{text}' -> '{translation}'")
                            return translation
                        else:
                            raise Exception(f"MyMemory API error: {data.get('responseDetails', 'Unknown error')}")
                    else:
                        raise Exception(f"MyMemory HTTP {response.status}")
                        
        except Exception as fallback_error:
            _translation_stats['retries'] += 1
            print(f"[TranslateAsync] ❌ MyMemory error: {fallback_error} (attempt {attempt + 1})")
            if attempt < max_retries:
                await asyncio.sleep(0.5 * (attempt + 1))  # 指数退避
    
    # 如果所有API都失败，返回原文
    _translation_stats['failures'] += 1
    print(f"[TranslateAsync] ❌ All translation APIs failed after retries, returning original: {text}")
    return text


def _update_cache(text: str, translation: str):
    """更新翻译缓存"""
    # 如果缓存已满，删除最旧的项目
    if len(_translation_cache) >= _max_cache_size:
        # 删除最旧的缓存项（FIFO）
        first_key = next(iter(_translation_cache))
        del _translation_cache[first_key]
        print(f"[TranslateAsync] 🗑️ Cache evicted oldest entry: '{first_key[:30]}{'...' if len(first_key) > 30 else ''}'")
    
    _translation_cache[text] = translation


def get_translation_stats() -> dict:
    """获取翻译详细统计信息"""
    return {
        'cache_size': len(_translation_cache),
        'max_cache_size': _max_cache_size,
        'total_requests': _translation_stats['total_requests'],
        'cache_hits': _translation_stats['cache_hits'],
        'google_success': _translation_stats['google_success'],
        'mymemory_success': _translation_stats['mymemory_success'],
        'failures': _translation_stats['failures'],
        'retries': _translation_stats['retries'],
        'cache_hit_rate': _translation_stats['cache_hits'] / max(_translation_stats['total_requests'], 1) * 100,
        'success_rate': (_translation_stats['google_success'] + _translation_stats['mymemory_success']) / max(_translation_stats['total_requests'] - _translation_stats['cache_hits'], 1) * 100,
        'recent_cache_keys': list(_translation_cache.keys())[-5:]  # 最近5个缓存项
    }


def reset_translation_stats():
    """重置翻译统计信息"""
    global _translation_stats
    _translation_stats = {
        'total_requests': 0,
        'cache_hits': 0,
        'google_success': 0,
        'mymemory_success': 0,
        'failures': 0,
        'retries': 0
    }
    print("[TranslateAsync] 📊 Translation statistics reset")
