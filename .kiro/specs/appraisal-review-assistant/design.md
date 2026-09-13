# Design Document: 估價書表填寫助手

## 設計原則

1. **數值由程式決定，文字由模型生成。** 等級、修正率、加總、價格一律由確定性規則計算；語言模型只把算好的結果轉成說明並引用出處，另可輔助解析區段範圍文字（結果須人工確認）。
2. **每一格都能追溯。** 建議值、Evidence、Grade_Definition、矩陣查值、Rule_Citation 缺一不可，否則標為待確認而非輸出。
3. **缺漏不等於零。** 空白、`EXEMPT`、`0.00` 是三種狀態，全程分開；任何 `MISSING` 都會阻擋依賴它的計算並在輸出留白。
4. **表上的值不一定是評比值。** 記載值永遠保留，評比值透過 Legal_Override 改寫並註明依據；兩者並列顯示。

## 系統分層

```
資料蒐集層   Segment 範圍 → 設施距離 → Evidence
               │
案件層       Case（表3 已填值、表4 已給值、MISSING 欄位）＋ Legal_Override
               │
規則庫       Regional_Criteria（p.1–5，對象 Segment）＋ Individual_Criteria（p.6–9，對象 Parcel）＋ overrides
               │
計算引擎     判級 → 矩陣 → 小計／總修正 → 表4 串接 → Trial_Price → Price_Reconciliation
             純函式，無 I/O；輸入 Case + Criteria + Evidence + Override，輸出 List[Fill_Suggestion]
               │
自我驗證     以最終值重跑計算引擎，比對已填值
               │
說明層       Bedrock：Fill_Suggestion → 說明＋引用（不產生數值，後驗證攔截）
               │
輸出層       逐格建議＋證據、地圖與距離、缺漏清單、覆寫清單、匯出官方 Excel 三個工作表
```

計算引擎不依賴網路、模型或介面，可完整單元測試；這是把正確性風險與展示風險隔開的邊界。

## 為什麼要兩層、為什麼一起用

| | 區域因素 | 個別因素 |
|---|---|---|
| 基準頁 | p.1–5 | p.6–9 |
| 判定對象 | Segment | Parcel |
| 輸出到 | 表5 → 表4「區域因素調整百分率」 | 表4 項目 7–25 |
| 內容 | 8 大類 29 細項：土地使用管制、交通運輸、自然條件、土地改良、公共建設、特殊設施、環境污染、其他影響因素 | 19 細項：面積、寬度、深度、形狀、臨街、地勢、道路種類、面前道路寬度、接近學校／市場／公園／車站／商圈、嫌惡設施、停車、使用分區、建蔽率、容積率、禁限建 |

兩層是相加的兩段修正，不是二選一：

```
Trial_Price = 正常單價 × (1 + 價格日期調整) ⊕ Total_Regional_Adjustment ⊕ Individual_Sum
```

`⊕` 為相乘或相加，設定項，輸出揭露。表4 項目 1–5 由查估單位填寫，本系統不產生。

**同名細項不是重複修正。** 區域因素問「P002 這個區段離學校多遠 vs P001 這個區段」，個別因素問「樹德段 284 這一筆地離學校多遠 vs 樹德段 1415」。量的對象不同，各判一次各自正確。

**例外只有使用分區、建蔽率、容積率。** 這三項在區段與宗地上是同一個數字，兩邊都填就是同一差異算兩次。題目 p.5 備註明定併入表4，表5 對應三列輸出 `−`。

**容積率是接續，不是重複。** 基準 p.8 備註 2：先在表4 以土地開發分析法試算；若調整不足，剩餘差異補到表5。系統顯示「表4 調了多少 → 為何不足 → 表5 補多少 → 合計」。本案四筆容積率同為 200%，無差異，不需試算也不需補充。

**區段主要道路 ≠ 宗地面前道路。** P001 主要道路八德街 28M（區段層級 → 「優」），但該宗地臨的是 8M 以下巷道（宗地層級 → 面前道路寬度「稍劣／劣」、容積率降為 200%）。兩者不衝突，欄位對應表必須把它們當成兩個欄位。

## 修正率矩陣由公式生成

每個細項的矩陣為等差且反對稱：

```
修正百分比 = (比較標的等級序 − 比準地等級序) × step
step       = Max_Adjustment ÷ (等級數 − 1)
等級序      = 5 級：優 0 … 劣 4；7 級：極優 0 … 極劣 6；2 級：優 0、劣 1；3 級：優 0、普通 1、劣 2
```

以決賽基準表核對：容積率 25 ÷ 4 = 6.25 ✓、其他影響因素 20 ÷ 6 = 3.33 ✓、有無限制建築 50 ÷ 2 = 25 ✓、面前道路寬度 12 ÷ 4 = 3 ✓。規則庫只抄每個細項的 Max_Adjustment 與級距定義，矩陣由公式生成；建置時逐格回歸，差異寫入 `overrides`。

反向級距（嫌惡設施、環境污染：越遠越優）由 Grade_Definition 的級距順序表達，矩陣不變。

### 已核對的 Max_Adjustment

| 層 | 細項 | Max | 級數 | step | 備註 |
|---|---|---:|---:|---:|---|
| 區域 | 都市計畫內外 | 20 | 2 | 20 | |
| 區域 | 使用分區 | 20 | 5 | 5 | 住宅區 = 稍優 |
| 區域 | 建蔽率 | 10 | 5 | 2.5 | 50–60% = 稍劣 |
| 區域 | 容積率 | 25 | 5 | 6.25 | 180–260% = 稍劣 |
| 區域 | 有無禁止建築 | 50 | 2 | 50 | |
| 區域 | 有無限制建築 | 50 | 3 | 25 | |
| 區域 | 其他影響因素 | 20 | 7 | 3.33 | 唯一七級 |
| 個別 | 面積 | 10 | 5 | 2.5 | |
| 個別 | 寬度 | 5 | 5 | 1.25 | |
| 個別 | 深度 | 5 | 5 | 1.25 | 優 14–30m，非單調 |
| 個別 | 形狀 | 5 | 2 | 5 | |
| 個別 | 臨路情形 | 10 | 5 | 2.5 | |
| 個別 | 地勢 | 10 | 2 | 10 | |
| 個別 | 道路種類 | 5 | 5 | 1.25 | |
| 個別 | 面前道路寬度 | 12 | 5 | 3 | |
| 個別 | 嫌惡設施 | 8 | 5 | 2 | 反向 |
| 個別 | 停車方便性 | 5 | 3 | 2.5 | |
| 個別 | 使用分區 | 15 | 5 | 3.75 | |
| 個別 | 建蔽率 | 10 | 5 | 2.5 | |
| 個別 | 容積率 | — | — | — | 土地開發分析法，不查表 |
| 個別 | 有無禁限建 | 50 | 5 | 12.5 | |
| 個別 | 無尾巷 | 5 | 2 | 5 | |

區域因素 p.2–5 的交通、自然條件、土地改良、公共建設、特殊設施、環境污染各細項，與個別因素 p.7–8 的接近學校／市場／公園／車站／商圈，PDF 文字擷取順序打亂，須對照原頁逐格抄錄（任務 2.3）。

## 本案特例：土地使用管制全為 0%

| 區段 | 使用分區 | 建蔽率 | 容積率（表3） | 容積率（評比） | 禁建／限建 |
|---|---|---:|---:|---:|---|
| P001-00 比準地 | 第一種住宅區 | 50% | 260% | **200%** | 無／無 |
| P002-00 | 第一種住宅區 | 50% | 200% | **200%** | 無／無 |
| P003-00 | 第一種住宅區 | 50% | 260% | **200%** | 無／無 |
| P004-00 | 第一種住宅區 | 50% | 260% | **200%** | 無／無 |

四筆同級 → 使用分區、建蔽率、容積率、禁限建修正率均 0%。若照表3 原始值算，P001 260%（普通）vs P002 200%（稍劣）會多出一級 6.25% 的錯誤修正。

**價差全部來自交通運輸、公共建設、特殊設施、環境污染、其他影響因素**，資料蒐集的重心放在這五類。

## 資料模型

### Criteria_Item

```json
{
  "id": "regional.public_facility.school",
  "layer": "regional",
  "group": "公共建設",
  "group_index": 5,
  "name": "接近學校之程度",
  "max_adjustment": 6,
  "grade_count": 5,
  "measure": "自區段邊界至最近國小／國中／高中／大專之直線距離",
  "grades": [
    { "grade": "優",   "rule": { "type": "in_segment_or_range", "unit": "m", "lt": 500 } },
    { "grade": "稍優", "rule": { "type": "range", "unit": "m", "gte": 500,  "lt": 1000 } },
    { "grade": "普通", "rule": { "type": "range", "unit": "m", "gte": 1000, "lt": 1500 } },
    { "grade": "稍劣", "rule": { "type": "range", "unit": "m", "gte": 1500, "lt": 2000 } },
    { "grade": "劣",   "rule": { "type": "range", "unit": "m", "gte": 2000, "or_absent": true } }
  ],
  "overrides": {},
  "source": { "doc": "評價基準明細表.pdf", "page": 4 }
}
```

`rule.type`：`range`、`in_segment_or_range`、`category`、`boolean`、`land_development_analysis`（容積率專用，不生成矩陣）。此範例的 Max 與級距為示意，正式值依任務 2.3 抄錄。

### Evidence

```json
{
  "field": "regional.public_facility.school",
  "segment": "P002-00",
  "value": 350,
  "unit": "m",
  "in_segment": false,
  "facility": { "name": "○○國小", "type": "elementary" },
  "measure": "自區段邊界至設施最近點直線距離",
  "source": { "dataset": "新北市學校位置開放資料", "retrieved": "2026-09-12" },
  "valuation_date": "2022-09-01",
  "temporal_status": "current_data_needs_confirmation"
}
```

`temporal_status`：`verified_at_valuation_date`、`current_data_needs_confirmation`、`unavailable`。量測基準在案件層級設定一次，所有 Evidence 共用。

### Legal_Override

```json
{
  "field": "容積率",
  "scope": "parcel",
  "segment": "P001-00",
  "recorded": "260%",
  "effective": "200%",
  "basis": "宗地臨路為 8 公尺以下巷道，依都市計畫法規容積率降為 200%",
  "source": { "law": null, "status": "pending", "stated_by": "主辦方說明會 2026-09-12" },
  "active": true
}
```

`status` 為 `pending` 時，受影響的 Fill_Suggestion 連帶 `needs_confirmation`。

### Fill_Suggestion

```json
{
  "id": "S-041",
  "location": { "form": "表5-1", "item_id": "regional.public_facility.school", "column": "P002-00" },
  "suggested": "+1.5",
  "grade": { "base": "稍優", "target": "優" },
  "evidence": ["E-017", "E-018"],
  "overrides": [],
  "computation": "P001 區段距最近國小 620m → 稍優；P002 區段內有國小 → 優；矩陣(稍優, 優) = +1.5",
  "citations": [{ "doc": "評價基準明細表.pdf", "page": 4, "item": "接近學校之程度" }],
  "confidence": "needs_confirmation",
  "confidence_reason": "E-017 為 2026 現況資料，時點待確認",
  "explanation": null,
  "final": null
}
```

`confidence`：`determined`（Evidence 齊備且時點已確認）、`needs_confirmation`（Evidence 時點待確認、Override 待確認、邊界待確認）、`manual`（其他影響因素、土地開發分析法）。`final` 由使用者確認後寫入，含值、修改者、時間。

## 計算引擎

每一步是獨立純函式，依序執行：

| 步 | 函式 | 輸入 | 輸出 |
|---|---|---|---|
| 1 | `grade()` | Criteria_Item、原始條件（含 Evidence、Override） | Grade、`MISSING`、或 `manual` |
| 2 | `adjust()` | Criteria_Item、Base Grade、Target Grade | 修正百分比＋計算過程 |
| 3 | `subtotal()` / `total_regional()` | 表5 各細項修正 | 八個小計、Total_Regional_Adjustment |
| 4 | `individual_sum()` | 表4 項目 7–25 | Individual_Sum |
| 5 | `trial_price()` | 正常單價、價格日期調整、區域、個別、疊加方式、捨入 | Trial_Price＋計算式 |
| 6 | `reconcile()` | 三個 Trial_Price、策略、閾值 | 比準地地價＋權重＋計算式 |

規則：

- 步 1 對區域層只讀 Segment 條件、對個別層只讀 Parcel 條件；同名細項不共用輸入。
- 任一 Segment／Parcel 的條件為 `MISSING` → 該細項整列 `MISSING`，不部分計算。
- 表5 使用分區、建蔽率、容積率三列固定 `EXEMPT`；若接續記錄存在，容積率列改為補充量並附記錄。
- 步 3、4 略過 `EXEMPT` 與 `MISSING`；任一 `MISSING` 使該小計標 `MISSING`。
- 步 5 任一輸入 `MISSING` → Trial_Price `MISSING`；步 6 任一 Trial_Price `MISSING` → 不輸出比準地地價，列出阻擋欄位。
- 其他影響因素預設四 Segment 同為普通；級差需附 Evidence 與理由，否則 `grade()` 回 `manual`。

### 其他影響因素：先排序再定級

唯一七級項目（±20，step 3.33），內容為寧適度、人文素質、明星學區、淹水、地震帶、重大工程規劃、聯外動線，無客觀級距。介面流程：

1. 預設四個 Segment 同為「普通」。
2. 使用者可依單一子因素將 Segment 拖曳排序，以 Base_Segment 為錨點指派絕對 Grade。
3. 任何級差必須附 Evidence 與理由（例：比準地區段描述提到捷運開發區 → 重大工程規劃）。
4. 寫入的是每個 Segment 的絕對 Grade；矩陣以〔Base Grade × Target Grade〕查值。

### Price_Reconciliation

| 策略 | 說明 |
|---|---|
| `mean` | 三個 Trial_Price 算術平均 |
| `weighted_by_adjustment` | 權重 ∝ 1 ÷ (1 + \|區域總修正\| + \|個別合計\|)，預設 |
| `drop_outlier` | 剔除總修正率絕對值超過閾值（預設 30%）者後取平均 |

策略、權重、閾值、捨入方式寫入設定並於輸出揭露；法源確認前輸出標示待確認。

## 資料蒐集層

| 要查的 | 候選來源 |
|---|---|
| 國小／國中／高中／大專 | 新北市開放資料、教育部校園位置 |
| 傳統市場／超市／購物中心 | 新北市市場處、OSM |
| 公園／廣場／徒步區 | 新北市景觀處、OSM |
| 火車站／捷運站／客運站／站牌 | TDX 運輸資料流通服務 |
| 交流道 | 高公局、OSM |
| 郵局／醫院／機關 | 政府資料開放平臺、OSM |
| 變電所／高壓鐵塔／瓦斯槽 | 台電、OSM |
| 墓地／殯儀館／火葬場 | 新北市殯葬處 |
| 垃圾場／焚化爐／污水處理場 | 新北市環保局 |
| 區段範圍圖形 | 國土測繪中心地籍圖、地價區段圖 |

流程：區段範圍文字（如「沿樹人街以北、長壽街21巷以西、啟智街14巷以南及樹德街136巷以東」）→ 模型輔助解析候選邊界街道 → 人工確認 → 圖形 → 對每類設施算最近距離 → Evidence。無法確定邊界的區段，其所有距離連帶 `needs_confirmation`。

時點：Valuation_Date 為 2022-09-01。2023 年後才開的設施不能算；只能取得現況資料時標 `current_data_needs_confirmation`，輸出留待人工確認。

## 說明層邊界

輸入給模型的是已完成的 Fill_Suggestion 結構；輸出僅限 `explanation` 字串。約束：

- 提示中明確列出「不得產生或修改任何數字」。
- 輸出後以正則抽取 `explanation` 內所有數值，逐一比對是否存在於該 Fill_Suggestion 的 `suggested`／`grade`／`computation`／Evidence 值；出現未知數值即捨棄說明並退回結構化輸出。

依競賽規範，基礎模型限 AWS 服務提供者，走 Amazon Bedrock。模型另可用於區段範圍文字解析（輸出候選街道清單，人工確認後才進入距離計算）。

## 輸出層

- 每個 Segment 一張卡：地圖、範圍、設施與距離、各細項 Grade。
- 三表逐格檢視：每格顯示建議值與信心狀態，點開見 Evidence、Override、Grade_Definition、矩陣查值、Rule_Citation。
- 缺漏清單與覆寫清單常駐。
- 確認／修改寫回 `final`，完成後觸發自我驗證。
- 匯出：寫入官方 xlsx 的「表3區段勘查表」、「表5-1區域因素明細表(住)」、「表4比較法調查估價表」，其餘 23 個工作表不動；`MISSING` 留白並於備註標示；附設定與清單。

## 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| 計算引擎 | Python，純函式、無 I/O | 可完整單元測試；與現有 `src/` 一致 |
| 規則庫 | JSON + 產生器 | 只抄 Max 與級距，矩陣由公式生成 |
| 地理計算 | shapely／geopandas | 區段圖形與最近距離 |
| Excel 匯出 | openpyxl | 只寫指定工作表 |
| 說明生成、範圍解析 | Amazon Bedrock | 競賽限定 AWS 基礎模型 |
| 介面 | Web 單頁 | Live Demo 需可部署且可錄影 |

## 測試策略

1. **公式回歸**：兩層所有矩陣逐格比對基準表，差異必須為 0 或被記錄為 override。
2. **Legal_Override 前後**：以表3 原始值（P001 260%）跑一次應得 6.25%，以覆寫值跑一次應得 0%，且輸出採覆寫版本。
3. **分層隔離**：同名細項在兩層各判一次不得觸發重複修正；使用分區／建蔽率／容積率在表5 非 `EXEMPT` 且無接續記錄時必須被拒絕。
4. **缺漏傳播**：任一 Segment 條件 `MISSING` → 該細項整列 `MISSING` → 小計 `MISSING` → Trial_Price `MISSING` → 不輸出地價。
5. **往返驗證**：Fill 產出的三表以最終值重跑計算引擎，須 0 個不一致。
6. **邊界**：級距端點值（28m、200m、260%）、反向級距、二級與七級細項、非單調級距（深度）。
7. **說明層**：數值後驗證能攔下含未知數字的輸出。

## 與既有程式碼的關係

`src/import_drive_archive/` 為官方資料匯入管線，任務已完成，與本功能無執行期相依。本功能新增 `src/appraisal_filler/`，不修改該套件。
