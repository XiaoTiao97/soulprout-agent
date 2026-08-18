"""加载 Gateway 相关 .env 文件。"""

from __future__ import annotations

from pathlib import Path


def load_gateway_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / "gateway" / ".env")
    load_dotenv(root / ".env")
