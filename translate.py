# translate.py
from __future__ import annotations
import requests
import json

def translate_en_to_zh(text: str) -> str:
    """
    使用免费的翻译API进行英译中
    这里使用Microsoft Translator的免费接口作为示例
    """
    if not text:
        return ""
    
    try:
        # 使用Microsoft Translator免费API
        # 注意：生产环境建议申请正式的API Key
        url = "https://api.mymemory.translated.net/get"
        params = {
            'q': text,
            'langpair': 'en|zh-CN'
        }
        
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('responseStatus') == 200:
                return data['responseData']['translatedText']
        
        # 如果API调用失败，返回原文（防止程序崩溃）
        print(f"[Translate] API failed, returning original text: {text}")
        return text
        
    except Exception as e:
        print(f"[Translate] Error: {e}, returning original text: {text}")
        return text
