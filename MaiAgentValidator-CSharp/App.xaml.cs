using System;
using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using MaiAgentValidator.Services;

namespace MaiAgentValidator
{
    /// <summary>
    /// App.xaml 的互動邏輯
    /// </summary>
    public partial class App : Application
    {
        private IHost _host;

        public App()
        {
            // 設定未處理例外的處理器
            DispatcherUnhandledException += App_DispatcherUnhandledException;
            AppDomain.CurrentDomain.UnhandledException += CurrentDomain_UnhandledException;
        }

        protected override async void OnStartup(StartupEventArgs e)
        {
            // 建立主機和依賴注入容器
            _host = CreateHostBuilder().Build();
            
            try
            {
                await _host.StartAsync();

                // 取得主視窗並顯示
                var mainWindow = _host.Services.GetRequiredService<MainWindow>();
                mainWindow.Show();
            }
            catch (Exception ex)
            {
                MessageBox.Show($"應用程式啟動失敗：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                Shutdown();
            }

            base.OnStartup(e);
        }

        protected override async void OnExit(ExitEventArgs e)
        {
            if (_host != null)
            {
                await _host.StopAsync();
                _host.Dispose();
            }

            base.OnExit(e);
        }

        private IHostBuilder CreateHostBuilder()
        {
            return Host.CreateDefaultBuilder()
                .ConfigureServices((context, services) =>
                {
                    // 註冊日誌服務
                    services.AddLogging(builder =>
                    {
                        builder.AddConsole();
                        builder.AddDebug();
                        builder.SetMinimumLevel(LogLevel.Information);
                    });

                    // 註冊 HTTP 客戶端
                    services.AddHttpClient();

                    // 註冊應用程式服務
                    services.AddSingleton<EnhancedTextMatcher>();
                    
                    // 註冊視窗
                    services.AddTransient<MainWindow>();
                    services.AddTransient<AboutWindow>();

                    // 註冊其他服務
                    services.AddSingleton<IValidationService, ValidationService>();
                    services.AddSingleton<IFileService, FileService>();
                    services.AddSingleton<IExportService, ExportService>();
                    services.AddSingleton<IConfigurationService, ConfigurationService>();
                });
        }

        private void App_DispatcherUnhandledException(object sender, System.Windows.Threading.DispatcherUnhandledExceptionEventArgs e)
        {
            var logger = _host?.Services?.GetService<ILogger<App>>();
            logger?.LogError(e.Exception, "未處理的 UI 執行緒例外");

            MessageBox.Show(
                $"發生未預期的錯誤：\n\n{e.Exception.Message}\n\n應用程式將繼續運行，但建議重新啟動。",
                "錯誤",
                MessageBoxButton.OK,
                MessageBoxImage.Error);

            e.Handled = true;
        }

        private void CurrentDomain_UnhandledException(object sender, UnhandledExceptionEventArgs e)
        {
            var logger = _host?.Services?.GetService<ILogger<App>>();
            logger?.LogCritical(e.ExceptionObject as Exception, "未處理的應用程式域例外");

            if (e.ExceptionObject is Exception ex)
            {
                MessageBox.Show(
                    $"發生嚴重錯誤：\n\n{ex.Message}\n\n應用程式即將關閉。",
                    "嚴重錯誤",
                    MessageBoxButton.OK,
                    MessageBoxImage.Error);
            }

            Environment.Exit(1);
        }
    }

    #region Service Interfaces

    /// <summary>
    /// 驗證服務介面
    /// </summary>
    public interface IValidationService
    {
        Task<ValidationStatistics> ProcessValidationAsync(
            string filePath, 
            string chatbotId, 
            ValidationSettings settings,
            IProgress<ValidationProgress> progress,
            CancellationToken cancellationToken);
    }

    /// <summary>
    /// 文件服務介面
    /// </summary>
    public interface IFileService
    {
        Task<List<ValidationRow>> LoadValidationDataAsync(string filePath);
        Task SaveValidationResultsAsync(string filePath, List<ValidationRow> data, ValidationStatistics stats);
        List<string> GetSupportedFileExtensions();
    }

    /// <summary>
    /// 匯出服務介面
    /// </summary>
    public interface IExportService
    {
        Task ExportToExcelAsync(string filePath, List<ValidationRow> data, ValidationStatistics stats);
        Task ExportToCsvAsync(string filePath, List<ValidationRow> data, ValidationStatistics stats);
    }

    /// <summary>
    /// 設定服務介面
    /// </summary>
    public interface IConfigurationService
    {
        Task<AppSettings> LoadSettingsAsync();
        Task SaveSettingsAsync(AppSettings settings);
        string GetSettingsFilePath();
    }

    #endregion

    #region Service Implementations (Placeholder)

    /// <summary>
    /// 驗證服務實作
    /// </summary>
    public class ValidationService : IValidationService
    {
        private readonly ILogger<ValidationService> _logger;
        private readonly EnhancedTextMatcher _textMatcher;

        public ValidationService(ILogger<ValidationService> logger, EnhancedTextMatcher textMatcher)
        {
            _logger = logger;
            _textMatcher = textMatcher;
        }

        public async Task<ValidationStatistics> ProcessValidationAsync(
            string filePath, 
            string chatbotId, 
            ValidationSettings settings, 
            IProgress<ValidationProgress> progress, 
            CancellationToken cancellationToken)
        {
            _logger.LogInformation($"開始處理驗證：{filePath}");
            
            // 實作驗證邏輯
            await Task.Delay(1000, cancellationToken);
            
            return new ValidationStatistics
            {
                總查詢數 = 0,
                成功數 = 0,
                失敗數 = 0,
                成功率 = 0.0
            };
        }
    }

    /// <summary>
    /// 文件服務實作
    /// </summary>
    public class FileService : IFileService
    {
        private readonly ILogger<FileService> _logger;

        public FileService(ILogger<FileService> logger)
        {
            _logger = logger;
        }

        public async Task<List<ValidationRow>> LoadValidationDataAsync(string filePath)
        {
            _logger.LogInformation($"載入驗證數據：{filePath}");
            
            // 實作文件載入邏輯
            await Task.Delay(500);
            
            return new List<ValidationRow>();
        }

        public async Task SaveValidationResultsAsync(string filePath, List<ValidationRow> data, ValidationStatistics stats)
        {
            _logger.LogInformation($"儲存驗證結果：{filePath}");
            
            // 實作結果儲存邏輯
            await Task.Delay(500);
        }

        public List<string> GetSupportedFileExtensions()
        {
            return new List<string> { ".csv", ".xlsx", ".xls" };
        }
    }

    /// <summary>
    /// 匯出服務實作
    /// </summary>
    public class ExportService : IExportService
    {
        private readonly ILogger<ExportService> _logger;

        public ExportService(ILogger<ExportService> logger)
        {
            _logger = logger;
        }

        public async Task ExportToExcelAsync(string filePath, List<ValidationRow> data, ValidationStatistics stats)
        {
            _logger.LogInformation($"匯出到 Excel：{filePath}");
            
            // 實作 Excel 匯出邏輯
            await Task.Delay(500);
        }

        public async Task ExportToCsvAsync(string filePath, List<ValidationRow> data, ValidationStatistics stats)
        {
            _logger.LogInformation($"匯出到 CSV：{filePath}");
            
            // 實作 CSV 匯出邏輯
            await Task.Delay(500);
        }
    }

    /// <summary>
    /// 設定服務實作
    /// </summary>
    public class ConfigurationService : IConfigurationService
    {
        private readonly ILogger<ConfigurationService> _logger;

        public ConfigurationService(ILogger<ConfigurationService> logger)
        {
            _logger = logger;
        }

        public async Task<AppSettings> LoadSettingsAsync()
        {
            _logger.LogInformation("載入應用程式設定");
            
            // 實作設定載入邏輯
            await Task.Delay(100);
            
            return new AppSettings();
        }

        public async Task SaveSettingsAsync(AppSettings settings)
        {
            _logger.LogInformation("儲存應用程式設定");
            
            // 實作設定儲存邏輯
            await Task.Delay(100);
        }

        public string GetSettingsFilePath()
        {
            return System.IO.Path.Combine(Environment.CurrentDirectory, "appsettings.json");
        }
    }

    #endregion

    #region Data Models

    /// <summary>
    /// 驗證設定
    /// </summary>
    public class ValidationSettings
    {
        public double SimilarityThreshold { get; set; } = 0.3;
        public int MaxConcurrent { get; set; } = 5;
        public double ApiDelay { get; set; } = 1.0;
        public int MaxRetries { get; set; } = 3;
        public bool EnableQueryMetadata { get; set; } = false;
        public string KnowledgeBaseId { get; set; } = string.Empty;
        public string LabelId { get; set; } = string.Empty;
        public bool EnableContextCombination { get; set; } = true;
    }

    /// <summary>
    /// 驗證進度
    /// </summary>
    public class ValidationProgress
    {
        public int Current { get; set; }
        public int Total { get; set; }
        public string Message { get; set; } = string.Empty;
        public string CurrentItem { get; set; } = string.Empty;
    }

    /// <summary>
    /// 應用程式設定
    /// </summary>
    public class AppSettings
    {
        public string ApiBaseUrl { get; set; } = "http://localhost:8000";
        public string ApiKey { get; set; } = string.Empty;
        public ValidationSettings ValidationSettings { get; set; } = new ValidationSettings();
        public string LastUsedFile { get; set; } = string.Empty;
        public string ExportDirectory { get; set; } = string.Empty;
    }

    #endregion
} 