# main.py
from __future__ import annotations
import json
import time
import re
from fastapi import FastAPI, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from asr import GoogleSTTStream  # 使用真实的Google STT进行中英文混合识别
from translate import translate_en_to_zh_async, get_translation_stats

# 语言处理工具函数
def has_sentence_ending_punctuation(text: str) -> bool:
    """检测文本是否包含句子结束标点符号"""
    if not text:
        return False
    
    # 英文标点: . ! ? 
    # 中文标点: 。！？
    # 其他常用标点: ؟ ¿ ¡ ؛ 
    sentence_endings = r'[.!?。！？؟¿¡؛]'
    
    # 检查文本末尾是否有句子结束标点
    stripped_text = text.rstrip()
    if re.search(sentence_endings + r'\s*$', stripped_text):
        return True
    
    # 检查文本中间是否有明显的句子分界
    sentences = re.split(sentence_endings, text)
    # 如果分割后有多个非空部分，说明有句子结束标点
    if len([s for s in sentences if s.strip()]) > 1:
        return True
        
    return False

def contains_chinese_chars(text: str) -> bool:
    """检测文本是否包含中文字符"""
    if not text:
        return False
    
    # CJK统一表意文字范围 (最常用的中文字符)
    # \u4e00-\u9fff: 中日韩统一表意文字
    # \u3400-\u4dbf: 中日韩统一表意文字扩展A
    # \uff00-\uffef: 半角及全角字符
    chinese_pattern = r'[\u4e00-\u9fff\u3400-\u4dbf\uff00-\uffef]'
    
    return bool(re.search(chinese_pattern, text))

def detect_text_language(text: str, stt_language_code: str = None) -> str:
    """智能语言检测 - 结合STT结果和字符分析"""
    if not text:
        return 'unknown'
    
    # 首先检查字符组成
    has_chinese = contains_chinese_chars(text)
    
    # 如果文本包含中文字符，优先判定为中文
    if has_chinese:
        return 'zh-CN' if not stt_language_code or not stt_language_code.startswith('zh') else stt_language_code
    
    # 如果STT明确检测为中文但没有中文字符，可能是误判
    if stt_language_code and stt_language_code.startswith('zh') and not has_chinese:
        print(f"[Language] ⚠️ STT detected Chinese but no Chinese chars found in: '{text[:30]}...'")
        # 降级到基于字符的检测
        return 'en-US'  # 默认英文
    
    # 使用STT的语言检测结果
    if stt_language_code:
        return stt_language_code
    
    # 最后默认为英文
    return 'en-US'

app = FastAPI(title="Gather Subtitles Server (Python)")

# 如需跨域调试
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"],
)

@app.get("/", response_class=PlainTextResponse)
def root():
    return "OK"

@app.websocket("/stream")
async def stream(ws: WebSocket):
    print("[Backend] WebSocket connection attempt")
    await ws.accept()
    print("[Backend] ✅ WebSocket connection accepted")
    
    # 连接统计
    connection_start_time = time.time()
    last_heartbeat = time.time()

    # 存储要发送的消息队列
    message_queue = []
    
    # 语言检测统计
    language_stats = {
        'total_results': 0,
        'chinese_count': 0,
        'english_count': 0,
        'other_count': 0,
        'last_detected_languages': []  # 最近10个检测结果
    }
    
    # 文本缓冲区 - 用于积累partial结果直到检测到标点
    partial_text_buffer = {
        'content': '',
        'language_code': 'en-US',
        'last_update': time.time(),
        'buffer_timeout': 5.0,  # 5秒超时，避免无标点的长句一直缓冲
        'min_chars_for_punctuation_check': 10  # 最少10个字符才检查标点
    }
    
    # 文本去重机制 - 防止相同文本被重复处理
    processed_texts = set()
    last_processed_text = ""
    last_sent_translation = ""
    
    # 移除音频缓冲区 - 改为即时处理以降低延迟
    # audio_buffer = bytearray()
    # audio_buffer_size_threshold = 16000 * 2  # 32KB (约1秒音频数据)
    
    # 注意：已移除旧的send_payload和translate_and_update函数，现在使用smart_translate_and_update统一处理

    def process_text_for_translation(text: str, language_code: str, is_final: bool = False, force_translate: bool = False):
        """处理文本以决定是否触发翻译 - 统一的文本处理逻辑（含去重）"""
        nonlocal last_processed_text, processed_texts
        
        if len(text.strip()) == 0:
            return
        
        # 去重检查 - 防止重复处理相同文本
        text_key = f"{text.strip()}_{is_final}_{language_code}"
        if text_key in processed_texts or text.strip() == last_processed_text:
            print(f"[Backend] 🔄 Skipping duplicate text: '{text[:30]}...', Final: {is_final}")
            return
            
        # 智能语言检测
        detected_language = detect_text_language(text, language_code)
        
        print(f"[Backend] 📝 Processing NEW text: '{text[:50]}{'...' if len(text) > 50 else ''}' "
              f"(STT: {language_code}, Detected: {detected_language}, Final: {is_final}, Force: {force_translate})")
        
        # 决定是否触发翻译 - 更严格的条件
        should_translate = False
        trigger_reason = ""
        
        if is_final:
            should_translate = True
            trigger_reason = "is_final"
        elif force_translate:
            should_translate = True
            trigger_reason = "force_translate"  
        elif has_sentence_ending_punctuation(text) and len(text.strip()) >= partial_text_buffer['min_chars_for_punctuation_check']:
            # 只在partial结果中检测到标点符号时翻译
            if not is_final:  # 确保这是partial结果
                should_translate = True
                trigger_reason = "punctuation_detected"
        
        if should_translate:
            # 记录已处理的文本
            processed_texts.add(text_key)
            last_processed_text = text.strip()
            
            # 限制去重集合大小，防止内存泄露
            if len(processed_texts) > 100:
                # 清理最旧的一半记录
                processed_texts = set(list(processed_texts)[-50:])
            
            print(f"[Backend] 🚀 Triggering translation - Reason: {trigger_reason}")
            
            # 更新语言统计
            language_stats['total_results'] += 1
            if detected_language.startswith('zh'):
                language_stats['chinese_count'] += 1
                lang_type = 'Chinese'
            elif detected_language.startswith('en'):
                language_stats['english_count'] += 1
                lang_type = 'English'
            else:
                language_stats['other_count'] += 1
                lang_type = 'Other'
            
            # 记录最近的语言检测结果
            language_stats['last_detected_languages'].append({
                'language': detected_language,
                'type': lang_type,
                'text_preview': text[:30] + ('...' if len(text) > 30 else ''),
                'timestamp': time.time(),
                'trigger_reason': trigger_reason
            })
            # 只保留最近10个结果
            if len(language_stats['last_detected_languages']) > 10:
                language_stats['last_detected_languages'].pop(0)
            
            # 添加到翻译队列
            message_queue.append(('smart_translate', {'text': text, 'language': detected_language, 'is_final': is_final}))
            
            # 清空缓冲区
            partial_text_buffer['content'] = ''
            partial_text_buffer['last_update'] = time.time()
        else:
            print(f"[Backend] 📋 Not translating - Text: '{text[:30]}...', Length: {len(text)}, Has punct: {has_sentence_ending_punctuation(text)}, Final: {is_final}")

    # ASR 回调 - 支持智能标点触发翻译
    def on_partial(text: str, language_code: str):
        print(f"[Backend] 📄 ASR partial: '{text}' (lang: {language_code}, len: {len(text)})")
        
        if len(text.strip()) == 0:
            return
            
        # 更新缓冲区
        partial_text_buffer['content'] = text
        partial_text_buffer['language_code'] = language_code
        partial_text_buffer['last_update'] = time.time()
        
        # 检查是否需要基于标点符号触发翻译
        process_text_for_translation(text, language_code, is_final=False, force_translate=False)

    def on_final(text: str, language_code: str):
        print(f"[Backend] ✅ ASR final: '{text}' (lang: {language_code}, len: {len(text)})")
        
        if len(text.strip()) > 0:
            # Final结果始终触发翻译
            process_text_for_translation(text, language_code, is_final=True, force_translate=False)
        else:
            print(f"[Backend] Final text is empty, not processing")


    async def smart_translate_and_update(text: str, language_code: str, is_final: bool = True, retry_count: int = 0):
        """智能翻译函数 - 根据检测到的语言决定是否翻译（增强版含去重）"""
        nonlocal last_sent_translation
        max_retries = 1
        
        try:
            # 再次进行语言检测确保准确性（防御性编程）
            final_language = detect_text_language(text, language_code)
            has_chinese = contains_chinese_chars(text)
            
            print(f"[Backend] 🧠 Smart translate (attempt {retry_count + 1}): '{text[:50]}{'...' if len(text) > 50 else ''}' "
                  f"(Input lang: {language_code}, Final lang: {final_language}, Has Chinese chars: {has_chinese})")
            
            start_time = time.time()
            
            # 智能翻译决策 - 使用双重验证
            if final_language.startswith('zh') or has_chinese:
                # 中文内容直接显示，不翻译
                zh_text = text
                print(f"[Backend] 🇨🇳 Chinese content detected - displaying as-is: '{text}'")
                detection_info = f"Lang:{final_language}, Chars:{has_chinese}"
                print(f"[Backend] 🔍 Chinese detection details: {detection_info}")
            else:
                # 英文或其他语言，进行翻译
                print(f"[Backend] 🇺🇸 Non-Chinese content - translating to Chinese: '{text[:30]}...'")
                zh_text = await translate_en_to_zh_async(text, max_retries=2)
                elapsed_time = time.time() - start_time
                print(f"[Backend] ✅ Translation completed in {elapsed_time:.2f}s: '{text}' -> '{zh_text}'")
            
            # 去重检查 - 避免发送相同的翻译结果
            translation_key = f"{text.strip()}_{zh_text.strip()}"
            if translation_key == last_sent_translation:
                print(f"[Backend] 🔄 Skipping duplicate translation result: '{zh_text[:30]}...'")
                return
                
            last_sent_translation = translation_key
            
            # 发送结果
            data = json.dumps({"en": text, "zh": zh_text, "isFinal": is_final}, ensure_ascii=False)
            message_queue.append(('send', data))
            
            # 增强日志记录
            final_status = "FINAL" if is_final else "PARTIAL"
            char_analysis = f"Chinese chars: {has_chinese}, Lang detection: {final_language}"
            print(f"[Backend] 📤 NEW translation queued ({len(zh_text)} chars) - {char_analysis} - Status: {final_status}")
            
        except Exception as e:
            error_type = type(e).__name__
            print(f"[Backend] ❌ Smart translation error ({error_type}): {e}")
            
            if retry_count < max_retries:
                print(f"[Backend] 🔄 Retrying smart translation ({retry_count + 1}/{max_retries})")
                await asyncio.sleep(1.0 * (retry_count + 1))
                await smart_translate_and_update(text, language_code, is_final, retry_count + 1)
            else:
                final_status = "FINAL" if is_final else "PARTIAL"
                print(f"[Backend] ❌ Smart translation failed after {max_retries + 1} attempts, sending original text - Status: {final_status}")
                # 发送原文作为最后选择
                data = json.dumps({"en": text, "zh": text, "isFinal": is_final}, ensure_ascii=False)
                message_queue.append(('send', data))

    print("[Backend] Creating GoogleSTTStream...")
    stt = None
    stt_rebuild_count = 0
    max_rebuild_attempts = 5
    
    def create_stt_stream():
        nonlocal stt, stt_rebuild_count
        try:
            if stt:
                print(f"[Backend] Closing existing STT stream")
                stt.close()
            
            stt_rebuild_count += 1
            print(f"[Backend] Creating STT stream (attempt {stt_rebuild_count})")
            stt = GoogleSTTStream(
                on_partial=on_partial, 
                on_final=on_final,
                language="en-US",
                alt_langs=["zh-CN"]  # 添加简体中文作为备选语言
            )
            print("[Backend] ✅ GoogleSTTStream created successfully")
            return True
        except Exception as e:
            print(f"[Backend] ❌ Failed to create STT stream: {e}")
            return False
    
    def should_rebuild_stt():
        """检查是否需要重建STT流"""
        if not stt:
            return True
        if stt_rebuild_count >= max_rebuild_attempts:
            print(f"[Backend] ⚠️ Max STT rebuild attempts ({max_rebuild_attempts}) reached")
            return False
        return True
    
    # 初始创建STT流
    if not create_stt_stream():
        print("[Backend] ❌ Failed to create initial STT stream")
        return

    # 健康检查计时器
    last_health_check = time.time()
    health_check_interval = 60  # 每分钟检查一次

    try:
        while True:
            # 定期健康检查和统计报告
            now = time.time()
            if now - last_health_check > health_check_interval:
                if stt:
                    stt_stats = stt.get_stats()
                    print(f"[Backend] 📊 STT Health Check: {stt_stats}")
                    
                    if not stt.is_healthy():
                        print(f"[Backend] ⚠️ STT health check failed, may need rebuild")
                        if should_rebuild_stt():
                            create_stt_stream()
                
                # 翻译统计报告
                try:
                    translation_stats = get_translation_stats()
                    print(f"[Backend] 📈 Translation Stats: Cache:{translation_stats['cache_size']}/{translation_stats['max_cache_size']}, "
                          f"Requests:{translation_stats['total_requests']}, "
                          f"Hit Rate:{translation_stats['cache_hit_rate']:.1f}%, "
                          f"Success Rate:{translation_stats['success_rate']:.1f}%, "
                          f"Failures:{translation_stats['failures']}, "
                          f"Retries:{translation_stats['retries']}")
                except Exception as stats_error:
                    print(f"[Backend] ⚠️ Failed to get translation stats: {stats_error}")
                
                # 连接统计
                connection_duration = now - connection_start_time
                print(f"[Backend] ⏱️ Connection Stats: Duration:{connection_duration:.1f}s, "
                      f"Queue Size:{len(message_queue)}, "
                      f"Last Heartbeat:{now - last_heartbeat:.1f}s ago")
                
                # 检查缓冲区超时 - 处理没有标点的长句
                if (partial_text_buffer['content'] and 
                    now - partial_text_buffer['last_update'] > partial_text_buffer['buffer_timeout'] and
                    len(partial_text_buffer['content'].strip()) > 5):
                    
                    print(f"[Backend] ⏰ Buffer timeout, force translating: '{partial_text_buffer['content'][:50]}...'")
                    process_text_for_translation(
                        partial_text_buffer['content'], 
                        partial_text_buffer['language_code'], 
                        is_final=False, 
                        force_translate=True
                    )
                
                # 语言检测统计报告（增强版）
                if language_stats['total_results'] > 0:
                    chinese_pct = (language_stats['chinese_count'] / language_stats['total_results']) * 100
                    english_pct = (language_stats['english_count'] / language_stats['total_results']) * 100
                    other_pct = (language_stats['other_count'] / language_stats['total_results']) * 100
                    print(f"[Backend] 🗣️ Language Stats: Total:{language_stats['total_results']}, "
                          f"Chinese:{language_stats['chinese_count']}({chinese_pct:.1f}%), "
                          f"English:{language_stats['english_count']}({english_pct:.1f}%), "
                          f"Other:{language_stats['other_count']}({other_pct:.1f}%)")
                    
                    # 显示最近的语言检测结果（增强版）
                    if language_stats['last_detected_languages']:
                        recent = language_stats['last_detected_languages'][-3:]  # 最近3个
                        recent_info = [f"{r['type']}({r['trigger_reason']}):'{r['text_preview']}'" for r in recent]
                        print(f"[Backend] 🕐 Recent Languages: {', '.join(recent_info)}")
                    
                    # 缓冲区状态报告
                    buffer_status = f"Buffer: {len(partial_text_buffer['content'])} chars, Age: {now - partial_text_buffer['last_update']:.1f}s"
                    print(f"[Backend] 📋 {buffer_status}")
                      
                last_health_check = now
            
            # 检查并处理队列中的消息和翻译任务
            while message_queue:
                try:
                    item = message_queue.pop(0)
                    if isinstance(item, tuple) and len(item) == 2:
                        action, data = item
                        if action == 'smart_translate':
                            # 启动智能翻译任务
                            text = data['text']
                            language = data['language']
                            is_final = data.get('is_final', True)  # 默认为True保持兼容性
                            asyncio.create_task(smart_translate_and_update(text, language, is_final))
                            print(f"[Backend] 🧠 Started smart translation task for: '{text}' (lang: {language}, final: {is_final})")
                        elif action == 'send':
                            # 发送消息
                            await ws.send_text(data)
                            print(f"[Backend] ✅ Sent translated message: {data}")
                    else:
                        # 普通消息
                        await ws.send_text(item)
                        print(f"[Backend] ✅ Sent queued message: {item}")
                except Exception as send_error:
                    print(f"[Backend] ❌ Failed to process queued item: {send_error}")
            
            # 使用短超时接收消息，避免阻塞消息发送
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=0.1)
                if msg["type"] == "websocket.disconnect":
                    print("[Backend] WebSocket disconnect received")
                    break
                if "bytes" in msg and msg["bytes"]:
                    bytes_len = len(msg['bytes'])
                    if bytes_len > 0:
                        # 优化音频数据处理 - 添加质量控制和流量管理
                        
                        # 基本音频质量检查（简单的静音检测）
                        audio_data = msg["bytes"]
                        
                        # 检查是否为静音数据（所有字节都接近0）
                        is_likely_silent = all(abs(b - 128) < 10 for b in audio_data[:min(100, len(audio_data))])  # 检查前100字节
                        
                        if is_likely_silent and bytes_len < 1000:  # 小的静音数据包可能不重要
                            print(f"[Backend] 🔇 Skipping likely silent audio data: {bytes_len} bytes")
                        else:
                            # 减少日志频率以降低I/O压力
                            if bytes_len % 32000 == 0:  # 每32KB记录一次
                                print(f"[Backend] 📡 Processing audio data: {bytes_len} bytes")
                            
                            # 智能STT推送 - 减少对不健康流的压力
                            if stt and stt.is_healthy():
                                success = stt.push(audio_data)
                                if not success:
                                    print(f"[Backend] ⚠️ Failed to push {bytes_len} bytes to STT")
                                    # 检查是否需要重建
                                    if not stt.is_healthy() and should_rebuild_stt():
                                        print(f"[Backend] 🔄 STT stream unhealthy, rebuilding...")
                                        if create_stt_stream():
                                            # 重试推送，但不强制
                                            stt.push(audio_data)
                            else:
                                # STT流不健康 - 减少重建频率以避免过度压力
                                if should_rebuild_stt():
                                    if stt:
                                        stats = stt.get_stats()
                                        print(f"[Backend] 📊 STT unhealthy, stats: runtime={stats.get('runtime', 0):.1f}s, "
                                              f"repeat_count={stats.get('repeat_count', 0)}, "
                                              f"queue_size={stats.get('queue_size', 0)}")
                                    
                                    print(f"[Backend] 🔄 Attempting STT stream rebuild...")
                                    if create_stt_stream():
                                        # 只在重建成功后推送
                                        stt.push(audio_data)
                                    else:
                                        print(f"[Backend] ❌ STT rebuild failed, dropping {bytes_len} bytes")
                                else:
                                    # 达到重建上限，丢弃数据以避免内存积累
                                    if bytes_len > 5000:  # 只对大数据包记录日志
                                        print(f"[Backend] 🗑️ STT unavailable, dropping {bytes_len} bytes audio data")
                    else:
                        print(f"[Backend] ⚠️ Received empty audio data")
                elif "text" in msg and msg["text"] == "PING":
                    last_heartbeat = time.time()
                    print("[Backend] 💓 Received heartbeat PING, sending PONG")
                    message_queue.append(('send', "PONG"))
                else:
                    print(f"[Backend] Received unknown message type: {msg}")
            except asyncio.TimeoutError:
                # 超时是正常的，继续循环检查消息队列
                # 同时检查心跳超时（5分钟没有心跳就断开连接）
                if time.time() - last_heartbeat > 300:
                    print("[Backend] ⚠️ Heartbeat timeout, closing connection")
                    break
                pass
    except Exception as e:
        print(f"[Backend] WebSocket error: {e}")
    finally:
        connection_duration = time.time() - connection_start_time
        print(f"[Backend] Connection closed after {connection_duration:.1f} seconds")
        print("[Backend] Closing STT stream and WebSocket")
        stt.close()
        try:
            await ws.close()
        except Exception:
            pass
