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
        # FastAPI 的 ws 是异步，这里用线程转异步
        asyncio.run_coroutine_threadsafe(ws.send_text(data), asyncio.get_event_loop())

    # ASR 回调
    def on_partial(text: str):
        print(f"[Backend] ASR partial result: '{text}'")
        zh = translate_en_to_zh(text)
        print(f"[Backend] Translation result: '{zh}'")
        send_payload(text, zh, False)

    def on_final(text: str):
        print(f"[Backend] ASR final result: '{text}'")
        zh = translate_en_to_zh(text)
        print(f"[Backend] Translation result: '{zh}'")
        send_payload(text, zh, True)

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
                # print(f"[Backend] Received audio data: {len(msg['bytes'])} bytes")
                stt.push(msg["bytes"])
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
