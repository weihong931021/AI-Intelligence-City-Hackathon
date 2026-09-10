# Requirements Document

> **狀態：已結案（2026-09-10）。**
> 本規格撰寫於官方資料尚未取得時。命題文件與資料集已於 2026/09/07 備存至
> [官方資料](../../../官方資料/README.md)（共 4 份 PDF，已核對完整性），本規格的目的已達成。
> 未完成的任務（報告產生器、協調器、CLI）不再繼續；已完成的模組保留於
> `src/import_drive_archive/` 供日後重跑匯入時參考。
> 專案主線已移至 [appraisal-review-assistant](../appraisal-review-assistant/requirements.md)。

## Introduction

本功能定義一套可稽核的匯入流程，涵蓋指定的遠端資料夾與工作區既有壓縮檔，並在處理完成後產生繁體中文內容說明。本文件僅描述預期行為，不執行下載、解壓縮或檔案整理。

## Glossary

- **Archive_Import_System**：負責來源盤點、取得、驗證、解壓縮、整理、重複檢查及報告輸出的功能。
- **Google_Drive_Source**：網址 `https://drive.google.com/drive/folders/1fHmn3VTXyfYkERvsDqKMP_A_6_hVgJaE` 所指向的 Google Drive 資料夾。
- **Workspace_ZIP**：匯入開始前已存在於工作區且副檔名為 `.zip` 的壓縮檔；目前掃描辨識到 `B_地政局-命題文件.zip`。
- **Source_Item**：Google_Drive_Source 或 Workspace_ZIP 中可盤點的單一檔案或目錄。
- **Import_Workspace**：匯入功能可讀取來源並寫入處理結果的工作區範圍。
- **Staging_Area**：與原始來源分離、用於存放下載中或驗證中內容的暫存區域。
- **Output_Area**：存放驗證通過且完成整理之內容的目錄。
- **Source_Namespace**：在 Output_Area 中區分 Google_Drive_Source 與各 Workspace_ZIP 的頂層目錄。
- **Archive_Entry**：壓縮檔內的一個檔案、目錄或連結項目。
- **Safety_Limits**：可設定的單檔解壓縮大小、總解壓縮大小、項目數量及壓縮比上限。
- **Unsafe_Archive_Entry**：具有絕對路徑、父目錄跳脫、輸出範圍外連結目標，或超出 Safety_Limits 的 Archive_Entry。
- **Content_Fingerprint**：根據檔案位元內容產生、用於比較內容是否相同的穩定識別值。
- **Duplicate_Group**：具有相同檔案大小及 Content_Fingerprint 的兩個以上檔案所形成的群組。
- **Conflict_Copy**：目標路徑已被不同內容占用時，以可追溯且唯一的新名稱保存的來源檔案。
- **Import_Manifest**：記錄每個來源、原始相對路徑、結果路徑、大小、完整性、處理狀態及異常的清單。
- **Traditional_Chinese_Report**：以繁體中文撰寫的最終內容盤點與處理摘要。

## Requirements

### Requirement 1: 來源辨識與盤點

**User Story:** As a 使用者, I want 系統辨識指定的遠端與本機來源, so that 匯入範圍可在處理前確認。

#### Acceptance Criteria

1. WHEN 匯入作業開始, THE Archive_Import_System SHALL 將 Google_Drive_Source 登錄為遠端來源。
2. WHEN Import_Workspace 掃描完成, THE Archive_Import_System SHALL 將每個 Workspace_ZIP 登錄為本機來源。
3. WHEN `B_地政局-命題文件.zip` 存在於 Import_Workspace, THE Archive_Import_System SHALL 在來源盤點中列出 `B_地政局-命題文件.zip`。
4. THE Archive_Import_System SHALL 為每個已登錄來源指派可追溯的來源識別資訊。

### Requirement 2: Google Drive 存取權限

**User Story:** As a 使用者, I want 得知遠端資料夾的存取結果, so that 權限問題可被明確處理。

#### Acceptance Criteria

1. WHEN Google_Drive_Source 允許存取, THE Archive_Import_System SHALL 盤點可見的 Source_Item 及資料夾階層。
2. IF Google_Drive_Source 要求登入或授權, THEN THE Archive_Import_System SHALL 將來源狀態標示為需要授權並提供授權需求說明。
3. IF Google_Drive_Source 拒絕存取, THEN THE Archive_Import_System SHALL 記錄拒絕原因與受影響的來源範圍。
4. IF Google_Drive_Source 無法存取, THEN THE Archive_Import_System SHALL 保留 Workspace_ZIP 的後續處理資格。

### Requirement 3: 來源取得與完整性

**User Story:** As a 使用者, I want 驗證取得檔案的完整性, so that 不完整內容不會進入整理結果。

#### Acceptance Criteria

1. WHEN 遠端 Source_Item 開始取得, THE Archive_Import_System SHALL 將傳輸中內容置於 Staging_Area。
2. WHEN Source_Item 取得完成, THE Archive_Import_System SHALL 比對來源可提供的檔案大小與完整性資訊。
3. IF Source_Item 的實際大小或完整性資訊與來源資訊不一致, THEN THE Archive_Import_System SHALL 將 Source_Item 標示為完整性驗證失敗。
4. IF Source_Item 取得中斷, THEN THE Archive_Import_System SHALL 將未完成內容與已驗證內容分離並記錄中斷狀態。
5. WHEN Source_Item 通過完整性驗證, THE Archive_Import_System SHALL 在 Import_Manifest 記錄驗證結果。

### Requirement 4: 壓縮檔安全檢查

**User Story:** As a 使用者, I want 在解壓縮前檢查壓縮檔風險, so that 惡意或異常項目無法影響輸出範圍。

#### Acceptance Criteria

1. THE Archive_Import_System SHALL 在解壓縮前取得每個 Archive_Entry 的類型、相對路徑、壓縮大小及解壓縮大小。
2. THE Archive_Import_System SHALL 在解壓縮前套用 Safety_Limits。
3. IF Archive_Entry 包含絕對路徑或父目錄跳脫路徑, THEN THE Archive_Import_System SHALL 將 Archive_Entry 標示為 Unsafe_Archive_Entry 並排除於解壓縮結果。
4. IF Archive_Entry 的連結目標位於 Output_Area 外, THEN THE Archive_Import_System SHALL 將 Archive_Entry 標示為 Unsafe_Archive_Entry 並排除於解壓縮結果。
5. IF 壓縮檔超出任一 Safety_Limits, THEN THE Archive_Import_System SHALL 停止該壓縮檔的解壓縮並記錄觸發的限制。
6. IF 壓縮檔格式損壞、加密或不受支援, THEN THE Archive_Import_System SHALL 保留原始壓縮檔並記錄無法解壓縮的原因。

### Requirement 5: 避免覆寫與衝突處理

**User Story:** As a 使用者, I want 保留既有檔案與同名來源檔案, so that 匯入過程不會造成資料遺失。

#### Acceptance Criteria

1. WHEN Source_Item 準備寫入 Output_Area, THE Archive_Import_System SHALL 先檢查目標相對路徑的占用狀態。
2. IF 目標相對路徑已由不同內容占用, THEN THE Archive_Import_System SHALL 保留目標相對路徑的既有內容。
3. IF 目標相對路徑已由不同內容占用, THEN THE Archive_Import_System SHALL 將 Source_Item 儲存為 Conflict_Copy。
4. WHEN Conflict_Copy 建立完成, THE Archive_Import_System SHALL 在 Import_Manifest 記錄原始路徑、衝突路徑及結果路徑。
5. WHEN 相同匯入作業重新執行, THE Archive_Import_System SHALL 依既有 Import_Manifest 重用相同的衝突命名結果。

### Requirement 6: 目錄結構保存與來源隔離

**User Story:** As a 使用者, I want 保留來源目錄脈絡, so that 整理後內容仍可追溯到原始位置。

#### Acceptance Criteria

1. WHEN Google_Drive_Source 的 Source_Item 寫入 Output_Area, THE Archive_Import_System SHALL 在 Google Drive 專屬 Source_Namespace 下保存原始相對目錄結構。
2. WHEN Workspace_ZIP 的 Archive_Entry 寫入 Output_Area, THE Archive_Import_System SHALL 在該 Workspace_ZIP 專屬 Source_Namespace 下保存安全的相對目錄結構。
3. WHEN 空目錄屬於來源盤點結果, THE Archive_Import_System SHALL 在 Import_Manifest 記錄空目錄的原始相對路徑。
4. IF 來源路徑包含 Output_Area 不支援的名稱, THEN THE Archive_Import_System SHALL 產生可用且唯一的結果名稱並記錄名稱對應。

### Requirement 7: 重複檔案辨識

**User Story:** As a 使用者, I want 辨識內容相同的檔案, so that 重複內容可被清楚整理且不會誤刪不同內容。

#### Acceptance Criteria

1. WHEN 檔案通過完整性驗證, THE Archive_Import_System SHALL 計算檔案大小與 Content_Fingerprint。
2. WHEN 兩個以上檔案具有相同檔案大小及 Content_Fingerprint, THE Archive_Import_System SHALL 建立 Duplicate_Group。
3. WHEN Duplicate_Group 建立完成, THE Archive_Import_System SHALL 指定一個保留項目並記錄每個重複來源路徑。
4. IF 兩個檔案名稱相同但 Content_Fingerprint 不同, THEN THE Archive_Import_System SHALL 將兩個檔案視為內容衝突而非 Duplicate_Group。
5. WHEN 重複內容整理完成, THE Archive_Import_System SHALL 在 Import_Manifest 記錄保留項目與其他重複項目的對應關係。

### Requirement 8: 可稽核清單與錯誤隔離

**User Story:** As a 使用者, I want 查閱每個項目的處理結果, so that 成功、略過與失敗內容皆可追蹤。

#### Acceptance Criteria

1. THE Archive_Import_System SHALL 在 Import_Manifest 為每個 Source_Item 記錄來源識別資訊、原始相對路徑、項目類型及處理狀態。
2. WHEN Source_Item 產生結果檔案, THE Archive_Import_System SHALL 在 Import_Manifest 記錄結果路徑、檔案大小及 Content_Fingerprint。
3. IF 單一 Source_Item 處理失敗, THEN THE Archive_Import_System SHALL 將錯誤限制於該 Source_Item 並記錄失敗原因。
4. WHEN 匯入作業結束, THE Archive_Import_System SHALL 在 Import_Manifest 記錄各處理狀態的項目數量。

### Requirement 9: 繁體中文內容說明與摘要

**User Story:** As a 使用者, I want 取得繁體中文的完整內容說明, so that 可快速理解匯入資料與處理結果。

#### Acceptance Criteria

1. WHEN 匯入作業結束, THE Archive_Import_System SHALL 產生 Traditional_Chinese_Report。
2. THE Traditional_Chinese_Report SHALL 為每個已盤點 Source_Item 列出來源、原始相對路徑、項目類型、檔案大小及處理狀態。
3. WHEN Source_Item 為可讀取的文字檔案, THE Archive_Import_System SHALL 在 Traditional_Chinese_Report 提供該文字內容的繁體中文摘要。
4. WHEN Source_Item 為非文字檔案, THE Archive_Import_System SHALL 在 Traditional_Chinese_Report 提供檔案格式、檔案大小、原始相對路徑及用途判讀。
5. WHEN Source_Item 為壓縮檔, THE Archive_Import_System SHALL 在 Traditional_Chinese_Report 說明壓縮檔內的目錄、檔案類型及項目數量。
6. THE Traditional_Chinese_Report SHALL 彙整 Google Drive 權限、完整性驗證、Unsafe_Archive_Entry、Conflict_Copy、Duplicate_Group 及處理錯誤的結果。
7. IF Source_Item 無法讀取或無法判讀用途, THEN THE Archive_Import_System SHALL 在 Traditional_Chinese_Report 明確標示限制原因。
