# main.py
from __future__ import annotations
import json
from fastapi import FastAPI, WebSocket
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from asr import GoogleSTTStream
from translate import translate_en_to_zh

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
    print("[Backend] WebSocket connection accepted")

    # 存储要发送的消息队列
    message_queue = []
    
    # 发送字幕给前端（content.js 里会渲染）
    def send_payload(en: str, zh: str, is_final: bool):
        print(f"[Backend] Sending payload - EN: '{en}', ZH: '{zh}', Final: {is_final}")
        try:
            data = json.dumps({"en": en, "zh": zh, "isFinal": is_final}, ensure_ascii=False)
        except Exception:
            data = json.dumps({"en": en, "zh": zh, "isFinal": is_final})
        # 将消息添加到队列而不是立即发送
        message_queue.append(data)

    # ASR 回调
    def on_partial(text: str):
        print(f"[Backend] ✅ ASR partial result received: '{text}' (length: {len(text)})")
        if len(text.strip()) > 0:
            print(f"[Backend] Translating partial text: '{text}'")
            zh = translate_en_to_zh(text)
            print(f"[Backend] ✅ Partial translation result: '{text}' -> '{zh}'")
            send_payload(text, zh, False)
        else:
            print(f"[Backend] Partial text is empty, not processing")

    def on_final(text: str):
        print(f"[Backend] ✅ ASR final result received: '{text}' (length: {len(text)})")
        if len(text.strip()) > 0:
            print(f"[Backend] Translating final text: '{text}'")
            zh = translate_en_to_zh(text)
            print(f"[Backend] ✅ Final translation result: '{text}' -> '{zh}'")
            send_payload(text, zh, True)
        else:
            print(f"[Backend] Final text is empty, not processing")

    print("[Backend] Creating GoogleSTTStream...")
    stt = GoogleSTTStream(on_partial=on_partial, on_final=on_final)
    print("[Backend] GoogleSTTStream created successfully")

    try:
        while True:
            # 检查并发送队列中的消息
            while message_queue:
                try:
                    data = message_queue.pop(0)
                    await ws.send_text(data)
                    print(f"[Backend] ✅ Sent queued message: {data}")
                except Exception as send_error:
                    print(f"[Backend] ❌ Failed to send queued message: {send_error}")
            
            # 使用短超时接收消息，避免阻塞消息发送
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=0.1)
                if msg["type"] == "websocket.disconnect":
                    print("[Backend] WebSocket disconnect received")
                    break
                if "bytes" in msg and msg["bytes"]:
                    bytes_len = len(msg['bytes'])
                    if bytes_len > 0:
                        print(f"[Backend] 📡 Received audio data: {bytes_len} bytes, pushing to STT stream")
                        stt.push(msg["bytes"])
                    else:
                        print(f"[Backend] ⚠️ Received empty audio data")
                elif "text" in msg and msg["text"] == "PING":
                    print("[Backend] Received PING, sending PONG")
                    await ws.send_text("PONG")
                else:
                    print(f"[Backend] Received unknown message type: {msg}")
            except asyncio.TimeoutError:
                # 超时是正常的，继续循环检查消息队列
                pass
    except Exception as e:
        print(f"[Backend] WebSocket error: {e}")
    finally:
        print("[Backend] Closing STT stream and WebSocket")
        stt.close()
        try:
            await ws.close()
        except Exception:
            pass
