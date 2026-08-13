from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

from studio_env import TELEGRAM_ENV_PATH, load_local_env


def _extract_chat(update: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("message", "channel_post", "my_chat_member"):
        payload = update.get(key)
        if isinstance(payload, dict) and isinstance(payload.get("chat"), dict):
            return payload["chat"]
    return None


def _write_env_value(path: Path, key: str, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    updated = []
    found = False
    for line in lines:
        if line.startswith(f"{key}="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"{key}={value}")
    path.write_bytes(("\n".join(updated) + "\n").encode("utf-8"))


def _write_chat_id(path: Path, chat_id: str) -> None:
    _write_env_value(path, "WUKONG_TELEGRAM_CHAT_ID", chat_id)


def _get_updates(base_url: str) -> list[dict[str, Any]]:
    updates = requests.get(f"{base_url}/getUpdates", timeout=15)
    updates.raise_for_status()
    return updates.json().get("result", [])


def _chats_from_updates(updates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(chat["id"]): chat
        for update in updates
        if (chat := _extract_chat(update))
    }


def _validate_chat_id(base_url: str, bot_id: str, chat_id: str) -> bool:
    if not chat_id:
        return False
    if chat_id == bot_id:
        print("[!] WUKONG_TELEGRAM_CHAT_ID is the bot ID, not your Telegram chat ID.")
        return False
    response = requests.get(f"{base_url}/getChat", params={"chat_id": chat_id}, timeout=15)
    if not response.ok:
        print(f"[!] Existing chat_id is not usable: HTTP {response.status_code}")
        return False
    chat = response.json().get("result", {})
    if str(chat.get("id")) == bot_id or chat.get("is_bot"):
        print("[!] Existing chat_id points to a bot. Use your user/group chat instead.")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Wukong ROM Studio Telegram notifications")
    parser.add_argument("--chat-id", help="Set a known Telegram chat ID manually")
    parser.add_argument("--wait", type=int, default=0, help="Wait this many seconds for a new /start message")
    args = parser.parse_args()

    load_local_env()
    token = os.environ.get("WUKONG_TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        print(f"[!] Missing WUKONG_TELEGRAM_BOT_TOKEN in {TELEGRAM_ENV_PATH}")
        return 1
    base_url = f"https://api.telegram.org/bot{token}"
    me = requests.get(f"{base_url}/getMe", timeout=15)
    me.raise_for_status()
    bot = me.json()["result"]
    username = bot["username"]
    bot_id = str(bot["id"])

    if args.chat_id:
        chat_id = str(args.chat_id).strip()
        if not _validate_chat_id(base_url, bot_id, chat_id):
            return 4
        _write_chat_id(TELEGRAM_ENV_PATH, chat_id)
        print(f"[OK] Telegram configured for @{username}; chat_id={chat_id}")
        return 0

    existing_chat_id = os.environ.get("WUKONG_TELEGRAM_CHAT_ID", "").strip()
    if _validate_chat_id(base_url, bot_id, existing_chat_id):
        print(f"[OK] Telegram already configured for @{username}; chat_id={existing_chat_id}")
        return 0

    deadline = time.monotonic() + max(args.wait, 0)
    chats: dict[str, dict[str, Any]] = {}
    while True:
        chats = _chats_from_updates(_get_updates(base_url))
        if chats or time.monotonic() >= deadline:
            break
        print(f"[*] Waiting for a message to @{username}...")
        time.sleep(3)

    if not chats:
        print(f"[!] No user/group chat found for @{username}.")
        print(f"    Open https://t.me/{username}, send /start or any message, then run:")
        print("    python configure_telegram.py --wait 60")
        return 2
    if len(chats) > 1:
        print("[!] Multiple chats found. Set WUKONG_TELEGRAM_CHAT_ID manually:")
        for chat_id, chat in chats.items():
            print(f"    {chat_id}: {chat.get('type', '-')} {chat.get('username') or chat.get('title') or chat.get('first_name') or ''}")
        return 3
    chat_id = next(iter(chats))
    _write_chat_id(TELEGRAM_ENV_PATH, chat_id)
    print(f"[OK] Telegram configured for @{username}; chat_id={chat_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as exc:
        print(f"[!] Telegram API request failed: {exc}")
        raise SystemExit(1)
