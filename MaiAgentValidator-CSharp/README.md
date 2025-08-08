# MaiAgent 驗證工具 C# 版本 🚀

![Version](https://img.shields.io/badge/version-4.2.6-blue.svg)
![.NET](https://img.shields.io/badge/.NET-6.0-purple.svg)
![WPF](https://img.shields.io/badge/WPF-Material_Design-green.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)

**MaiAgent 驗證工具 C# 版本** 是原 Python 版本的現代化 C# 實現，採用 WPF + Material Design 構建，提供更優秀的桌面應用體驗。

## ✨ 主要特色

### 🎨 現代化 UI 設計
- **Material Design**：採用 Google Material Design 設計語言
- **響應式界面**：流暢的動畫效果和視覺反饋
- **多分頁管理**：清晰的功能模組劃分
- **深色/淺色主題**：支援主題切換（計畫中）
- **可自定義樣式**：豐富的 UI 自定義選項

### ⚡ 技術優勢
- **.NET 6.0**：最新的 .NET 技術棧
- **異步架構**：全面採用 async/await 模式
- **依賴注入**：現代化的服務架構
- **強類型**：編譯時錯誤檢查
- **記憶體安全**：自動垃圾回收管理
- **高性能**：原生編譯性能

### 🔧 核心功能
- **AI 助理驗證**：完整的驗證工作流程
- **RAG 統計分析**：精確的統計指標計算
- **批次處理**：高效的併發處理機制
- **智能重試**：自動錯誤恢復和重試
- **結果匯出**：Excel/CSV 格式匯出
- **設定管理**：持久化設定儲存

## 🛠️ 系統需求

### 最低需求
- **作業系統**：Windows 10 版本 1809 或更高版本
- **.NET 運行時**：.NET 6.0 Desktop Runtime
- **記憶體**：4GB RAM
- **磁碟空間**：200MB 可用空間
- **螢幕解析度**：1280x720 或更高

### 建議需求
- **作業系統**：Windows 11
- **.NET 運行時**：.NET 6.0 Desktop Runtime
- **記憶體**：8GB RAM 或更多
- **磁碟空間**：1GB 可用空間
- **螢幕解析度**：1920x1080 或更高

## 📦 安裝與部署

### 方法一：使用預編譯版本（推薦）

1. **下載發行版**：
   ```
   從 GitHub Releases 下載最新的 .zip 檔案
   ```

2. **解壓縮**：
   ```
   解壓縮到任意目錄（建議：C:\Program Files\MaiAgent）
   ```

3. **執行應用程式**：
   ```
   雙擊 MaiAgentValidator.exe 啟動程式
   ```

### 方法二：從原始碼編譯

1. **安裝開發環境**：
   ```bash
   # 安裝 .NET 6.0 SDK
   https://dotnet.microsoft.com/download/dotnet/6.0
   
   # 安裝 Visual Studio 2022 或 Visual Studio Code（可選）
   ```

2. **複製程式碼**：
   ```bash
   git clone https://github.com/MaiAgent-steven/MaiAgent_GUI_Tool.git
   cd MaiAgent_GUI_Tool
   ```

3. **還原 NuGet 套件**：
   ```bash
   dotnet restore MaiAgentValidator.csproj
   ```

4. **編譯專案**：
   ```bash
   # Debug 版本
   dotnet build MaiAgentValidator.csproj
   
   # Release 版本
   dotnet build MaiAgentValidator.csproj -c Release
   ```

5. **執行應用程式**：
   ```bash
   dotnet run --project MaiAgentValidator.csproj
   ```

### 方法三：建立可執行檔

```bash
# 建立自包含的可執行檔（包含 .NET 運行時）
dotnet publish MaiAgentValidator.csproj -c Release -r win-x64 --self-contained true

# 建立依賴框架的可執行檔（需要安裝 .NET 運行時）
dotnet publish MaiAgentValidator.csproj -c Release -r win-x64 --self-contained false
```

## 🚀 快速開始

### 第一次啟動

1. **啟動應用程式**：
   - 雙擊 `MaiAgentValidator.exe`
   - 或使用命令列：`dotnet run`

2. **設定 API 連線**：
   - 前往「🔧 設定」分頁
   - 輸入 API 基礎 URL 和金鑰
   - 點擊「測試連接」確認設定

3. **載入聊天機器人**：
   - 點擊「重新載入機器人列表」
   - 確認機器人列表載入成功

### 執行驗證

1. **選擇測試文件**：
   - 前往「🔍 驗證」分頁
   - 點擊「瀏覽」選擇 CSV 或 Excel 文件
   - 支援格式：`.csv`, `.xlsx`, `.xls`

2. **設定驗證參數**：
   - 調整相似度閾值（建議 0.3）
   - 設定併發數量（建議 5）
   - 配置 API 延遲和重試次數

3. **選擇聊天機器人**：
   - 在聊天機器人列表中選擇目標機器人

4. **開始驗證**：
   - 點擊「開始驗證」
   - 監控進度條和日誌輸出
   - 可隨時點擊「停止驗證」中斷

5. **查看結果**：
   - 前往「📊 結果」分頁
   - 查看統計摘要和詳細結果
   - 點擊「匯出結果」儲存報告

## 📁 專案結構

```
MaiAgentValidator/
├── Models/                     # 數據模型
│   └── ValidationRow.cs       # 驗證數據結構
├── Services/                   # 服務層
│   ├── MaiAgentApiClient.cs   # API 客戶端
│   ├── EnhancedTextMatcher.cs # 文本匹配服務
│   └── ...                    # 其他服務
├── Views/                      # 視圖層
│   ├── MainWindow.xaml        # 主視窗 XAML
│   ├── MainWindow.xaml.cs     # 主視窗邏輯
│   ├── AboutWindow.xaml       # 關於視窗
│   └── AboutWindow.xaml.cs    # 關於視窗邏輯
├── ViewModels/                 # 視圖模型（計畫中）
├── App.xaml                    # 應用程式資源
├── App.xaml.cs                 # 應用程式入口
├── MaiAgentValidator.csproj    # 專案文件
└── README-CSharp.md           # 本文件
```

## 🔧 開發指南

### 技術棧

- **.NET 6.0**：目標框架
- **WPF**：桌面應用程式框架
- **Material Design in XAML**：UI 設計庫
- **Microsoft.Extensions***：依賴注入和日誌
- **Newtonsoft.Json**：JSON 序列化
- **ClosedXML**：Excel 文件處理
- **CsvHelper**：CSV 文件處理

### 架構模式

- **MVVM**：Model-View-ViewModel 模式（計畫中）
- **依賴注入**：IoC 容器管理服務
- **異步程式設計**：async/await 模式
- **服務導向**：模組化服務架構

### 擴展開發

1. **新增服務**：
   ```csharp
   // 在 App.xaml.cs 中註冊服務
   services.AddSingleton<IYourService, YourService>();
   ```

2. **新增視窗**：
   ```csharp
   // 建立 XAML 和 Code-behind
   // 在 App.xaml.cs 中註冊
   services.AddTransient<YourWindow>();
   ```

3. **新增數據模型**：
   ```csharp
   // 在 Models/ 目錄下建立類別
   // 實現 INotifyPropertyChanged 以支援資料綁定
   ```

## 📋 功能對照表

| 功能 | Python 版本 | C# 版本 | 狀態 |
|------|-------------|---------|------|
| 基本驗證 | ✅ | ✅ | 已完成 |
| RAG 統計 | ✅ | ✅ | 已完成 |
| 批次處理 | ✅ | ✅ | 已完成 |
| Excel 匯出 | ✅ | ✅ | 已完成 |
| 設定管理 | ✅ | 🚧 | 開發中 |
| 重測功能 | ✅ | 🚧 | 開發中 |
| 組織管理 | ✅ | 📋 | 計畫中 |
| 知識庫管理 | ✅ | 📋 | 計畫中 |
| 主題切換 | ❌ | 📋 | 計畫中 |
| 多語言支援 | ❌ | 📋 | 計畫中 |

**圖例**：✅ 已完成、🚧 開發中、📋 計畫中、❌ 不支援

## 🐛 已知問題

1. **文件載入**：大型 Excel 文件可能需要較長載入時間
2. **UI 回應**：長時間驗證時界面可能短暫無回應（正在優化）
3. **記憶體使用**：處理大量數據時記憶體使用量較高

## 🔄 版本歷史

### v4.2.6 (2025-01-27) - 初始 C# 版本
- 🎉 **首次發布**：C# WPF 版本正式發布
- 🎨 **Material Design UI**：採用現代化設計語言
- ⚡ **高性能架構**：.NET 6.0 + 異步處理
- 🔧 **核心功能**：實現基本驗證和統計功能
- 📊 **結果匯出**：支援 Excel 和 CSV 格式
- 🛡️ **錯誤處理**：完善的異常處理機制

### 未來版本規劃

#### v4.3.0 - 功能完善
- 🔧 設定管理功能
- 🔄 失敗問題重測
- 📝 更詳細的日誌系統
- 🎯 效能優化

#### v4.4.0 - 進階功能
- 👥 組織管理模組
- 🗃️ 知識庫管理
- 📱 響應式設計改進
- 🌍 多語言支援

#### v5.0.0 - 重大更新
- 🎨 深色主題支援
- 📊 進階統計分析
- 🔌 插件系統
- ☁️ 雲端同步功能

## 🤝 貢獻指南

我們歡迎社群貢獻！請遵循以下步驟：

### 開發環境設定

1. **Fork 專案**
2. **安裝 .NET 6.0 SDK**
3. **安裝 Visual Studio 2022**（建議）或 VS Code
4. **安裝 Git**

### 提交流程

1. **建立功能分支**：
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **開發和測試**：
   ```bash
   # 確保程式碼可以編譯
   dotnet build
   
   # 執行測試（如果有）
   dotnet test
   ```

3. **提交變更**：
   ```bash
   git commit -m "Add: 您的功能描述"
   ```

4. **推送分支**：
   ```bash
   git push origin feature/your-feature-name
   ```

5. **建立 Pull Request**

### 程式碼規範

- **命名規範**：遵循 C# 命名慣例
- **註解**：使用繁體中文註解
- **格式**：使用 Visual Studio 預設格式化
- **架構**：遵循 MVVM 模式（視圖模型層開發中）

## 📄 授權條款

本專案採用 MIT 授權條款。詳見 [LICENSE](LICENSE) 檔案。

## 🙏 致謝

- **MaiAgent Team**：原始 Python 版本開發
- **Material Design in XAML**：優秀的 WPF Material Design 庫
- **Microsoft**：.NET 平台和開發工具
- **開源社群**：各種開源套件和工具

## 📞 支援與回饋

- **問題回報**：[GitHub Issues](https://github.com/MaiAgent-steven/MaiAgent_GUI_Tool/issues)
- **功能建議**：[GitHub Discussions](https://github.com/MaiAgent-steven/MaiAgent_GUI_Tool/discussions)
- **電子郵件**：maiagent-team@example.com

---

**🌟 如果這個專案對您有幫助，請給我們一個 Star！**

**Made with ❤️ by MaiAgent Team** 