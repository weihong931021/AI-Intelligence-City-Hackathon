# LandLens 後端（dev.md §6.1）

FastAPI 單一服務，提供聊天與文件辨識；AUTOFILL / compute / export 依 §6.4 加在 `app/api/`。

## 本機啟動

```bash
cd backend
/Users/weihong/.langflow/uv/uv venv .venv --python 3.14   # 第一次
/Users/weihong/.langflow/uv/uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

AWS 憑證：走 boto3 預設鏈，開發時會自動讀 `backend/.env`，找不到再讀 `../frontend/.env`（不覆蓋既有環境變數）。

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | 此 workshop 帳號可用的最佳模型；GPT-6 / Claude 5 被帳號層級擋住 |
| `AWS_DEFAULT_REGION` | `us-west-2` | |
| `BEDROCK_MAX_TOKENS` | `1024` | |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | 逗號分隔 |

## API

- `GET /api/health` → `{ok, model, region}`
- `POST /api/extract-case` body `{name, text, images:[{page, data}]}`：`data` 是 JPEG base64。使用 Bedrock Converse 的結構化 tool 擷取原文欄位，回傳 `{kind, title, summary, fields:[{target,key,value,source,evidence}], warnings}`。`kind` 區分案件、空白範本與參考文件；純文字結果須核對原文證據，掃描圖註明頁次。一次模型呼叫最多 5 張頁面，多批同欄位有衝突時不任選數值。辨識失敗回 502，不回傳假空案件；模型不計算單價或修正率。
- `POST /api/chat` body `{messages:[{role:"user"|"assistant", text}], system?}`，回 `text/event-stream`：
  - `data: {"type":"text","text":"…"}` 逐段
  - `data: {"type":"done"}`
  - `data: {"type":"error","message":"…"}`

## 測試

```bash
.venv/bin/python -m pytest -q
```
