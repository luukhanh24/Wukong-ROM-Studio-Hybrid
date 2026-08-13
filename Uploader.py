import collections
import html
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from studio_env import load_local_env


load_local_env()
TELEGRAM_BOT_TOKEN = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("WUKONG_TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_PARSE_MODE = os.environ.get("WUKONG_TELEGRAM_PARSE_MODE", "HTML").strip() or "HTML"
TELEGRAM_TIMEOUT = int(os.environ.get("WUKONG_TELEGRAM_TIMEOUT", "10") or "10")
TELEGRAM_TIMEZONE = os.environ.get("WUKONG_TELEGRAM_TIMEZONE", "Asia/Bangkok").strip() or "Asia/Bangkok"


def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": TELEGRAM_PARSE_MODE,
        "disable_web_page_preview": True,
    }
    try:
        response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
        response.raise_for_status()
        return response.json().get("result", {}).get("message_id")
    except Exception as exc:
        print(f"[!] Telegram notification failed: {exc}")
        return None


def format_time(seconds):
    return f"{int(seconds // 60)}p {int(seconds % 60)}s"


def format_size(size_bytes):
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.2f} GB"


def local_timestamp():
    try:
        now = datetime.now(ZoneInfo(TELEGRAM_TIMEZONE))
    except ZoneInfoNotFoundError:
        if TELEGRAM_TIMEZONE == "Asia/Bangkok":
            now = datetime.now(timezone(timedelta(hours=7)))
        else:
            now = datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %H:%M:%S %z")


def build_notification_message(filename, file_size, build_duration):
    return "\n".join(
        [
            "\u2705 <b>ROM Build Ho\u00e0n T\u1ea5t!</b>",
            f"\U0001f4e6 <b>ROM:</b> {html.escape(filename)}",
            f"\U0001f4e6 <b>Dung l\u01b0\u1ee3ng:</b> {format_size(file_size)}",
            f"\u23f1 <b>Th\u1eddi gian build:</b> {format_time(build_duration)}",
            f"\U0001f552 <b>Ho\u00e0n t\u1ea5t l\u00fac:</b> {local_timestamp()} ({html.escape(TELEGRAM_TIMEZONE)})",
        ]
    )


class BuildNotifier:
    def __init__(self, initial_data=None):
        self.queue = collections.deque()
        if initial_data:
            self.queue.append(initial_data)
        self.lock = threading.Lock()
        self.port = 54322

    def start_server(self):
        def server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                try:
                    server_socket.bind(("127.0.0.1", self.port))
                    server_socket.listen()
                    while True:
                        conn, _ = server_socket.accept()
                        with conn:
                            data = conn.recv(1024).decode("utf-8")
                            if not data:
                                continue
                            try:
                                payload = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            with self.lock:
                                if payload not in self.queue:
                                    self.queue.append(payload)
                except Exception as exc:
                    print(f"[!] Notifier server stopped: {exc}")

        threading.Thread(target=server, daemon=True).start()

    def process_queue(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Notifier started.")
        while True:
            current_task = None
            with self.lock:
                if self.queue:
                    current_task = self.queue.popleft()

            if not current_task:
                time.sleep(1)
                continue

            file_path = current_task.get("file_path")
            build_duration = float(current_task.get("build_duration", 0.0) or 0.0)
            if not file_path:
                continue

            if not os.path.exists(file_path):
                alt_path = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "ROM_BUILD_DONE",
                    os.path.basename(file_path),
                )
                if os.path.exists(alt_path):
                    file_path = alt_path

            if not os.path.exists(file_path):
                print(f"[!] File not found: {file_path}")
                continue

            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            print(f"[*] Sending notification for: {filename}")
            message = build_notification_message(filename, file_size, build_duration)
            if send_telegram_message(message):
                print("[OK] Notification sent.")


def send_to_existing(payload):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(2)
            client.connect(("127.0.0.1", 54322))
            client.sendall(json.dumps(payload).encode("utf-8"))
        return True
    except OSError:
        return False


if __name__ == "__main__":
    if os.name == "nt":
        os.system("")
    file_to_add = sys.argv[1] if len(sys.argv) > 1 else None
    build_duration = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    initial_data = (
        {"file_path": file_to_add, "build_duration": build_duration}
        if file_to_add
        else None
    )

    if initial_data and send_to_existing(initial_data):
        print("Sent to existing notifier.")
        sys.exit(0)

    app = BuildNotifier(initial_data)
    app.start_server()
    try:
        app.process_queue()
    except KeyboardInterrupt:
        print("\nExiting.")
