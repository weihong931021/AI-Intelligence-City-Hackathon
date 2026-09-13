"""環境設定。憑證走 boto3 預設鏈；開發時從 backend/.env 或 frontend/.env 載入。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

DEFAULT_MODEL_ID = "us.anthropic.claude-sonnet-4-6"  # 此帳號可用的最佳模型（GPT-6 / Claude 5 被擋）


def load_env() -> None:
    """backend/.env 優先，其次 frontend/.env；不覆蓋已存在的環境變數。"""
    for path in (BACKEND_DIR / ".env", REPO_DIR / "frontend" / ".env"):
        if path.exists():
            load_dotenv(path, override=False)


@dataclass(frozen=True)
class Settings:
    model_id: str
    region: str
    max_tokens: int
    cors_origins: list[str]


def get_settings() -> Settings:
    load_env()
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        model_id=os.getenv("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID),
        region=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION") or "us-west-2",
        max_tokens=int(os.getenv("BEDROCK_MAX_TOKENS", "1024")),
        cors_origins=[o.strip() for o in origins.split(",") if o.strip()],
    )
