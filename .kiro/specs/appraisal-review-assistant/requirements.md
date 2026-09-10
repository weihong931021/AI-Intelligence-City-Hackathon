# Requirements Document

## Introduction

本功能定義「AI 輔助不動產估價案件審查」系統的第一版行為：接收**已填寫完成**的估價書表，依評價基準明細表與市價查估作業手冊逐項核算，找出優劣等級誤判、修正率錯誤、加總錯誤與跨表不一致，並對每項發現提供可追溯的依據與建議值。

範圍界定：

- 主軸為**審查已填書表**；「從位置自動蒐集資料輔助填表」不在第一版範圍。
- 第一版鎖定**商業用地**，以官方範例案件（新北市金山區、區段 P002-00、案號 1140901-99-001）為基準案例。
- 系統**不自行產生地價、修正率或土地條件**；所有數值皆須由規則計算或由使用者輸入。

依據文件：

- [命題文件](../../../官方資料/命題文件/【命題文件】地政局-新北市政府AI黑客松競賽.pdf)
- [查估書表範本](../../../官方資料/範例/查估書表範本.pdf)
- [評價基準明細表範例](../../../官方資料/範例/評價基準明細表範例.pdf)
- [土地徵收補償市價查估作業手冊](../../../官方資料/其他參考資料/土地徵收補償市價查估作業手冊.pdf)
- [系統構想與流程](../../../系統構想與流程-討論整理.md)

## Glossary

- **Review_System**：負責書表載入、規則判定、逐項核算、跨表比對、說明生成與結果輸出的功能。
- **Land_Use_Type**：用地類型（商業用地、住宅用地、農業用地、工業用地等）；決定適用的 Criteria_Table。
- **Survey_Form**：表1 地價區段勘查表，記錄地價區段的原始條件（距離、寬度、名稱、區段內外等）。
- **Regional_Factor_Form**：表5 影響地價區域因素分析明細表，記錄各細項的優劣等級與修正百分比。
- **Comparison_Form**：表4 比較法調查估價表，記錄比準地與比較標的的個別因素條件、差異率與試算價格。
- **Case_Bundle**：同一案號下 Survey_Form、Regional_Factor_Form 與 Comparison_Form 的集合。
- **Criteria_Table**：某 Land_Use_Type 適用的評價基準明細表，由多個 Criteria_Item 組成。
- **Criteria_Item**：基準表中的一個修正細項，含所屬主要項目、上限值（Max_Adjustment）、等級定義（Grade_Definition）及量測方式說明。
- **Grade**：優劣等級，序列為 優、稍優、普通、稍劣、劣；部分細項僅有 優、劣 兩級。
- **Grade_Definition**：將原始條件對應到 Grade 的判定依據，可為數值級距（如「500m 以上未滿 1,000m」）或類別對應（如「第二種商業區」）。
- **Max_Adjustment**：Criteria_Item 的修正率上限值（基準表中以醒目標示的數值，如 20、15、6）。
- **Adjustment_Matrix**：某 Criteria_Item 中「比準地 Grade × 比較標的 Grade」對應到修正百分比的矩陣。
- **Matrix_Formula**：由 Max_Adjustment 與等級數推導 Adjustment_Matrix 的公式。
- **Matrix_Override**：個案基準表中偏離 Matrix_Formula 的儲存格，以實際基準表數值為準。
- **Group_Subtotal**：Regional_Factor_Form 中同一主要項目所有細項修正百分比的加總（百分比小計）。
- **Total_Regional_Adjustment**：影響地價區域因素總修正數，為各 Group_Subtotal 的加總。
- **Individual_Factor_Adjustment**：Comparison_Form 中個別因素各調整項目的差異率。
- **Signed_Sum**：差異率的一般加總（含正負號）。
- **Absolute_Sum**：差異率先取絕對值再加總。
- **Exempt_Mark**：書表中表示「免修正」的符號 `−`，與數值 `0.00` 意義不同。
- **Finding**：審查發現，含類型、嚴重度、位置、原值、應為值、計算過程與依據來源。
- **Rule_Citation**：Finding 所引用的依據，含來源文件、頁碼或基準表細項識別。
- **Manual_Corpus**：市價查估作業手冊經切塊並保留頁碼的可檢索內容。

## Requirements

### Requirement 1: 案件載入與欄位結構

**User Story:** As a 審查人員, I want 將已填寫的書表載入系統, so that 後續核算有一致的資料結構可依據。

#### Acceptance Criteria

1. THE Review_System SHALL 接受以結構化格式（表單或 JSON）輸入的 Survey_Form、Regional_Factor_Form 及 Comparison_Form。
2. WHEN Case_Bundle 載入完成, THE Review_System SHALL 記錄案號、年期、地價區段編號、Land_Use_Type 及比準地地號。
3. IF Case_Bundle 缺少三張表中任一張, THEN THE Review_System SHALL 標示可執行的審查範圍並說明受限的檢查項目。
4. IF 欄位值為空白, THEN THE Review_System SHALL 將該欄位標示為缺漏，且不得以 `0` 代入後續計算。
5. THE Review_System SHALL 區分 Exempt_Mark 與數值 `0.00`，並在資料結構中分別表示。

### Requirement 2: 評價基準規則庫

**User Story:** As a 審查人員, I want 系統依適用的基準明細表判定等級與修正率, so that 判定結果具有一致且可查證的依據。

#### Acceptance Criteria

1. THE Review_System SHALL 為每個 Land_Use_Type 維護一份 Criteria_Table。
2. THE Criteria_Item SHALL 包含所屬主要項目、細項名稱、Max_Adjustment、Grade_Definition 及量測方式說明。
3. WHEN Adjustment_Matrix 需要取得, THE Review_System SHALL 依 Matrix_Formula 由 Max_Adjustment 與等級數計算修正百分比。
4. THE Matrix_Formula SHALL 定義為：修正百分比 =（比較標的等級序 − 比準地等級序）×（Max_Adjustment ÷（等級數 − 1））。
5. IF Criteria_Item 定義了 Matrix_Override, THEN THE Review_System SHALL 以 Matrix_Override 的數值取代 Matrix_Formula 的計算結果。
6. WHEN Criteria_Table 建立或更新, THE Review_System SHALL 將 Matrix_Formula 的計算結果與官方基準表逐格比對並回報所有差異儲存格。
7. THE Review_System SHALL 記錄 Criteria_Table 的來源文件與版本，供 Rule_Citation 引用。

### Requirement 3: 優劣等級判定核對

**User Story:** As a 審查人員, I want 系統依原始條件重新判定等級, so that 人工判讀不一致的情形可被發現。

#### Acceptance Criteria

1. WHEN Survey_Form 提供某細項的原始條件, THE Review_System SHALL 依該細項的 Grade_Definition 判定應得 Grade。
2. IF 判定的應得 Grade 與 Regional_Factor_Form 記載的 Grade 不同, THEN THE Review_System SHALL 產生等級誤判的 Finding，並記錄原值、應為值及所依據的級距。
3. IF 原始條件的量測方式無法確認, THEN THE Review_System SHALL 將該細項標示為待確認而非直接判定錯誤。
4. IF 原始條件缺漏, THEN THE Review_System SHALL 產生缺漏的 Finding 並排除該細項的等級核對。
5. THE Review_System SHALL 在 Finding 中記錄距離或數值的單位，且不得將不同量測方式（如直線距離與道路距離）視為等同。

### Requirement 4: 修正率與加總核算

**User Story:** As a 審查人員, I want 系統重算修正率與各層加總, so that 計算或抄填錯誤可被逐項指出。

#### Acceptance Criteria

1. WHEN Regional_Factor_Form 記載某細項的比準地 Grade 與比較標的 Grade, THE Review_System SHALL 依 Adjustment_Matrix 取得應得修正百分比。
2. IF 應得修正百分比與 Regional_Factor_Form 記載的修正百分比不同, THEN THE Review_System SHALL 產生修正率錯誤的 Finding 並附計算過程。
3. THE Review_System SHALL 重算每個主要項目的 Group_Subtotal，並與 Regional_Factor_Form 記載的百分比小計比對。
4. THE Review_System SHALL 重算 Total_Regional_Adjustment 為各 Group_Subtotal 的加總，並與 Regional_Factor_Form 記載的總修正數比對。
5. IF 任一層級的加總結果與記載值不同, THEN THE Review_System SHALL 產生加總錯誤的 Finding 並列出參與加總的細項與數值。
6. IF 某細項標示 Exempt_Mark, THEN THE Review_System SHALL 將該細項排除於加總之外，且不得以 `0` 參與計算。

### Requirement 5: 跨表一致性檢查

**User Story:** As a 審查人員, I want 系統比對三張表之間的對應關係, so that 跨表抄填錯誤可被發現。

#### Acceptance Criteria

1. THE Review_System SHALL 比對 Survey_Form 記載的原始條件與 Regional_Factor_Form 對應細項的 Grade 判定基礎。
2. THE Review_System SHALL 比對 Regional_Factor_Form 的 Total_Regional_Adjustment 與 Comparison_Form 的區域因素調整百分率。
3. IF Total_Regional_Adjustment 與區域因素調整百分率不同, THEN THE Review_System SHALL 產生跨表不一致的 Finding，並同時標示兩張表的位置與數值。
4. THE Review_System SHALL 比對 Survey_Form 與 Comparison_Form 中同時出現的條件欄位（如使用分區、建蔽率、容積率、面前道路寬度、接近設施距離）。
5. IF 同一條件在不同表格記載不同數值, THEN THE Review_System SHALL 產生跨表不一致的 Finding 並列出所有出現位置。

### Requirement 6: 比較法估價表核算

**User Story:** As a 審查人員, I want 系統驗算比較法估價表的調整與價格, so that 加總方式與價格推算錯誤可被指出。

#### Acceptance Criteria

1. THE Review_System SHALL 重算 Individual_Factor_Adjustment 的 Signed_Sum，並與 Comparison_Form 記載的合計比對。
2. THE Review_System SHALL 重算 Absolute_Sum，並與 Comparison_Form 記載的調整百分率絕對值加總比對。
3. IF Signed_Sum 與 Absolute_Sum 被填入相同欄位或互相對調, THEN THE Review_System SHALL 產生加總方式混用的 Finding。
4. THE Review_System SHALL 依交易日期調整百分率驗算「調整至估價基準日單價」。
5. THE Review_System SHALL 依調整至估價基準日單價與各項調整百分率驗算試算價格。
6. IF 驗算結果與記載價格的差異超出可設定的容差, THEN THE Review_System SHALL 產生價格驗算不符的 Finding 並列出完整計算式。
7. THE Review_System SHALL 記錄驗算採用的進位方式，並在 Finding 中說明。

### Requirement 7: 重複修正與例外辨識

**User Story:** As a 審查人員, I want 系統辨識重複修正與特殊調整, so that 不合常規但有理由的情形不會被誤判為錯誤。

#### Acceptance Criteria

1. IF 同一影響因素在區域因素與個別因素同時被修正, THEN THE Review_System SHALL 產生可能重複修正的 Finding。
2. IF Comparison_Form 的備註欄記載了調整理由, THEN THE Review_System SHALL 將對應 Finding 標示為具備說明的例外而非確定錯誤。
3. THE Review_System SHALL 為每個 Finding 指派嚴重度，區分確定錯誤、待確認及提醒。
4. IF 某項數值偏離規則但備註提供依據, THEN THE Review_System SHALL 保留該 Finding 並要求人工確認，不得自動判定通過。

### Requirement 8: 依據追溯與說明生成

**User Story:** As a 審查人員, I want 每項發現都能追溯到規則來源, so that 審查結果可被覆核。

#### Acceptance Criteria

1. THE Review_System SHALL 為每個 Finding 記錄 Rule_Citation，含來源文件、基準表細項識別及可取得的頁碼。
2. WHEN Finding 需要文字說明, THE Review_System SHALL 依 Finding 已有的欄位、數值與 Rule_Citation 生成說明。
3. THE Review_System SHALL 禁止說明生成環節產生或變更任何等級、修正率、價格或距離數值。
4. IF 說明生成引用 Manual_Corpus, THEN THE Review_System SHALL 附上對應段落與頁碼。
5. IF 說明生成無法取得足夠依據, THEN THE Review_System SHALL 輸出 Finding 的結構化欄位並標示未提供文字說明的原因。

### Requirement 9: 審查結果呈現與匯出

**User Story:** As a 審查人員, I want 檢視並確認審查結果後匯出, so that 修正後的書表可交付使用。

#### Acceptance Criteria

1. WHEN 審查完成, THE Review_System SHALL 輸出 Finding 清單，依嚴重度與所在表格排序。
2. THE Review_System SHALL 為每個 Finding 呈現所在表格、欄位位置、原值、應為值、計算過程與 Rule_Citation。
3. THE Review_System SHALL 提供整體摘要，含各嚴重度的 Finding 數量與受影響的細項數。
4. WHEN 使用者確認或否決某個 Finding, THE Review_System SHALL 記錄確認結果與時間。
5. WHEN 使用者完成確認, THE Review_System SHALL 匯出填答完成的 Survey_Form。
6. THE Review_System SHALL 在匯出內容中保留未解決 Finding 的清單。

### Requirement 10: 文件擷取（第一版之後）

**User Story:** As a 審查人員, I want 直接上傳書表檔案, so that 不必手動輸入欄位。

#### Acceptance Criteria

1. THE Review_System SHALL 將文件擷取設計為產生 Case_Bundle 結構的可插拔前置步驟。
2. WHEN 文件擷取完成, THE Review_System SHALL 提供可編輯的欄位確認介面。
3. THE Review_System SHALL 為每個擷取欄位記錄信心度與來源位置。
4. IF 擷取結果未經使用者確認, THEN THE Review_System SHALL 在審查結果中標示欄位來源為未確認的擷取值。

## Out of Scope

- 從地址、地標或地號自動蒐集土地條件與成交案例。
- 自動選取比較標的。
- 商業用地以外的 Land_Use_Type 規則庫建置（架構須支援，第一版不建置）。
- 產生新的估價結論或取代估價師的專業判斷。
