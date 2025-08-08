using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Windows;

namespace MaiAgentValidator
{
    /// <summary>
    /// AboutWindow.xaml 的互動邏輯
    /// </summary>
    public partial class AboutWindow : Window
    {
        public AboutWindow()
        {
            InitializeComponent();
            InitializeSystemInfo();
        }

        private void InitializeSystemInfo()
        {
            try
            {
                // 作業系統資訊
                var osVersion = Environment.OSVersion;
                var osName = GetOSFriendlyName();
                OsVersionLabel.Text = $"{osName} {osVersion.Version}";

                // .NET 版本
                var dotNetVersion = RuntimeInformation.FrameworkDescription;
                DotNetVersionLabel.Text = dotNetVersion;

                // 架構資訊
                var architecture = RuntimeInformation.OSArchitecture.ToString();
                ArchitectureLabel.Text = architecture;

                // 程序 ID
                var processId = Environment.ProcessId;
                ProcessIdLabel.Text = processId.ToString();
            }
            catch (Exception ex)
            {
                // 如果獲取系統資訊失敗，顯示預設值
                OsVersionLabel.Text = "未知";
                DotNetVersionLabel.Text = "未知";
                ArchitectureLabel.Text = "未知";
                ProcessIdLabel.Text = "未知";
                
                System.Diagnostics.Debug.WriteLine($"獲取系統資訊時發生錯誤: {ex.Message}");
            }
        }

        private string GetOSFriendlyName()
        {
            try
            {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    // 嘗試獲取更友善的 Windows 版本名稱
                    var version = Environment.OSVersion.Version;
                    return version.Major switch
                    {
                        10 when version.Build >= 22000 => "Windows 11",
                        10 => "Windows 10",
                        6 when version.Minor == 3 => "Windows 8.1",
                        6 when version.Minor == 2 => "Windows 8",
                        6 when version.Minor == 1 => "Windows 7",
                        _ => "Windows"
                    };
                }
                else if (RuntimeInformation.IsOSPlatform(OSPlatform.Linux))
                {
                    return "Linux";
                }
                else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                {
                    return "macOS";
                }
                else
                {
                    return "未知作業系統";
                }
            }
            catch
            {
                return "Windows";
            }
        }

        private void CopyInfoButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                var systemInfo = GenerateSystemInfoText();
                Clipboard.SetText(systemInfo);
                MessageBox.Show("系統資訊已複製到剪貼簿", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"複製系統資訊時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
            }
        }

        private string GenerateSystemInfoText()
        {
            var info = $@"MaiAgent 管理工具集 - 系統資訊
版本：4.2.6 - RAG 增強版
建置日期：2025-01-27

系統環境：
作業系統：{OsVersionLabel.Text}
.NET 版本：{DotNetVersionLabel.Text}
框架：WPF + Material Design
架構：{ArchitectureLabel.Text}
程序 ID：{ProcessIdLabel.Text}

核心功能：
• AI 助理回覆品質驗證
• RAG 增強統計分析
• 批次驗證處理
• 詳細統計報告
• 智能重試機制
• 組織管理功能
• 知識庫管理

技術特點：
• 異步處理架構，高效能並發操作
• 智能錯誤處理和自動重試機制
• 網路連接優化和超時設定
• 跨平台適配和記憶體優化
• API 限流控制和容錯能力
• 現代化 Material Design UI
• 依賴注入和服務架構

開發團隊：MaiAgent Team
版權聲明：Copyright © 2025 MaiAgent Team. 保留所有權利。
授權條款：MIT License

生成時間：{DateTime.Now:yyyy-MM-dd HH:mm:ss}";

            return info;
        }

        private void CloseButton_Click(object sender, RoutedEventArgs e)
        {
            Close();
        }

        protected override void OnSourceInitialized(EventArgs e)
        {
            base.OnSourceInitialized(e);
            
            // 設定視窗圖標（如果需要）
            try
            {
                // 可以在這裡設定自定義圖標
            }
            catch
            {
                // 忽略圖標設定錯誤
            }
        }
    }
} 