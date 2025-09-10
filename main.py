# main.py
from __future__ import annotations
import json
import time
from fastapi import FastAPI, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from asr import GoogleSTTStream  # Using mock for translation testing
from translate import translate_en_to_zh_async

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

    # ASR 回调 - 优化翻译逻辑，只发送翻译后的Final结果
    def on_partial(text: str):
        print(f"[Backend] ✅ ASR partial result received: '{text}' (length: {len(text)})")
        # 不发送Partial结果到前端，只记录日志
        if len(text.strip()) == 0:
            print(f"[Backend] Partial text is empty")

    def on_final(text: str):
        print(f"[Backend] ✅ ASR final result received: '{text}' (length: {len(text)})")
        if len(text.strip()) > 0:
            # Final结果：直接进行异步翻译，不先发送英文
            message_queue.append(('translate', text))
        else:
            print(f"[Backend] Final text is empty, not processing")

    async def translate_and_update(text: str):
        """异步翻译并更新结果"""
        try:
            print(f"[Backend] 🔄 Starting async translation for: '{text}'")
            zh = await translate_en_to_zh_async(text)
            print(f"[Backend] ✅ Async translation completed: '{text}' -> '{zh}'")
            
            # 发送翻译更新消息
            data = json.dumps({"en": text, "zh": zh, "isFinal": True}, ensure_ascii=False)
            message_queue.append(('send', data))
        except Exception as e:
            print(f"[Backend] ❌ Async translation failed: {e}")
            # 翻译失败时保持英文显示，不发送更新

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
            stt = GoogleSTTStream(on_partial=on_partial, on_final=on_final)
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
            # 定期健康检查
            now = time.time()
            if now - last_health_check > health_check_interval:
                if stt:
                    stats = stt.get_stats()
                    print(f"[Backend] 📊 STT Health Check: {stats}")
                    
                    if not stt.is_healthy():
                        print(f"[Backend] ⚠️ STT health check failed, may need rebuild")
                        if should_rebuild_stt():
                            create_stt_stream()
                last_health_check = now
            
            # 检查并处理队列中的消息和翻译任务
            while message_queue:
                try:
                    item = message_queue.pop(0)
                    if isinstance(item, tuple) and len(item) == 2:
                        action, data = item
                        if action == 'translate':
                            # 启动异步翻译任务
                            asyncio.create_task(translate_and_update(data))
                            print(f"[Backend] 🔄 Started translation task for: '{data}'")
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
                        print(f"[Backend] 📡 Received audio data: {bytes_len} bytes, pushing to STT immediately")
                        
                        # 即时处理模式 - 直接发送给STT，无缓冲
                        if stt and stt.is_healthy():
                            success = stt.push(msg["bytes"])
                            if not success:
                                print(f"[Backend] ⚠️ Failed to push audio data")
                                # 检查是否需要重建
                                if not stt.is_healthy() and should_rebuild_stt():
                                    print(f"[Backend] 🔄 STT stream unhealthy, rebuilding...")
                                    if create_stt_stream():
                                        stt.push(msg["bytes"])  # 重试推送
                        else:
                            # STT流不健康或不存在，尝试重建
                            if should_rebuild_stt():
                                if stt:
                                    stats = stt.get_stats()
                                    print(f"[Backend] 📊 STT stats before rebuild: {stats}")
                                
                                print(f"[Backend] 🔄 STT stream needs rebuild...")
                                if create_stt_stream():
                                    stt.push(msg["bytes"])  # 重试推送
                            else:
                                print(f"[Backend] ❌ STT stream unavailable and max rebuilds reached")
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
