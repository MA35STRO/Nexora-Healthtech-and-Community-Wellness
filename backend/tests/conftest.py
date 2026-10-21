"""Tests always run offline and deterministic: no API key, no Telegram, regardless of backend/.env."""
import os

os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["KAWAN_DB"] = ":memory:"
