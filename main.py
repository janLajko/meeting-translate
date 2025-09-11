# main.py
from __future__ import annotations
import json
import time
from fastapi import FastAPI, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from asr import GoogleSTTStream  # Using mock for translation testing
from translate import translate_en_to_zh_async, get_translation_stats

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
    
    # 移除音频缓冲区 - 改为即时处理以降低延迟
    # audio_buffer = bytearray()
    # audio_buffer_size_threshold = 16000 * 2  # 32KB (约1秒音频数据)
    
    # 发送字幕给前端（content.js 里会渲染）
    def send_payload(en: str, zh: str, is_final: bool):
        print(f"[Backend] Sending payload - EN: '{en}', ZH: '{zh}', Final: {is_final}")
        try:
            data = json.dumps({"en": en, "zh": zh, "isFinal": is_final}, ensure_ascii=False)
        except Exception:
            data = json.dumps({"en": en, "zh": zh, "isFinal": is_final})
        # 将消息添加到队列而不是立即发送
        message_queue.append(('send', data))

    # ASR 回调 - 支持语言检测和智能翻译逻辑
    def on_partial(text: str, language_code: str):
        print(f"[Backend] ✅ ASR partial result received: '{text}' (lang: {language_code}, length: {len(text)})")
        # 不发送Partial结果到前端，只记录日志
        if len(text.strip()) == 0:
            print(f"[Backend] Partial text is empty")

    def on_final(text: str, language_code: str):
        print(f"[Backend] ✅ ASR final result received: '{text}' (lang: {language_code}, length: {len(text)})")
        if len(text.strip()) > 0:
            # 更新语言统计
            language_stats['total_results'] += 1
            if language_code.startswith('zh'):
                language_stats['chinese_count'] += 1
                lang_type = 'Chinese'
            elif language_code.startswith('en'):
                language_stats['english_count'] += 1
                lang_type = 'English'
            else:
                language_stats['other_count'] += 1
                lang_type = 'Other'
            
            # 记录最近的语言检测结果
            language_stats['last_detected_languages'].append({
                'language': language_code,
                'type': lang_type,
                'text_preview': text[:30] + ('...' if len(text) > 30 else ''),
                'timestamp': time.time()
            })
            # 只保留最近10个结果
            if len(language_stats['last_detected_languages']) > 10:
                language_stats['last_detected_languages'].pop(0)
            
            # Final结果：根据语言智能处理翻译
            message_queue.append(('smart_translate', {'text': text, 'language': language_code}))
        else:
            print(f"[Backend] Final text is empty, not processing")

    async def translate_and_update(text: str, retry_count: int = 0):
        """改进的异步翻译并更新结果 - 增加错误处理和监控"""
        max_retries = 1  # 最多重试1次
        
        try:
            print(f"[Backend] 🔄 Starting async translation (attempt {retry_count + 1}): '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # 记录翻译开始时间
            start_time = time.time()
            
            # 调用改进的翻译函数，包含内部重试机制
            zh = await translate_en_to_zh_async(text, max_retries=2)
            
            # 记录翻译耗时
            elapsed_time = time.time() - start_time
            print(f"[Backend] ✅ Translation completed in {elapsed_time:.2f}s: '{text}' -> '{zh}'")
            
            # 验证翻译质量（基本检查）
            if zh == text and len(text) > 10:  # 如果翻译结果与原文相同且原文较长，可能是翻译失败
                print(f"[Backend] ⚠️ Translation may have failed (identical to source), but sending anyway")
            
            # 发送翻译结果
            data = json.dumps({"en": text, "zh": zh, "isFinal": True}, ensure_ascii=False)
            message_queue.append(('send', data))
            
            print(f"[Backend] 📤 Translation queued for sending: {len(zh)} chars")
            
        except asyncio.TimeoutError:
            print(f"[Backend] ⏰ Translation timeout for: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            if retry_count < max_retries:
                print(f"[Backend] 🔄 Retrying translation ({retry_count + 1}/{max_retries})")
                # 延迟重试
                await asyncio.sleep(1.0 * (retry_count + 1))
                await translate_and_update(text, retry_count + 1)
            else:
                print(f"[Backend] ❌ Translation timeout after {max_retries + 1} attempts, sending original text")
                # 发送原文
                data = json.dumps({"en": text, "zh": text, "isFinal": True}, ensure_ascii=False)
                message_queue.append(('send', data))
                
        except Exception as e:
            error_type = type(e).__name__
            print(f"[Backend] ❌ Translation error ({error_type}): {e}")
            
            if retry_count < max_retries:
                print(f"[Backend] 🔄 Retrying translation due to {error_type} ({retry_count + 1}/{max_retries})")
                await asyncio.sleep(1.0 * (retry_count + 1))
                await translate_and_update(text, retry_count + 1)
            else:
                print(f"[Backend] ❌ Translation failed after {max_retries + 1} attempts, sending original text")
                # 发送原文作为最后选择
                data = json.dumps({"en": text, "zh": text, "isFinal": True}, ensure_ascii=False)
                message_queue.append(('send', data))

    async def smart_translate_and_update(text: str, language_code: str, retry_count: int = 0):
        """智能翻译函数 - 根据检测到的语言决定是否翻译"""
        max_retries = 1
        
        try:
            print(f"[Backend] 🔄 Smart translate processing (attempt {retry_count + 1}): '{text[:50]}{'...' if len(text) > 50 else ''}' (lang: {language_code})")
            
            start_time = time.time()
            
            # 根据语言代码智能决定是否翻译
            if language_code.startswith('zh'):  # 中文（zh-CN, zh-TW等）
                # 中文内容直接显示，不翻译
                zh_text = text
                print(f"[Backend] 📝 Chinese detected, displaying original text: '{text}'")
            else:
                # 英文或其他语言，进行翻译
                zh_text = await translate_en_to_zh_async(text, max_retries=2)
                elapsed_time = time.time() - start_time
                print(f"[Backend] 🔄 Translation completed in {elapsed_time:.2f}s: '{text}' -> '{zh_text}'")
            
            # 发送结果
            data = json.dumps({"en": text, "zh": zh_text, "isFinal": True}, ensure_ascii=False)
            message_queue.append(('send', data))
            
            print(f"[Backend] 📤 Smart translation queued for sending: {len(zh_text)} chars (lang: {language_code})")
            
        except Exception as e:
            error_type = type(e).__name__
            print(f"[Backend] ❌ Smart translation error ({error_type}): {e}")
            
            if retry_count < max_retries:
                print(f"[Backend] 🔄 Retrying smart translation ({retry_count + 1}/{max_retries})")
                await asyncio.sleep(1.0 * (retry_count + 1))
                await smart_translate_and_update(text, language_code, retry_count + 1)
            else:
                print(f"[Backend] ❌ Smart translation failed after {max_retries + 1} attempts, sending original text")
                # 发送原文
                data = json.dumps({"en": text, "zh": text, "isFinal": True}, ensure_ascii=False)
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
                
                # 语言检测统计报告
                if language_stats['total_results'] > 0:
                    chinese_pct = (language_stats['chinese_count'] / language_stats['total_results']) * 100
                    english_pct = (language_stats['english_count'] / language_stats['total_results']) * 100
                    other_pct = (language_stats['other_count'] / language_stats['total_results']) * 100
                    print(f"[Backend] 🗣️ Language Stats: Total:{language_stats['total_results']}, "
                          f"Chinese:{language_stats['chinese_count']}({chinese_pct:.1f}%), "
                          f"English:{language_stats['english_count']}({english_pct:.1f}%), "
                          f"Other:{language_stats['other_count']}({other_pct:.1f}%)")
                    
                    # 显示最近的语言检测结果
                    if language_stats['last_detected_languages']:
                        recent = language_stats['last_detected_languages'][-3:]  # 最近3个
                        recent_info = [f"{r['type']}:'{r['text_preview']}'" for r in recent]
                        print(f"[Backend] 🕐 Recent Languages: {', '.join(recent_info)}")
                      
                last_health_check = now
            
            # 检查并处理队列中的消息和翻译任务
            while message_queue:
                try:
                    item = message_queue.pop(0)
                    if isinstance(item, tuple) and len(item) == 2:
                        action, data = item
                        if action == 'translate':
                            # 启动传统异步翻译任务（保留兼容性）
                            asyncio.create_task(translate_and_update(data))
                            print(f"[Backend] 🔄 Started translation task for: '{data}'")
                        elif action == 'smart_translate':
                            # 启动智能翻译任务
                            text = data['text']
                            language = data['language']
                            asyncio.create_task(smart_translate_and_update(text, language))
                            print(f"[Backend] 🧠 Started smart translation task for: '{text}' (lang: {language})")
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
