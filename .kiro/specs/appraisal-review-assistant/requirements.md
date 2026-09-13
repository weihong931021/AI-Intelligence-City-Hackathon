# Requirements Document

## Introduction

本功能定義「AI 輔助估價書表填寫」系統：輸入決賽指定的 4 個地價區段（比準地 P001-00 與比較標的 P002／P003／P004），系統補查空白欄位、依樹林區普通住宅用地評價基準判定等級與修正率、串接價格計算，產出可直接照抄或匯出的表3、表5、表4，每一格附證據與依據。

主辦方對成果的分級（2026-09-12 說明會）：

- **100 分**：空白表丟進去，系統直接填完產出。
- **退一步**：針對指定區段，逐格告訴長官該填什麼與為什麼，長官可直接照抄。
- 手填是長官平常在做的事，不是加值；賣點是自動化程度與可加速多少。

範圍界定：

- 案件固定為決賽指定的樹林區普通住宅用地 4 個區段，價格日期 **2022-09-01**（民國 111 年 9 月 1 日），案號 1110901-99-XXX。
- 比較案例已由題目指定，**不選案**；價格日期調整率已由題目給定，**不重算**。
- 權重已寫死在基準表矩陣的級距裡，**不做特徵選擇或迴歸**。
- 系統不自行產生地價；所有數值由規則計算或由使用者輸入，最終值須人工確認。
- 「審查已填書表」不再是獨立功能；同一套計算引擎在填完後重跑一次，作為自我驗證。

依據文件：

- [決賽題目](../../../官方資料/決賽題目_20260912/題目.pdf)：6 頁，4 個區段的表3 已填值、待完成的表5 與表4。
- [評價基準明細表](../../../官方資料/決賽題目_20260912/評價基準明細表.pdf)：p.1–5 區域因素、p.6–9 個別因素。
- [資料使用說明](../../../官方資料/決賽題目_20260912/資料使用說明.md)：檔案用途、目標工作表、判斷界線。
- [決賽說明會：主辦方補充說明](../../../決賽說明會-主辦方補充說明.md)：捷開區分區、容積率 200%、作品方向、待確認清單。
- 3 份 Excel 範本：表3、表5、表4（各 24 個工作表，只使用指定的 3 個）。

## Glossary

- **Fill_System**：負責案件載入、資料蒐集、判級、修正計算、價格串接、輸出與說明生成的功能。
- **Segment**：地價區段（P001-00、P002-00、P003-00、P004-00）。區域因素的判定對象。
- **Parcel**：宗地（樹德段 1415、樹德段 284、太平段 367／917、文林段 317）。個別因素的判定對象。
- **Base_Segment**：比準地所在區段 P001-00；矩陣查值時的「基準」軸。
- **Regional_Criteria**：區域因素評價基準（基準表 p.1–5），8 大類 29 細項，結果填入表5。
- **Individual_Criteria**：個別因素評價基準（基準表 p.6–9），19 細項，結果填入表4 項目 7–25。
- **Criteria_Item**：基準表中的一個細項，含所屬層（`regional`／`individual`）、主要項目、Max_Adjustment、等級數、Grade_Definition、量測方式。
- **Grade**：優劣等級。一般為 優、稍優、普通、稍劣、劣 五級；部分細項為二級或三級；其他影響因素為七級（極優、優、稍優、普通、稍劣、劣、極劣）。
- **Grade_Definition**：原始條件對應到 Grade 的規則：數值級距、類別對應、有無、或反向級距（距離越遠越優，如嫌惡設施、環境污染）。
- **Max_Adjustment**：細項修正率上限，以決賽基準表為準（例：容積率 25、其他影響因素 20、禁限建 50）。
- **Matrix_Formula**：修正百分比 =（比較標的等級序 − 比準地等級序）× Max_Adjustment ÷（等級數 − 1）。
- **Matrix_Override**：個案基準表偏離公式的儲存格，以基準表數值為準。
- **Field_State**：欄位三態：有值、`EXEMPT`（免修正 `−`）、`MISSING`（空白／未查得）。`MISSING` 不得以 0 或「無」代入。
- **Evidence**：補查所得的原始條件及其出處：數值、單位、量測方式、設施名稱、資料來源、擷取日期、時點狀態。
- **Valuation_Date**：價格日期 2022-09-01。
- **Legal_Override**：依法規改寫表上記載值的評比值，含記載值、評比值、法規依據、說明、出處確認狀態。
- **Fill_Suggestion**：對一個空白欄位的建議：建議值、Evidence、Grade、修正率、計算過程、Rule_Citation、信心狀態（`determined`／`needs_confirmation`／`manual`）。
- **Rule_Citation**：依據來源：文件、頁碼、細項識別。
- **Total_Regional_Adjustment**：表5 各主要項目百分比小計的加總，填入表4「區域因素調整百分率」。
- **Individual_Sum**：表4 項目 7–25 差異率的加總。
- **Trial_Price**：單一比較標的經價格日期、區域因素、個別因素調整後的試算價格。
- **Price_Reconciliation**：三個 Trial_Price 收斂為比準地地價的策略（算術平均、依修正幅度加權、剔除離群）。

## Requirements

### Requirement 1: 決賽案件內建

**User Story:** As a 地政局承辦員, I want 系統已載入決賽指定案件, so that 不必手動輸入題目已給的資料。

#### Acceptance Criteria

1. THE Fill_System SHALL 內建 4 個 Segment 的表3 已填值：主要道路名稱與寬度、區段內道路平均寬度、使用分區、都市計畫內外、建蔽率、容積率、禁止建築、限制建築、建築密度、建築型態、土地利用現況、自然條件、土地改良勾選，並保留題目頁碼。
2. THE Fill_System SHALL 內建表4 已給值：三個比較標的的交易日期、正常單價（130,167／135,275／170,909）、價格日期調整率（5.96%／4.09%／5.49%）、調整後單價（137,925／140,808／180,292）。
3. THE Fill_System SHALL 將表3 所有設施欄位（學校、市場、公園廣場徒步區、大型車站、站牌、交流道、觀光遊憩、停車場地、服務性設施、特殊設施、廢棄物處理、殯葬、環境污染）及表4 項目 7–25 標為 `MISSING`。
4. THE Fill_System SHALL 記錄 Valuation_Date、案號、比準地與各比較標的的地號與 Segment 編號。
5. THE Fill_System SHALL 將區段層級的「主要道路寬度」與宗地層級的「面前道路寬度」（表4 項目 14）視為兩個獨立欄位，不得互相代入。

### Requirement 2: 兩層基準規則庫

**User Story:** As a 地政局承辦員, I want 系統依樹林區住宅用地的兩層基準判定, so that 判級與修正率有一致且可查證的依據。

#### Acceptance Criteria

1. THE Fill_System SHALL 維護 Regional_Criteria（29 細項）與 Individual_Criteria（19 細項）兩份規則庫，每個 Criteria_Item 標示所屬層。
2. THE Criteria_Item SHALL 包含 Max_Adjustment、等級數、Grade_Definition、量測方式與 Rule_Citation。
3. THE Fill_System SHALL 以 Matrix_Formula 生成修正矩陣，支援等級數 2、3、5、7。
4. THE Fill_System SHALL 以決賽基準表重新抄錄所有 Max_Adjustment，不得沿用其他案件數值。
5. WHEN 規則庫建立或更新, THE Fill_System SHALL 將公式結果與基準表逐格比對，差異儲存格寫入 Matrix_Override 並回報。
6. THE Fill_System SHALL 支援反向級距（距離越遠 Grade 越優），由 Grade_Definition 表達，矩陣公式不變。
7. THE Fill_System SHALL 將個別因素「容積率」標為不查表（土地開發分析法），不生成矩陣。

### Requirement 3: 資料蒐集與 Evidence

**User Story:** As a 地政局承辦員, I want 系統補查空白設施欄位並附出處, so that 每個等級都有可追溯的距離證據。

#### Acceptance Criteria

1. WHEN 表3 某設施欄位為 `MISSING`, THE Fill_System SHALL 產生補查需求，列出設施類別、適用級距與量測基準。
2. THE Fill_System SHALL 由 Segment 範圍與設施位置計算距離，產出 Evidence。
3. THE Fill_System SHALL 在案件層級設定量測基準（預設：自區段邊界至設施最近點直線距離）一次，所有 Evidence 共用，且於輸出揭露。
4. IF 設施位於 Segment 範圍內, THEN THE Fill_System SHALL 記錄「本區段內」而非距離。
5. IF Evidence 的資料日期晚於 Valuation_Date, THEN THE Fill_System SHALL 標示 `current_data_needs_confirmation`。
6. IF 無法取得 Evidence, THEN THE Fill_System SHALL 標示 `unavailable`，不得填「無」、0 或任何 Grade。
7. IF Segment 範圍的文字描述無法完整轉為圖形, THEN THE Fill_System SHALL 標示邊界待確認，且受影響的距離連帶標示。
8. THE Evidence SHALL 記錄資料集名稱與擷取日期。

### Requirement 4: 法規覆寫

**User Story:** As a 地政局承辦員, I want 表上記載值與實際評比值可以不同並註明法規依據, so that 系統不會把帳面值當成評比值算錯。

#### Acceptance Criteria

1. THE Fill_System SHALL 允許對任一原始條件設定 Legal_Override，含記載值、評比值、法規依據、說明與出處確認狀態。
2. WHEN Legal_Override 存在, THE Fill_System SHALL 以評比值判定 Grade，並在輸出同時顯示記載值與評比值。
3. THE Fill_System SHALL 內建：捷運開發區使用分區依都市計畫變更前分區判定，本案為第一種住宅區。
4. THE Fill_System SHALL 內建：宗地臨路為 8 公尺以下巷道者容積率評比值為 200%，本案四筆皆適用（表3 記載 260% 者亦以 200% 評比）。
5. IF Legal_Override 出處為待確認, THEN THE Fill_System SHALL 將所有受影響的 Fill_Suggestion 標示 `needs_confirmation`。
6. THE Fill_System SHALL 允許使用者新增、修改或停用 Legal_Override，並記錄變更者與時間。

### Requirement 5: 判級與修正計算

**User Story:** As a 地政局承辦員, I want 系統依原始條件判級並算出修正率, so that 表5 與表4 的數字有明確計算過程。

#### Acceptance Criteria

1. WHEN 某細項的原始條件（含 Evidence 與 Legal_Override）齊備, THE Fill_System SHALL 依 Grade_Definition 判定每個 Segment 或 Parcel 的絕對 Grade。
2. THE Fill_System SHALL 以〔Base_Segment Grade × 比較標的 Grade〕查矩陣取得修正百分比，並附計算過程。
3. THE Fill_System SHALL 將 Regional_Criteria 的判定對象限定為 Segment，Individual_Criteria 限定為 Parcel；同名細項（接近學校、接近市場、地勢、停車）在兩層各判一次，不視為重複。
4. THE Fill_System SHALL 將使用分區、建蔽率、容積率僅於 Individual_Criteria 修正；表5 對應三列輸出 `EXEMPT`。
5. WHEN 容積率於個別因素以土地開發分析法調整不足, THE Fill_System SHALL 允許於區域因素補充，並記錄個別因素已調量、不足理由與補充量。
6. IF 使用分區、建蔽率或容積率同時於表5 與表4 出現非 `EXEMPT` 的修正且無接續記錄, THEN THE Fill_System SHALL 拒絕輸出並標示重複修正。
7. THE Fill_System SHALL 重算表5 各主要項目百分比小計與 Total_Regional_Adjustment，`EXEMPT` 與 `MISSING` 不參與加總。
8. THE Fill_System SHALL 將其他影響因素預設為四個 Segment 同為普通（修正 0%），任何級差須附 Evidence 與理由，否則不寫入。
9. THE Fill_System SHALL 支援先排序再定級：依單一子因素將 Segment 排序後，以 Base_Segment 為錨點指派絕對 Grade；輸出仍為每個 Segment 的絕對 Grade。
10. IF 某細項任一 Segment 或 Parcel 的原始條件為 `MISSING`, THEN THE Fill_System SHALL 將該細項所有修正標為 `MISSING`，不得部分計算。

### Requirement 6: 價格串接與三價收斂

**User Story:** As a 地政局承辦員, I want 系統從三個比較標的算到一個比準地地價, so that 表4 的價格欄位可以填齊且公式透明。

#### Acceptance Criteria

1. THE Fill_System SHALL 將 Total_Regional_Adjustment 填入表4「區域因素調整百分率」。
2. THE Fill_System SHALL 重算 Individual_Sum。
3. THE Fill_System SHALL 依序套用價格日期調整、區域因素調整、個別因素調整計算每個比較標的的 Trial_Price；疊加方式（相乘或相加）為設定項並於輸出揭露。
4. THE Fill_System SHALL 記錄捨入方式並於輸出揭露。
5. THE Fill_System SHALL 提供 Price_Reconciliation 策略：`mean`、`weighted_by_adjustment`（總修正率絕對值越小權重越高）、`drop_outlier`（剔除總修正率超過閾值者）。
6. THE Fill_System SHALL 於輸出揭露所選策略、各案權重、閾值與計算式。
7. IF Price_Reconciliation 的法源未經確認, THEN THE Fill_System SHALL 於輸出標示待確認。
8. IF 任一 Trial_Price 因 `MISSING` 無法計算, THEN THE Fill_System SHALL 不輸出比準地地價，並列出阻擋的欄位。

### Requirement 7: 填表輸出與匯出

**User Story:** As a 地政局承辦員, I want 每個空白欄位有可照抄的建議與理由並能匯出, so that 填表時間縮短且結果可覆核。

#### Acceptance Criteria

1. THE Fill_System SHALL 對表3、表5、表4 每個可由規則決定的 `MISSING` 欄位產生 Fill_Suggestion。
2. THE Fill_Suggestion SHALL 包含建議值、Evidence、Grade、修正率、計算過程、Rule_Citation 與信心狀態。
3. THE Fill_System SHALL 以逐格形式呈現，點開任一格可見其 Evidence、Legal_Override、Grade_Definition 與矩陣查值。
4. IF 某欄位需人工判斷（其他影響因素、土地開發分析法）, THEN THE Fill_System SHALL 呈現候選 Grade 與所需舉證項目，信心狀態為 `manual`，不得自動填值。
5. WHEN 使用者確認或修改 Fill_Suggestion, THE Fill_System SHALL 記錄最終值、修改者與時間。
6. THE Fill_System SHALL 匯出官方 Excel 範本的指定工作表：「表3區段勘查表」、「表5-1區域因素明細表(住)」、「表4比較法調查估價表」，其餘工作表不動。
7. THE Fill_System SHALL 在匯出中將 `MISSING` 欄位留白並於備註標示待確認，不得填值。
8. THE Fill_System SHALL 隨匯出附缺漏清單、Legal_Override 清單、量測基準、疊加方式、捨入方式與 Price_Reconciliation 設定。

### Requirement 8: 自我驗證與說明生成

**User Story:** As a 地政局承辦員, I want 填完的結果被系統自己驗算並附白話說明, so that 覆核者不必重算也看得懂。

#### Acceptance Criteria

1. WHEN 使用者完成確認, THE Fill_System SHALL 以最終值重跑判級、矩陣、小計、總修正、價格串接，任一步與已填值不符即標示不一致。
2. THE Fill_System SHALL 在自我驗證中檢查：`EXEMPT` 與 `0.00` 混用、表5 總修正數與表4 區域因素調整百分率不一致、同名細項誤代入另一層。
3. WHEN Fill_Suggestion 需要文字說明, THE Fill_System SHALL 依已有的欄位、數值與 Rule_Citation 生成說明。
4. THE Fill_System SHALL 禁止說明生成環節產生或變更任何 Grade、修正率、價格或距離數值；輸出中出現未知數值即捨棄說明並退回結構化輸出。
5. THE Fill_System SHALL 使用 AWS 服務提供者的基礎模型（競賽限制）。
6. THE Fill_System SHALL 允許以模型輔助將 Segment 範圍文字轉為候選邊界，但候選結果須經人工確認後才用於距離計算。

## Out of Scope

- 自動選取比較標的（本案已指定 3 筆）。
- 指定 4 個 Segment 以外的資料蒐集。
- 樹林區普通住宅用地以外的規則庫建置（架構須支援用地類型切換，本版不建置）。
- 上傳書表檔案的文件擷取（輸入固定為題目 PDF，一次性轉錄）。
- 產生新的估價結論或取代估價師的專業判斷。

## 待向主辦方確認

- 「宗地臨路 8 公尺以下巷道容積率降為 200%」的確切法規出處。
- 三個 Trial_Price 收斂為比準地地價的法源與規則。
- 表3 設施距離的量測基準：自區段邊界或區段中心。
- 補查設施資料若僅能取得現況（2026）而非 2022-09-01 時點，是否可接受並標注。
- 區域因素與個別因素的疊加方式（相乘或相加）。
