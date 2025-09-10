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

    # 发送字幕给前端（content.js 里会渲染）
    def send_payload(en: str, zh: str, is_final: bool):
        print(f"[Backend] Sending payload - EN: '{en}', ZH: '{zh}', Final: {is_final}")
        try:
            data = json.dumps({"en": en, "zh": zh, "isFinal": is_final}, ensure_ascii=False)
        except Exception:
            data = json.dumps({"en": en, "zh": zh, "isFinal": is_final})
        # 使用异步任务发送，避免事件循环错误
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(ws.send_text(data), loop)
        except RuntimeError:
            # 如果没有运行中的事件循环，创建任务
            asyncio.create_task(ws.send_text(data))

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
            # 前端发来的是二进制：16kHz、LINEAR16、单声道 PCM
            msg = await ws.receive()
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
    except Exception as e:
        print(f"[Backend] WebSocket error: {e}")
    finally:
        print("[Backend] Closing STT stream and WebSocket")
        stt.close()
        try:
            await ws.close()
        except Exception:
            pass
