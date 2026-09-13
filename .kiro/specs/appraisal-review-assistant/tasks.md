# Implementation Plan: 估價書表填寫助手

## Overview

以 Python 3.12 建立計算引擎，前接資料蒐集層，後接 Excel 匯出、說明層與介面。排序原則：**先讓四個區段的表5、表4 算得出來，再讓它好看**。主線是 1 → 2 → 3 → 4 → 5；任務 6 是填表正確性的自我驗證，不可略過；7、8 依剩餘時間加上。標記 `*` 的測試子任務為可選，但 2.4（公式回歸）與 6.1（往返驗證）為必要。

決賽時程 9/12–9/13，交件截止 9/13 13:00。Wave 1–4 為最小可展示範圍：4 個區段的逐格建議＋證據＋匯出。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1. 資料模型與決賽案件"] },
    { "wave": 2, "tasks": ["2. 兩層基準規則庫", "3. 資料蒐集層"] },
    { "wave": 3, "tasks": ["4. 計算引擎"] },
    { "wave": 4, "tasks": ["5. 填表輸出與 Excel 匯出", "6. 自我驗證"] },
    { "wave": 5, "tasks": ["7. 說明層"] },
    { "wave": 6, "tasks": ["8. 介面、部署與交件"] }
  ],
  "dependencies": {
    "1. 資料模型與決賽案件": [],
    "2. 兩層基準規則庫": ["1. 資料模型與決賽案件"],
    "3. 資料蒐集層": ["1. 資料模型與決賽案件"],
    "4. 計算引擎": ["2. 兩層基準規則庫", "3. 資料蒐集層"],
    "5. 填表輸出與 Excel 匯出": ["4. 計算引擎"],
    "6. 自我驗證": ["4. 計算引擎"],
    "7. 說明層": ["4. 計算引擎"],
    "8. 介面、部署與交件": ["5. 填表輸出與 Excel 匯出", "6. 自我驗證", "7. 說明層"]
  }
}
```

此定義為無循環相依圖；同一 wave 的任務可平行排程。

## Tasks

- [ ] 1. 資料模型與決賽案件
  - 建立 `src/appraisal_filler/` 套件、三表結構與決賽案件 JSON。
  - _Dependencies: none_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.3, 4.4_
  - [ ] 1.1 定義資料模型
    - 在 `models.py` 定義 Segment、Parcel、Case（表3／表5／表4 欄位）、Criteria_Item、Evidence、Legal_Override、Fill_Suggestion。
    - 欄位三態：有值、`EXEMPT`、`MISSING`；禁止以 0 或「無」代表後兩者。
    - _Requirements: 1.3_
  - [ ] 1.2 轉錄決賽案件
    - 由 `官方資料/決賽題目_20260912/題目.pdf` 建立 `cases/shulin_2022.json`：4 個 Segment 的表3 已填值（主要道路、平均路寬、分區、都計、建蔽、容積、禁建、限建、建築密度、型態、利用現況、自然條件、土地改良勾選），保留頁碼。
    - 表4 已給值：交易日期、正常單價、價格日期調整率、調整後單價。
    - 所有設施欄位與表4 項目 7–25 為 `MISSING`。
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ] 1.3 內建 Legal_Override
    - 捷運開發區使用分區 → 第一種住宅區（依都市計畫變更前分區）。
    - 四筆宗地容積率評比值 → 200%（臨路 8m 以下巷道），`source.status: pending`。
    - _Requirements: 4.3, 4.4, 4.5_
  - [ ] 1.4 建立欄位對應表
    - 在 `crosswalk.py` 定義表3 → 表5、表5 → 表4 的欄位對應；區段主要道路寬度與宗地面前道路寬度為兩個欄位，不對應。
    - _Requirements: 1.5_
  - [ ]* 1.5 撰寫模型單元測試
    - 三態欄位序列化往返、Legal_Override 啟用／停用。
    - _Requirements: 1.3, 4.6_

- [ ] 2. 兩層基準規則庫
  - 將決賽基準表 p.1–9 轉為 Criteria_Table，矩陣由公式生成。
  - _Dependencies: 1_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  - [ ] 2.1 定義 Criteria_Item schema 與級距型別
    - 在 `criteria.py` 定義 `range`、`in_segment_or_range`、`category`、`boolean`、`land_development_analysis`；支援反向級距與非單調級距（深度）。
    - _Requirements: 2.2, 2.6, 2.7_
  - [ ] 2.2 實作 Matrix_Formula 產生器與 override
    - 支援等級數 2、3、5、7；override 優先於公式。
    - _Requirements: 2.3, 2.5_
  - [ ] 2.3 抄錄兩層 Max_Adjustment 與級距
    - 區域因素 p.1–5：8 大類 29 細項，標 `layer: regional`；其他影響因素 7 級、有無限制建築 3 級、容積率 Max 25。
    - 個別因素 p.6–9：19 細項，標 `layer: individual`；形狀、地勢、無尾巷 2 級；停車 3 級；嫌惡設施反向；容積率標 `land_development_analysis`。
    - design.md 已核對的 Max 直接用；其餘對照原頁逐格抄錄，每項記錄頁碼。
    - _Requirements: 2.1, 2.2, 2.4_
  - [ ] 2.4 公式逐格回歸
    - 對兩層所有矩陣逐格比對基準表，差異寫入 `overrides` 並記錄原因，不得調整公式遷就個案。
    - _Requirements: 2.5_
  - [ ]* 2.5 撰寫規則庫單元測試
    - 覆蓋 2／3／5／7 級、反向級距、非單調級距、級距端點（28m、200m、260%）、override 優先序。
    - _Requirements: 2.3, 2.6_

- [ ] 3. 資料蒐集層
  - 把表3 的 `MISSING` 設施欄位變成 Evidence。
  - _Dependencies: 1_
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 8.6_
  - [ ] 3.1 區段範圍數位化
    - 將 4 個區段的文字範圍轉為圖形；可用 Bedrock 解析候選邊界街道，人工確認後才成為圖形。
    - 無法確定的邊界標示待確認，受影響距離連帶標示。
    - _Requirements: 3.2, 3.7, 8.6_
  - [ ] 3.2 接入設施資料來源
    - 學校、市場、公園、車站、站牌、交流道、服務性設施、變電所、殯葬、廢棄物處理、污染源；每個來源記錄資料集名稱與擷取日期。
    - _Requirements: 3.2, 3.8_
  - [ ] 3.3 距離計算與 Evidence 產出
    - 量測基準在案件層級設定一次（預設：區段邊界至設施最近點直線距離）；設施在區段內時記「本區段內」。
    - 資料日期晚於 2022-09-01 者 `temporal_status: current_data_needs_confirmation`。
    - _Requirements: 3.2, 3.3, 3.4, 3.5_
  - [ ] 3.4 產出補查需求與缺漏清單
    - 每個 `MISSING` 欄位列出設施類別、適用級距、量測基準；無法取得者標 `unavailable`。
    - _Requirements: 3.1, 3.6_

- [ ] 4. 計算引擎
  - 判級 → 矩陣 → 小計／總修正 → 表4 串接 → Trial_Price → Price_Reconciliation，全部純函式。
  - _Dependencies: 2, 3_
  - _Requirements: 5.1–5.10, 6.1–6.8, 7.1, 7.2, 7.4_
  - [ ] 4.1 實作 `grade()` 與 `adjust()`
    - 區域層只讀 Segment 條件、個別層只讀 Parcel 條件；Legal_Override 存在時以評比值判級並保留記載值。
    - 任一 Segment／Parcel 條件 `MISSING` → 該細項整列 `MISSING`。
    - 其他影響因素預設四 Segment 同為普通；級差無 Evidence 與理由時回 `manual`。
    - _Requirements: 5.1, 5.2, 5.3, 5.8, 5.10, 4.2_
  - [ ] 4.2 實作三項例外與容積率接續
    - 表5 使用分區、建蔽率、容積率固定 `EXEMPT`；接續記錄存在時容積率列改為補充量並附記錄。
    - 偵測三項在兩表同時非 `EXEMPT` 且無接續記錄 → 拒絕輸出並標示。
    - _Requirements: 5.4, 5.5, 5.6_
  - [ ] 4.3 實作 `subtotal()`、`total_regional()`、`individual_sum()`
    - 略過 `EXEMPT` 與 `MISSING`；任一 `MISSING` 使該小計 `MISSING`。
    - _Requirements: 5.7, 6.2_
  - [ ] 4.4 實作 `trial_price()` 與 `reconcile()`
    - 表5 總修正數 → 表4 區域因素調整百分率；疊加方式與捨入為設定項並輸出揭露。
    - 三策略 `mean`／`weighted_by_adjustment`／`drop_outlier`；輸出策略、權重、閾值、計算式；法源未確認標待確認。
    - 任一 Trial_Price `MISSING` → 不輸出地價，列出阻擋欄位。
    - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_
  - [ ] 4.5 實作先排序再定級輔助
    - 依單一子因素排序 Segment，以 Base_Segment 為錨點指派絕對 Grade；輸出仍為絕對 Grade。
    - _Requirements: 5.9_
  - [ ] 4.6 組裝 Fill_Suggestion
    - 每個可決定的 `MISSING` 欄位產出建議值、Evidence、Grade、修正率、計算過程、Rule_Citation、信心狀態。
    - _Requirements: 7.1, 7.2, 7.4_
  - [ ]* 4.7 撰寫引擎單元測試
    - Legal_Override 前後（6.25% vs 0%）、同名細項不觸發重複、三項例外觸發拒絕、缺漏傳播到不輸出地價、三種收斂策略。
    - _Requirements: 4.2, 5.3, 5.6, 5.10, 6.8_

- [ ] 5. 填表輸出與 Excel 匯出
  - 逐格建議與官方範本匯出。
  - _Dependencies: 4_
  - _Requirements: 7.3, 7.5, 7.6, 7.7, 7.8_
  - [ ] 5.1 逐格輸出結構
    - 表3／表5／表4 每格：建議值、信心狀態、可展開的 Evidence、Override、Grade_Definition、矩陣查值、Rule_Citation。
    - 確認／修改寫回 `final`，記錄修改者與時間。
    - _Requirements: 7.3, 7.5_
  - [ ] 5.2 寫入官方 xlsx
    - 只寫「表3區段勘查表」、「表5-1區域因素明細表(住)」、「表4比較法調查估價表」三個工作表；其餘不動。
    - `MISSING` 留白並於備註標示待確認。
    - _Requirements: 7.6, 7.7_
  - [ ] 5.3 附清單與設定
    - 缺漏清單、Legal_Override 清單、量測基準、疊加方式、捨入方式、Price_Reconciliation 設定。
    - _Requirements: 7.8_

- [ ] 6. 自我驗證
  - 填完的三表以最終值重跑引擎，須 0 個不一致。
  - _Dependencies: 4_
  - _Requirements: 8.1, 8.2_
  - [ ] 6.1 往返驗證
    - 以 Fill 產出的最終值作為輸入重跑判級、矩陣、小計、總修正、價格串接，任一步不符即標示。
    - _Requirements: 8.1_
  - [ ] 6.2 語意檢查
    - `EXEMPT` 與 `0.00` 混用、表5 總修正數與表4 區域因素調整百分率不一致、同名細項誤代入另一層。
    - _Requirements: 8.2_

- [ ] 7. 說明層
  - Fill_Suggestion → 白話說明，不引入任何新數字。
  - _Dependencies: 4_
  - _Requirements: 8.3, 8.4, 8.5_
  - [ ] 7.1 實作 Bedrock 說明生成
    - 輸入為 Fill_Suggestion 結構，輸出僅限 `explanation` 字串。
    - _Requirements: 8.3, 8.5_
  - [ ] 7.2 實作數值後驗證閘門
    - 抽取說明中所有數值，比對是否存在於該 Fill_Suggestion 的欄位或 Evidence；出現未知數值即捨棄。
    - _Requirements: 8.4_
  - [ ]* 7.3 撰寫說明層測試
    - 驗證閘門能攔下含捏造數字的輸出。
    - _Requirements: 8.4_

- [ ] 8. 介面、部署與交件
  - 完成 Live Demo 與競賽必繳項目。
  - _Dependencies: 5, 6, 7_
  - _Requirements: 7.3_
  - [ ] 8.1 實作 Web 單頁
    - 每個 Segment 一張卡（地圖、範圍、設施距離、各細項 Grade）；三表逐格檢視；缺漏與覆寫清單常駐；其他影響因素排序介面；匯出按鈕。
  - [ ] 8.2 部署可公開存取的 Live Demo
    - 確認基礎模型使用 AWS 服務提供者，未提交任何憑證。
  - [ ] 8.3 錄製 Demo 影片並整理簡報
    - 簡報須含解決方案說明、數據及資料運用、AWS 雲端技術架構圖、使用介面及操作流程。
  - [ ] 8.4 整理交件清單
    - 團隊基本資料、解決方案說明、簡報檔、Live Demo 網址、影片連結、GitHub 連結、填答完成的勘查表（由 5.2 匯出）。

## Notes

- 主線 1 → 2 → 3 → 4 → 5 做完就是「空白表丟進去、系統填完」；時間不足時介面可簡化，但 Fill_Suggestion 的 Evidence 與 Rule_Citation 不可省。
- 任務 2.4 與 6.1 為必要；其餘 `*` 測試可選。
- 任務 3 的資料來源接入是最大的不確定項：先接學校、車站、站牌、市場、公園五類（對應價差最大的交通與公共建設），特殊設施與污染源次之。
- 本計畫不包含選案、指定 4 區段以外的蒐集、其他用地規則庫、文件上傳擷取。
