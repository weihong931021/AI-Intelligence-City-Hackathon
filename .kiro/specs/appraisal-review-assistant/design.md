# Design Document: Appraisal Review Assistant

## 設計原則

1. **數值由程式決定，文字由模型生成。** 等級、修正率、加總與價格一律由確定性規則計算；語言模型只把已算好的 Finding 轉成說明並引用出處。此原則直接對應命題的「降低人工判讀不一致」與評分中技術可行性佔 30% 的要求。
2. **每個 Finding 都能追溯。** 原值、應為值、計算過程、依據來源缺一不可，否則不輸出。
3. **缺漏不等於零。** 空白欄位與 `−`（免修正）與 `0.00` 是三種不同狀態，全程分開表示。
4. **偏離規則不等於錯誤。** 命題明載「各案件之基準明細表內容可能因個案特性調整」，故規則引擎輸出待確認而非直接判錯。

## 核心發現：修正率矩陣可由公式生成

評價基準明細表中，每個修正細項都是一張「比準地等級 × 比較標的等級」的修正百分比矩陣。經核對官方範例表，該矩陣為等差且反對稱：

```
修正百分比 = (比較標的等級序 − 比準地等級序) × step
step       = Max_Adjustment ÷ (等級數 − 1)
等級序      = 優 0、稍優 1、普通 2、稍劣 3、劣 4
```

以官方範例表核對（`Max_Adjustment → step`）：

| 細項 | Max | step | 驗證 |
|---|---:|---:|---|
| 都市計畫內外（2 級） | 20 | 20 | 優→劣 = 20、劣→優 = −20 |
| 使用分區編定 | 20 | 5 | 優列 0, 5, 10, 15, 20 |
| 建蔽率 | 10 | 2.5 | 優列 0, 2.5, 5, 7.5, 10 |
| 容積率 | 40 | 10 | 優列 0, 10, 20, 30, 40 |
| 主要道路寬度 | 15 | 3.75 | 優列 0, 3.75, 7.5, 11.25, 15 |
| 站牌之接近及密集程度 | 8 | 2 | 優列 0, 2, 4, 6, 8 |
| 接近市場之程度 | 6 | 1.5 | 優列 0, 1.5, 3, 4.5, 6 |
| 接近觀光遊憩設施 | 3 | 0.75 | 優列 0, 0.75, 1.5, 2.25, 3 |
| 停車場地之便利 | 4 | 1 | 優列 0, 1, 2, 3, 4 |

**影響：** 規則庫不必人工抄寫約 25 張 5×5 矩陣（約 600 個數值），只需抄寫每個細項的 `Max_Adjustment` 與 5 段級距定義（約 25 列），其餘由公式生成。

**風險與對策：** 公式是預設生成器，不是規範本身。建置規則庫時必須執行逐格回歸比對（見 Requirement 2.6）；任何不符的儲存格一律以官方基準表數值寫入 `overrides`，並在報告中列出，避免把個案調整誤當成公式適用。

## 系統分層

```
輸入層      Case_Bundle（表1／表5／表4 結構化欄位）
              │  ← 文件擷取為可插拔前置步驟（P1）
規則庫      Criteria_Table（上限值＋級距定義＋overrides）
            Manual_Corpus（手冊切塊＋頁碼）
              │
審查引擎    純函式，輸入 Case_Bundle + Criteria_Table，輸出 List[Finding]
              │
說明層      Bedrock：Finding → 自然語言說明＋引用（不產生數值）
              │
呈現層      三表對照、Finding 標紅、確認流程、匯出勘查表
```

審查引擎不依賴網路、模型或介面，因此可完整單元測試；這是把正確性風險與展示風險隔開的關鍵邊界。

## 資料模型

### Criteria_Item

```json
{
  "id": "public_facility.market_proximity",
  "group": "公共建設",
  "group_index": 4,
  "name": "接近市場之程度",
  "max_adjustment": 6,
  "measure": "至傳統市場、超級市場或超大型購物中心之距離",
  "grades": [
    { "grade": "優",   "rule": { "type": "in_district" } },
    { "grade": "稍優", "rule": { "type": "range", "unit": "m", "lt": 500 } },
    { "grade": "普通", "rule": { "type": "range", "unit": "m", "gte": 500,  "lt": 1000 } },
    { "grade": "稍劣", "rule": { "type": "range", "unit": "m", "gte": 1000, "lt": 1800 } },
    { "grade": "劣",   "rule": { "type": "range", "unit": "m", "gte": 1800, "or_absent": true } }
  ],
  "overrides": {},
  "source": { "doc": "評價基準明細表範例.pdf", "page": 3 }
}
```

`rule.type` 支援 `range`（數值級距）、`in_district`（區段內有）、`category`（類別對應，如使用分區）、`boolean`（有無）。

### Finding

```json
{
  "id": "F-012",
  "kind": "grade_mismatch",
  "severity": "error",
  "location": { "form": "表5-2", "item_id": "public_facility.market_proximity", "column": "比較標的1" },
  "recorded": "普通",
  "expected": "稍優",
  "computation": "表1 記載接近市場距離 350m；基準：未滿 500m 為稍優",
  "citations": [
    { "doc": "評價基準明細表範例.pdf", "page": 3, "item": "接近市場之程度" }
  ],
  "explanation": null,
  "acknowledged": null
}
```

`kind`：`grade_mismatch`、`adjustment_mismatch`、`subtotal_mismatch`、`total_mismatch`、`cross_form_mismatch`、`sum_method_confusion`、`price_mismatch`、`duplicate_adjustment`、`missing_value`、`exempt_vs_zero`。

`severity`：`error`（確定錯誤）、`review`（待確認）、`info`（提醒）。

## 審查引擎：檢查層

每一層是獨立純函式，各自可測，依序執行但互不依賴彼此的輸出。

| 層 | 檢查 | 產生的 Finding |
|---|---|---|
| L1 | 依 Grade_Definition 由原始條件判定應得等級，比對表5 記載 | `grade_mismatch`、`missing_value` |
| L2 | 依 Adjustment_Matrix 取應得修正率，比對表5 記載 | `adjustment_mismatch` |
| L3 | 重算各主要項目 Group_Subtotal | `subtotal_mismatch` |
| L4 | 重算 Total_Regional_Adjustment = Σ Group_Subtotal | `total_mismatch` |
| L5 | 表1 原始條件 ↔ 表5 等級基礎；表5 總修正數 ↔ 表4 區域因素調整百分率；表1／表4 共同欄位 | `cross_form_mismatch` |
| L6 | 表4 Signed_Sum 與 Absolute_Sum 分別重算並檢查是否互相對調 | `sum_method_confusion` |
| L7 | 價格驗算 | `price_mismatch` |
| L8 | 免修正符號與 0.00 混用、同因素重複修正 | `exempt_vs_zero`、`duplicate_adjustment` |

### L7 價格驗算式

以官方範例案件（案號 1140901-99-001）為回歸基準：

```
調整至估價基準日單價 = 土地正常單價 × (1 + 交易日期調整百分率)
                    = 184,763 × (1 + 0.02) = 188,458.26 → 188,459

試算價格 = 調整至估價基準日單價 × (1 + 個別因素合計)
        = 188,459 × (1 + 0.13) = 212,958.67 → 212,958
```

兩式與範本記載值一致，故此案件可直接作為引擎的驗收測試。進位方式（無條件捨去至整數）須寫入設定並在 Finding 中揭露；容差預設 1 元。

### L6 加總方式混用

表4 同時要求「合計」（Signed_Sum）與「調整百分率絕對值加總」（Absolute_Sum）。範例中兩者為 13.00% 與 15.00%。引擎重算兩值後：

- 記載的合計 == 重算的 Absolute_Sum，且記載的絕對值加總 == 重算的 Signed_Sum → 判定對調。
- 兩欄位記載相同數值但重算結果不同 → 判定混用。

此為手冊明列的審查重點，也是最容易被人工忽略的錯誤類型。

## 說明層邊界

輸入給模型的是已完成的 Finding 結構與檢索到的手冊段落；輸出僅限 `explanation` 字串。實作上以下列方式約束：

- 提示中明確列出「不得產生或修改任何數字」。
- 輸出後以正則抽取 `explanation` 內的所有數值，逐一比對是否存在於該 Finding 的 `recorded`／`expected`／`computation`／引用段落中；出現未知數值即捨棄該說明並退回結構化輸出。

此後驗證是必要的，因為評分看的是審查結果可信度，寧可沒有說明也不能有幻覺數字。

依競賽規範，基礎模型限使用 AWS 服務提供者，故說明層與檢索皆走 Amazon Bedrock。

## 呈現層

- 三表對照檢視，Finding 錨定到具體儲存格。
- 每個 Finding 展開顯示：原值、應為值、計算過程、引用頁碼。
- 逐項確認／否決，狀態寫回 Finding。
- 匯出填答完成的勘查表（競賽對地政局組的額外交付要求），並附未解決 Finding 清單。

## 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| 審查引擎 | Python，純函式、無 I/O | 可完整單元測試；與現有 `src/` 一致 |
| 規則庫 | JSON + 產生器 | 人工核對面積小，公式覆蓋其餘 |
| 手冊檢索 | Bedrock Knowledge Base 或本地向量索引 | 依現場環境擇一，介面固定 |
| 說明生成 | Amazon Bedrock | 競賽限定 AWS 基礎模型 |
| 介面 | Web 單頁 | Live Demo 需可部署且可錄影 |

## 測試策略

1. **公式回歸**：以官方基準表全表逐格比對 Matrix_Formula 生成結果，差異必須為 0 或被明確記錄為 override。
2. **黃金案例**：官方範例案件（P002-00）在無錯誤輸入下應產生 0 個 `error` 等級 Finding。
3. **注入錯誤**：對黃金案例逐項注入已知錯誤（改等級、改修正率、改小計、對調兩種加總、改價格），驗證對應層產出且僅產出預期的 Finding。
4. **邊界**：級距端點值、免修正符號、缺漏欄位、兩級距細項。
5. **說明層**：驗證數值後驗證機制能攔下含未知數字的輸出。

## 與既有程式碼的關係

`src/import_drive_archive/` 是官方資料的匯入管線，其任務已完成（資料已備存於 `官方資料/`），與本功能無執行期相依。本功能新增獨立套件，不修改該套件。
