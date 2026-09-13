# LandLens 前端

Codex 風格的聊天式介面：一開始是整片空白 + 置中輸入框；一般對話、附件辨識與補資料維持全寬聊天。文件完成後才自動展開右側工作區，也可手動開啟範本預覽。
規格背景見 [`plan/dev.md`](../plan/dev.md)，本目錄只做前端。

## 跑起來

```bash
pnpm install
pnpm dev                          # 預設打後端 /api/chat（vite 代理到 127.0.0.1:8000）
VITE_CHAT_BACKEND=mock pnpm dev   # 純前端模擬，不打任何 API
pnpm exec vitest run              # parser、SSE client、agent、文件匯入與縮放
pnpm build                        # tsc -b && vite build
```

`.env` 放 AWS 憑證給後端用，已在 `.gitignore`。

## 技術棧

- React 19 + Vite 8 + TypeScript + Tailwind v4
- [`@assistant-ui/react`](https://github.com/assistant-ui/assistant-ui) 0.15：`useLocalRuntime` + 自訂 `ChatModelAdapter`，thread 元件以官方 shadcn registry 的 `thread` 為底改寫
- Leaflet + react-leaflet（OSM 底圖，先佔位，之後換法定地圖）
- 沒有路由、沒有狀態管理套件；跨欄狀態只有「目前開哪個面板」

## 使用流程

1. 空白畫面輸入，或按「載入範例」帶入齊全範例；輸入框會隨文字增加高度。
2. 「＋」匯入 Excel（xlsx／xls）、CSV、TSV 或 PDF。附件先在瀏覽器準備文字、儲存格座標及 PDF 頁面影像，按送出才呼叫 `/api/extract-case`。支援含文字、掃描與圖文混合 PDF；每檔最多 10 MB、80,000 字、50 頁。
3. 模型辨識文件種類並抄錄已填欄位，顯示「文件辨識結果」與來源，直接加入「案件資料」。已填案件只詢問缺少的欄位；空白範本／參考文件說明內容，不自動顯示整張空白案件表單。辨識失敗保留附件，可用「重新產生」重試。後續對話沿用辨識結果，使用者文字更正優先。純前端 mock 模式不呼叫文件辨識模型。
4. 「表格範本」可在對話前開啟表3／表4／表5 的 PDF 預覽，或下載 Excel／PDF。右側文件支援觸控板雙指平移、以游標位置為中心的捏合縮放。
5. 右側「模型資訊」按鈕讀取 `/api/health` 顯示實際模型與區域；模擬模式顯示未連接模型。
6. Agent 從整段對話累積欄位：比準地 3 項（地號、估價基準日、地價區段號）＋ 3 個比較標的各 5 項（實例編號、地號、土地正常單價、交易日期、地價區段號）。
7. 缺欄位 → 回覆缺什麼，並在訊息下方附補填表單（也可用文字回）。
8. 齊全 → 產生 `render_table4` tool call；右側自動開「表4」面板，聊天欄留一張摘要卡。
9. 右側分頁列可切 地圖／表3／表4／表5（`⌘1`–`⌘4`，`Esc` 關閉工作區、回到全寬聊天）；手機在文件完成時直接切到文件，仍可切回對話。三張表目前直接輸出 `public/templates/` 的空白官方範本。

## 檔案地圖

```
src/
├── App.tsx                         版面：空白 ↔ 左右分欄（View Transitions 轉場）、工作區狀態
├── index.css                       Tailwind + 深色 token + 轉場動畫
├── agent/
│   ├── schema.ts                   輸入欄位定義、findMissing / mergeCase
│   ├── parse.ts                    自由文字 → CaseInput（含全形正規化）
│   ├── tools.ts                    tool 名稱、Table4Result、collectCase / findLatestTable4
│   ├── select.ts                   相容轉出（= tools.ts）
│   ├── sample.ts                   「載入範例」的兩組文字
│   ├── document-attachments.ts     表格／PDF 文字擷取與附件狀態
│   ├── recognition.ts              文件辨識 API、原文欄位轉換
│   ├── mockAgent.ts                純前端 agent（不打 API）
│   ├── apiAgent.ts / chatApi.ts    先辨識附件，再依案件欄位回覆；不以 LLM 計算金額
│   └── backend.ts                  依 VITE_CHAT_BACKEND 選 mock 或 api
├── components/
│   ├── assistant-ui/thread.tsx     Codex 風格聊天欄（空白／分欄兩種模式）
│   ├── assistant-ui/composer-controls.tsx 案件資料、範本與模型資訊
│   ├── assistant-ui/attachments.tsx 附件檔名、讀取狀態與移除
│   ├── tools/Table4Card.tsx        聊天欄裡的表4 摘要卡（開右側面板、下載）
│   ├── tools/MissingFieldsCard.tsx 缺欄位補填表單
│   └── workspace/                  右側工作區：分頁列、面板清單、Table4Preview、CaseMap
└── lib/utils.ts                    cn()
public/templates/                   表3 / 表4 / 表5 空白官方 xlsx 與 PDF
```

## 還沒做（後端接上後）

- 表4 列 9–34（個別因素、合計、權重、比準地地價）由計算引擎填；目前留白。
- 地圖座標是假的；法定三張地圖由地圖組接入 `workspace/CaseMap.tsx` 的位置。
