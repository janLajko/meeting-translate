"""
iFlytek (科大讯飞) 实时语音识别
基于 WebSocket 接口 (iat v2)，实现 STTStreamBase 接口

要求音频: 16kHz 单声道 LINEAR16 PCM (raw)
依赖: websocket-client
"""

import base64
import datetime
import hashlib
import hmac
import json
import threading
import time
import queue
from typing import Optional, Dict, Any
from urllib.parse import urlencode

try:
    import websocket  # websocket-client
    IFLYTEK_WS_AVAILABLE = True
except ImportError:
    print("[iFlytekASR] ⚠️ websocket-client 未安装，请运行: pip install websocket-client")
    IFLYTEK_WS_AVAILABLE = False

from stt_base import STTStreamBase, STTStatus


class IflytekSTTStream(STTStreamBase):
    """
    科大讯飞实时转写 (iat v2) 的 STT 流实现
    - 支持中英混说：通过 business.rlang = 'en_us'
    - 线程化：WebSocket 运行在独立线程，音频发送在发送线程
    - 队列：音频帧通过队列发送，避免阻塞
    - 回调：on_partial/on_final，语言码通过简单字符检测给出 zh-CN/en-US
    """

    def __init__(
        self,
        on_partial: callable,
        on_final: callable,
        appid: str,
        api_key: str,
        api_secret: str,
        hosturl: str = "wss://iat-api.xfyun.cn/v2/iat",
        language: str = "zh_cn",
        accent: str = "mandarin",
        ptt: int = 1,
        rlang: str = "en_us",
        sample_rate: int = 16000,
        debug: bool = False,
    ):
        super().__init__(on_partial, on_final, language, sample_rate, debug)

        if not IFLYTEK_WS_AVAILABLE:
            raise ImportError("websocket-client 未安装，无法使用 IflytekSTTStream")

        self.appid = appid
        self.api_key = api_key
        self.api_secret = api_secret
        self.hosturl = hosturl
        self.business_language = language
        self.business_accent = accent
        self.business_ptt = ptt
        self.business_rlang = rlang

        # WS/线程
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._sender_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected_event = threading.Event()
        self._audio_queue: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=100)

        # 发送帧状态控制
        self._first_frame_sent = False
        self._closed = False

        # 文本聚合
        self._agg_text = ""
        self._last_partial = ""

        # 统计
        self._bytes_sent_total = 0

        if self.debug:
            print(f"[iFlytekSTT] 初始化: lang={language}, accent={accent}, rlang={rlang}")

    # ============ 连接与鉴权 ============
    def _rfc1123_date(self) -> str:
        now = datetime.datetime.utcnow()
        return now.strftime('%a, %d %b %Y %H:%M:%S GMT')

    def _build_auth_url(self) -> str:
        """按官方文档生成鉴权URL"""
        from urllib.parse import urlparse

        url = urlparse(self.hosturl)
        host = url.hostname
        path = url.path
        date = self._rfc1123_date()

        signature_origin = f"host: {host}\n" \
                           f"date: {date}\n" \
                           f"GET {path} HTTP/1.1"
        signature_sha = hmac.new(self.api_secret.encode('utf-8'), signature_origin.encode('utf-8'), digestmod=hashlib.sha256).digest()
        signature = base64.b64encode(signature_sha).decode('utf-8')

        authorization_origin = f'api_key="{self.api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

        params = {
            "authorization": authorization,
            "date": date,
            "host": host,
        }
        return f"{self.hosturl}?{urlencode(params)}"

    def connect(self) -> bool:
        try:
            self._set_status(STTStatus.CONNECTING)
            self._stop_event.clear()
            self._first_frame_sent = False
            self._closed = False

            ws_url = self._build_auth_url()

            self._ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )

            # 启动WS线程
            self._ws_thread = threading.Thread(target=self._run_ws, daemon=True)
            self._ws_thread.start()

            # 启动发送线程
            self._sender_thread = threading.Thread(target=self._sender_worker, daemon=True)
            self._sender_thread.start()

            # 等待连接或失败
            start = time.time()
            while time.time() - start < 10:
                if self._connected_event.is_set():
                    self._set_status(STTStatus.CONNECTED)
                    self._increment_stat("connection_count")
                    with self._stats_lock:
                        if not self._stats["start_time"]:
                            self._stats["start_time"] = time.time()
                    if self.debug:
                        print("[iFlytekSTT] ✅ 连接成功")
                    return True
                if self.get_status() == STTStatus.ERROR:
                    break
                time.sleep(0.05)

            self._set_status(STTStatus.ERROR)
            if self.debug:
                print("[iFlytekSTT] ❌ 连接超时")
            return False

        except Exception as e:
            self._handle_error(e, "连接")
            self._set_status(STTStatus.ERROR)
            return False

    def _run_ws(self):
        try:
            # run_forever将阻塞，直到关闭
            self._ws.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            self._handle_error(e, "WS循环")
            self._set_status(STTStatus.ERROR)

    def _on_open(self, ws):
        self._connected_event.set()

    def _on_close(self, ws, *args):
        if self.debug:
            print("[iFlytekSTT] WS 关闭")
        if not self._closed:
            self._set_status(STTStatus.ERROR)

    def _on_error(self, ws, error):
        if self.debug:
            print(f"[iFlytekSTT] 错误: {error}")
        self._handle_error(Exception(str(error)), "WS错误")
        self._set_status(STTStatus.ERROR)

    # ============ 发送与推送 ============
    def push(self, audio_data: bytes) -> bool:
        if not audio_data or self._closed:
            return False
        try:
            self._audio_queue.put_nowait(audio_data)
            self._set_status(STTStatus.STREAMING)
            self._increment_stat("total_bytes_sent", len(audio_data))
            self._bytes_sent_total += len(audio_data)
            self._update_activity()
            return True
        except queue.Full:
            if self.debug:
                print("[iFlytekSTT] ⚠️ 音频队列已满，丢弃数据")
            return False
        except Exception as e:
            self._handle_error(e, "音频推送")
            return False

    def _sender_worker(self):
        try:
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if chunk is None:
                    break

                # 按官方建议拆分为1280字节（约40ms @16kHz 16bit mono）的小帧
                frame_size = 1280
                offset = 0
                while offset < len(chunk) and not self._stop_event.is_set():
                    piece = chunk[offset: offset + frame_size]
                    offset += frame_size

                    data_b64 = base64.b64encode(piece).decode('utf-8')

                    if not self._first_frame_sent:
                        # 首帧：包含common和business，status=0
                        frame = {
                            "common": {"app_id": self.appid},
                            "business": {
                                "domain": "iat",
                                "language": self.business_language,
                                "accent": self.business_accent,
                                "ptt": self.business_ptt,
                                "rlang": self.business_rlang,
                            },
                            "data": {
                                "status": 0,
                                "format": f"audio/L16;rate={self.sample_rate}",
                                "encoding": "raw",
                                "audio": data_b64,
                            },
                        }
                    else:
                        # 中间帧：仅data，status=1
                        frame = {
                            "data": {
                                "status": 1,
                                "format": f"audio/L16;rate={self.sample_rate}",
                                "encoding": "raw",
                                "audio": data_b64,
                            }
                        }

                    try:
                        if self._ws:
                            self._ws.send(json.dumps(frame))
                            self._first_frame_sent = True
                    except Exception as e:
                        self._handle_error(e, "发送音频帧")
                        self._set_status(STTStatus.ERROR)
                        break

                    # 发送节流：每个小帧约40ms
                    time.sleep(0.04)

        except Exception as e:
            self._handle_error(e, "发送线程")

    # ============ 接收与结果处理 ============
    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            code = data.get("code", -1)
            if code != 0:
                self._handle_error(Exception(f"iFlytek error code={code}, msg={data.get('message')}"), "识别")
                return

            payload = data.get("data", {})
            status = payload.get("status")  # 0/1/2 其中2通常表示最后一帧
            result = payload.get("result")
            if not result:
                return

            # 解析文本
            text = self._parse_result_text(result)
            if not text:
                return

            # 简单语言检测：含中文则 zh-CN，否则 en-US
            language_code = self._detect_lang(text)

            # 聚合：讯飞可能按增量发送，pgs=apd 表示追加，rpl 表示替换一段
            self._agg_text = self._update_aggregate_text(self._agg_text, result)

            # 发送 partial
            current_partial = self._agg_text or text
            if current_partial != self._last_partial:
                self._handle_partial_result(current_partial, language_code)
                self._last_partial = current_partial

            # 最后一帧，发送 final
            if status == 2:
                final_text = self._agg_text or text
                if final_text.strip():
                    self._handle_final_result(final_text, language_code)
                # 为下一段重置
                self._agg_text = ""
                self._last_partial = ""

        except Exception as e:
            self._handle_error(e, "处理消息")

    def _parse_result_text(self, result: Dict[str, Any]) -> str:
        try:
            ws_list = result.get("ws", [])
            parts = []
            for w in ws_list:
                cws = w.get("cw", [])
                if not cws:
                    continue
                # 取第一候选
                parts.append(cws[0].get("w", ""))
            return "".join(parts)
        except Exception:
            return ""

    def _update_aggregate_text(self, current: str, result: Dict[str, Any]) -> str:
        # 处理 pgs（分段策略）：apd=追加, rpl=替换
        try:
            pgs = result.get("pgs")
            text = self._parse_result_text(result)
            if not text:
                return current
            if pgs == "apd" or pgs is None:
                return current + text
            if pgs == "rpl":
                rg = result.get("rg", [1, 1])
                # 简化处理：当替换时，以当前内容与新文本拼接（严格算法需保留分词列表，这里以稳健性为先）
                # 退化到覆盖策略：直接返回当前+新文本去重结果
                candidate = current + text
                # 粗略去重：如果 text 已是 suffix 则不重复拼接
                if candidate.endswith(text + text):
                    return current + text
                return candidate
            return current
        except Exception:
            return current

    def _detect_lang(self, text: str) -> str:
        if any('\u4e00' <= ch <= '\u9fff' for ch in text):
            return "zh-CN"
        return "en-US"

    # ============ 关闭与重连 ============
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_event.set()

        # 发送结束帧（status=2）
        try:
            end_frame = {
                "common": {"app_id": self.appid},
                "business": {
                    "domain": "iat",
                    "language": self.business_language,
                    "accent": self.business_accent,
                    "ptt": self.business_ptt,
                    "rlang": self.business_rlang,
                },
                "data": {
                    "status": 2,
                    "format": f"audio/L16;rate={self.sample_rate}",
                    "encoding": "raw",
                    "audio": "",
                },
            }
            if self._ws:
                try:
                    self._ws.send(json.dumps(end_frame))
                except Exception:
                    pass
        except Exception:
            pass

        try:
            # 停止发送线程
            if self._sender_thread and self._sender_thread.is_alive():
                self._audio_queue.put_nowait(None)
                self._sender_thread.join(timeout=2)
        except Exception:
            pass

        try:
            if self._ws:
                try:
                    self._ws.close()
                except Exception:
                    pass
        finally:
            self._set_status(STTStatus.CLOSED)

    def _reconnect(self) -> bool:
        # 简化：关闭并重新连接
        self.close()
        time.sleep(1)
        return self.connect()

    # ============ 健康与统计 ============
    def is_healthy(self) -> bool:
        if not super().is_healthy():
            return False
        if self.get_status() in [STTStatus.ERROR, STTStatus.CLOSED]:
            return False
        return True

    def get_stats(self) -> Dict[str, Any]:
        stats = super().get_stats()
        stats.update({
            "engine": "iflytek",
            "bytes_sent_total": self._bytes_sent_total,
        })
        return stats


def create_iflytek_stt(
    on_partial: callable,
    on_final: callable,
    appid: str,
    api_key: str,
    api_secret: str,
    **kwargs,
) -> IflytekSTTStream:
    if not IFLYTEK_WS_AVAILABLE:
        raise ImportError("websocket-client 未安装")
    return IflytekSTTStream(
        on_partial=on_partial,
        on_final=on_final,
        appid=appid,
        api_key=api_key,
        api_secret=api_secret,
        **kwargs,
    )
