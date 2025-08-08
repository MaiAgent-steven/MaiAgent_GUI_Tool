using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Win32;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using MaiAgentValidator.Models;
using MaiAgentValidator.Services;
using MaiAgentValidator.ViewModels;

namespace MaiAgentValidator
{
    /// <summary>
    /// MainWindow.xaml 的互動邏輯
    /// </summary>
    public partial class MainWindow : Window, INotifyPropertyChanged
    {
        private readonly ILogger<MainWindow> _logger;
        private readonly IServiceProvider _serviceProvider;
        private MaiAgentApiClient _apiClient;
        private EnhancedTextMatcher _textMatcher;
        private CancellationTokenSource _validationCancellationSource;
        
        // 驗證數據
        private ObservableCollection<ValidationRow> _validationData;
        private List<Dictionary<string, object>> _chatbots;
        private string _selectedChatbotId;
        
        // 驗證控制
        private bool _isValidationRunning;
        private int _completedQuestions;
        private int _totalQuestions;

        // 統計數據
        private ValidationStatistics _currentStats;

        public MainWindow(IServiceProvider serviceProvider, ILogger<MainWindow> logger)
        {
            InitializeComponent();
            
            _serviceProvider = serviceProvider;
            _logger = logger;
            _textMatcher = _serviceProvider.GetRequiredService<EnhancedTextMatcher>();
            
            _validationData = new ObservableCollection<ValidationRow>();
            _chatbots = new List<Dictionary<string, object>>();
            _currentStats = new ValidationStatistics();
            
            // 初始化 UI
            InitializeUI();
            
            // 載入設定
            LoadConfiguration();
            
            DataContext = this;
        }

        #region Properties

        public ObservableCollection<ValidationRow> ValidationData
        {
            get => _validationData;
            set
            {
                _validationData = value;
                OnPropertyChanged(nameof(ValidationData));
            }
        }

        public ValidationStatistics CurrentStats
        {
            get => _currentStats;
            set
            {
                _currentStats = value;
                OnPropertyChanged(nameof(CurrentStats));
                UpdateStatsDisplay();
            }
        }

        public bool IsValidationRunning
        {
            get => _isValidationRunning;
            set
            {
                _isValidationRunning = value;
                OnPropertyChanged(nameof(IsValidationRunning));
                UpdateValidationButtons();
            }
        }

        #endregion

        #region UI Initialization

        private void InitializeUI()
        {
            // 設定數據網格的資料來源
            ResultsDataGrid.ItemsSource = ValidationData;
            
            // 初始化滑桿標籤
            UpdateSliderLabels();
            
            _logger.LogInformation("UI 初始化完成");
        }

        private void UpdateSliderLabels()
        {
            SimilarityThresholdLabel.Text = SimilarityThresholdSlider.Value.ToString("F2");
            MaxConcurrentLabel.Text = MaxConcurrentSlider.Value.ToString("F0");
            ApiDelayLabel.Text = ApiDelaySlider.Value.ToString("F1");
            MaxRetriesLabel.Text = MaxRetriesSlider.Value.ToString("F0");
        }

        private void UpdateValidationButtons()
        {
            StartValidationButton.IsEnabled = !IsValidationRunning;
            StopValidationButton.IsEnabled = IsValidationRunning;
            BrowseFileButton.IsEnabled = !IsValidationRunning;
            RetryFailedButton.IsEnabled = !IsValidationRunning;
        }

        private void UpdateStatsDisplay()
        {
            if (CurrentStats != null)
            {
                TotalQueriesLabel.Text = CurrentStats.總查詢數.ToString();
                SuccessRateLabel.Text = $"{CurrentStats.成功率:P1}";
                AverageF1Label.Text = CurrentStats.平均F1Score.ToString("F3");
                HitRateLabel.Text = $"{CurrentStats.平均HitRate:P1}";
            }
        }

        #endregion

        #region Event Handlers - Settings

        private async void TestConnectionButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                await CreateApiClient();
                var isConnected = await _apiClient.TestConnectionAsync();
                
                if (isConnected)
                {
                    MessageBox.Show("連接測試成功！", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
                    _logger.LogInformation("API 連接測試成功");
                }
                else
                {
                    MessageBox.Show("連接測試失敗，請檢查 API 設定。", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                    _logger.LogError("API 連接測試失敗");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"連接測試時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "API 連接測試時發生錯誤");
            }
        }

        private async void RefreshChatbotsButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                await CreateApiClient();
                _chatbots = await _apiClient.GetChatbotsAsync();
                
                ChatbotListBox.Items.Clear();
                foreach (var chatbot in _chatbots)
                {
                    if (chatbot.TryGetValue("name", out var nameObj) && chatbot.TryGetValue("id", out var idObj))
                    {
                        var name = nameObj?.ToString() ?? "未知";
                        var id = idObj?.ToString() ?? "";
                        ChatbotListBox.Items.Add(new { Name = name, Id = id, Display = $"{name} ({id})" });
                    }
                }
                
                _logger.LogInformation($"已載入 {_chatbots.Count} 個聊天機器人");
                MessageBox.Show($"已載入 {_chatbots.Count} 個聊天機器人", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"載入聊天機器人列表時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "載入聊天機器人列表時發生錯誤");
            }
        }

        private void SimilarityThresholdSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
        {
            if (SimilarityThresholdLabel != null)
                SimilarityThresholdLabel.Text = e.NewValue.ToString("F2");
        }

        private void MaxConcurrentSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
        {
            if (MaxConcurrentLabel != null)
                MaxConcurrentLabel.Text = e.NewValue.ToString("F0");
        }

        private void ApiDelaySlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
        {
            if (ApiDelayLabel != null)
                ApiDelayLabel.Text = e.NewValue.ToString("F1");
        }

        private void MaxRetriesSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
        {
            if (MaxRetriesLabel != null)
                MaxRetriesLabel.Text = e.NewValue.ToString("F0");
        }

        private void LoadConfigButton_Click(object sender, RoutedEventArgs e)
        {
            LoadConfiguration();
            MessageBox.Show("設定已載入", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private void SaveConfigButton_Click(object sender, RoutedEventArgs e)
        {
            SaveConfiguration();
            MessageBox.Show("設定已儲存", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private void AboutButton_Click(object sender, RoutedEventArgs e)
        {
            var aboutWindow = new AboutWindow();
            aboutWindow.Owner = this;
            aboutWindow.ShowDialog();
        }

        #endregion

        #region Event Handlers - Validation

        private void BrowseFileButton_Click(object sender, RoutedEventArgs e)
        {
            var openFileDialog = new OpenFileDialog
            {
                Title = "選擇測試文件",
                Filter = "支援的文件|*.csv;*.xlsx;*.xls|CSV 文件|*.csv|Excel 文件|*.xlsx;*.xls|所有文件|*.*",
                RestoreDirectory = true
            };

            if (openFileDialog.ShowDialog() == true)
            {
                CsvFilePathTextBox.Text = openFileDialog.FileName;
                _logger.LogInformation($"選擇測試文件: {openFileDialog.FileName}");
            }
        }

        private async void StartValidationButton_Click(object sender, RoutedEventArgs e)
        {
            if (!ValidateValidationSettings())
                return;

            try
            {
                IsValidationRunning = true;
                _validationCancellationSource = new CancellationTokenSource();
                
                // 載入測試數據
                await LoadValidationData();
                
                // 開始驗證
                await RunValidation(_validationCancellationSource.Token);
                
                MessageBox.Show("驗證完成！", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (OperationCanceledException)
            {
                AppendLog("驗證已取消");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"驗證時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "驗證時發生錯誤");
            }
            finally
            {
                IsValidationRunning = false;
                _validationCancellationSource?.Dispose();
                _validationCancellationSource = null;
            }
        }

        private void StopValidationButton_Click(object sender, RoutedEventArgs e)
        {
            _validationCancellationSource?.Cancel();
            AppendLog("正在停止驗證...");
        }

        private async void RetryFailedButton_Click(object sender, RoutedEventArgs e)
        {
            var openFileDialog = new OpenFileDialog
            {
                Title = "選擇要重測的驗證結果文件",
                Filter = "CSV 文件|*.csv|所有文件|*.*",
                RestoreDirectory = true
            };

            if (openFileDialog.ShowDialog() == true)
            {
                try
                {
                    // 載入失敗問題並重新測試
                    await RetryFailedQuestions(openFileDialog.FileName);
                }
                catch (Exception ex)
                {
                    MessageBox.Show($"重測失敗問題時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                    _logger.LogError(ex, "重測失敗問題時發生錯誤");
                }
            }
        }

        private void ClearLogButton_Click(object sender, RoutedEventArgs e)
        {
            LogTextBox.Clear();
        }

        private void ExportLogButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                var saveFileDialog = new SaveFileDialog
                {
                    Title = "匯出日誌",
                    Filter = "文字文件|*.txt|所有文件|*.*",
                    DefaultExt = "txt",
                    FileName = $"MaiAgent_Log_{DateTime.Now:yyyyMMdd_HHmmss}.txt"
                };

                if (saveFileDialog.ShowDialog() == true)
                {
                    File.WriteAllText(saveFileDialog.FileName, LogTextBox.Text);
                    MessageBox.Show("日誌已匯出", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"匯出日誌時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "匯出日誌時發生錯誤");
            }
        }

        #endregion

        #region Event Handlers - Results

        private void ExportResultsButton_Click(object sender, RoutedEventArgs e)
        {
            if (ValidationData.Count == 0)
            {
                MessageBox.Show("沒有可匯出的結果", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            try
            {
                var saveFileDialog = new SaveFileDialog
                {
                    Title = "匯出驗證結果",
                    Filter = "Excel 文件|*.xlsx|CSV 文件|*.csv|所有文件|*.*",
                    DefaultExt = "xlsx",
                    FileName = $"MaiAgent_Results_{DateTime.Now:yyyyMMdd_HHmmss}.xlsx"
                };

                if (saveFileDialog.ShowDialog() == true)
                {
                    ExportResults(saveFileDialog.FileName);
                    MessageBox.Show("結果已匯出", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"匯出結果時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "匯出結果時發生錯誤");
            }
        }

        private void OpenResultsFolderButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                var resultsFolder = Path.Combine(Environment.CurrentDirectory, "exports");
                if (!Directory.Exists(resultsFolder))
                    Directory.CreateDirectory(resultsFolder);

                System.Diagnostics.Process.Start("explorer.exe", resultsFolder);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"開啟結果資料夾時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "開啟結果資料夾時發生錯誤");
            }
        }

        #endregion

        #region Event Handlers - Organization Management

        private async void TestOrgConnectionButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                var apiClient = CreateOrgApiClient();
                var isConnected = await apiClient.TestConnectionAsync();
                
                if (isConnected)
                {
                    MessageBox.Show("組織管理 API 連接測試成功！", "成功", MessageBoxButton.OK, MessageBoxImage.Information);
                }
                else
                {
                    MessageBox.Show("組織管理 API 連接測試失敗，請檢查設定。", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"組織管理 API 連接測試時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "組織管理 API 連接測試時發生錯誤");
            }
        }

        private async void LoadOrganizationsButton_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                var apiClient = CreateOrgApiClient();
                var organizations = await apiClient.GetOrganizationsAsync();
                
                OrganizationListBox.Items.Clear();
                foreach (var org in organizations)
                {
                    if (org.TryGetValue("name", out var nameObj) && org.TryGetValue("id", out var idObj))
                    {
                        var name = nameObj?.ToString() ?? "未知";
                        var id = idObj?.ToString() ?? "";
                        OrganizationListBox.Items.Add(new { Name = name, Id = id, Display = $"{name} ({id})" });
                    }
                }
                
                AppendExportLog($"已載入 {organizations.Count} 個組織");
            }
            catch (Exception ex)
            {
                MessageBox.Show($"載入組織列表時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "載入組織列表時發生錯誤");
            }
        }

        private async void StartExportButton_Click(object sender, RoutedEventArgs e)
        {
            if (OrganizationListBox.SelectedItem == null)
            {
                MessageBox.Show("請選擇要匯出的組織", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
                return;
            }

            try
            {
                // 實作組織匯出邏輯
                AppendExportLog("開始匯出組織資料...");
                MessageBox.Show("組織匯出功能開發中", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show($"匯出組織時發生錯誤：{ex.Message}", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                _logger.LogError(ex, "匯出組織時發生錯誤");
            }
        }

        #endregion

        #region Helper Methods

        private bool ValidateValidationSettings()
        {
            if (string.IsNullOrEmpty(CsvFilePathTextBox.Text))
            {
                MessageBox.Show("請選擇測試文件", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
                return false;
            }

            if (!File.Exists(CsvFilePathTextBox.Text))
            {
                MessageBox.Show("測試文件不存在", "錯誤", MessageBoxButton.OK, MessageBoxImage.Error);
                return false;
            }

            if (ChatbotListBox.SelectedItem == null)
            {
                MessageBox.Show("請選擇聊天機器人", "提示", MessageBoxButton.OK, MessageBoxImage.Information);
                return false;
            }

            return true;
        }

        private async Task CreateApiClient()
        {
            var baseUrl = ApiBaseUrlTextBox.Text?.Trim();
            var apiKey = ApiKeyPasswordBox.Password?.Trim();

            if (string.IsNullOrEmpty(baseUrl) || string.IsNullOrEmpty(apiKey))
            {
                throw new InvalidOperationException("請設定 API 基礎 URL 和金鑰");
            }

            _apiClient?.Dispose();
            _apiClient = new MaiAgentApiClient(baseUrl, apiKey, _serviceProvider.GetRequiredService<ILogger<MaiAgentApiClient>>());
        }

        private MaiAgentApiClient CreateOrgApiClient()
        {
            var baseUrl = OrgExportApiUrlTextBox.Text?.Trim();
            var apiKey = OrgExportApiKeyPasswordBox.Password?.Trim();

            if (string.IsNullOrEmpty(baseUrl) || string.IsNullOrEmpty(apiKey))
            {
                throw new InvalidOperationException("請設定組織管理 API 基礎 URL 和金鑰");
            }

            return new MaiAgentApiClient(baseUrl, apiKey, _serviceProvider.GetRequiredService<ILogger<MaiAgentApiClient>>());
        }

        private void AppendLog(string message)
        {
            Dispatcher.Invoke(() =>
            {
                var timestamp = DateTime.Now.ToString("HH:mm:ss");
                LogTextBox.AppendText($"[{timestamp}] {message}\n");
                LogTextBox.ScrollToEnd();
            });
            
            _logger.LogInformation(message);
        }

        private void AppendExportLog(string message)
        {
            Dispatcher.Invoke(() =>
            {
                var timestamp = DateTime.Now.ToString("HH:mm:ss");
                ExportLogTextBox.AppendText($"[{timestamp}] {message}\n");
                ExportLogTextBox.ScrollToEnd();
            });
            
            _logger.LogInformation($"組織匯出: {message}");
        }

        private void UpdateProgress(int current, int total, string message = null)
        {
            Dispatcher.Invoke(() =>
            {
                ValidationProgressBar.Maximum = total;
                ValidationProgressBar.Value = current;
                
                var progressText = message ?? $"進度: {current}/{total}";
                ProgressLabel.Text = progressText;
            });
        }

        #endregion

        #region Configuration

        private void LoadConfiguration()
        {
            try
            {
                // 實作設定載入邏輯
                // 可以使用 .NET 的 IConfiguration 或自定義設定檔
                _logger.LogInformation("設定已載入");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "載入設定時發生錯誤");
            }
        }

        private void SaveConfiguration()
        {
            try
            {
                // 實作設定儲存邏輯
                _logger.LogInformation("設定已儲存");
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "儲存設定時發生錯誤");
            }
        }

        #endregion

        #region Validation Logic (Placeholder)

        private async Task LoadValidationData()
        {
            // 載入 CSV/Excel 文件的邏輯
            AppendLog("載入測試數據中...");
            
            // 實作文件讀取邏輯
            await Task.Delay(1000); // 模擬載入時間
            
            AppendLog("測試數據載入完成");
        }

        private async Task RunValidation(CancellationToken cancellationToken)
        {
            // 實作驗證邏輯
            AppendLog("開始執行驗證...");
            
            try
            {
                // 模擬驗證過程
                for (int i = 0; i < 10; i++)
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    
                    UpdateProgress(i + 1, 10, $"正在處理問題 {i + 1}/10");
                    await Task.Delay(1000, cancellationToken);
                }
                
                AppendLog("驗證完成");
            }
            catch (OperationCanceledException)
            {
                AppendLog("驗證已取消");
                throw;
            }
        }

        private async Task RetryFailedQuestions(string fileName)
        {
            // 實作重測失敗問題的邏輯
            AppendLog($"載入失敗問題文件: {fileName}");
            
            await Task.Delay(500); // 模擬處理時間
            
            AppendLog("重測功能開發中...");
        }

        private void ExportResults(string fileName)
        {
            // 實作結果匯出邏輯
            _logger.LogInformation($"匯出結果到: {fileName}");
        }

        #endregion

        #region INotifyPropertyChanged

        public event PropertyChangedEventHandler PropertyChanged;

        protected virtual void OnPropertyChanged(string propertyName)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        }

        #endregion

        protected override void OnClosing(CancelEventArgs e)
        {
            // 如果驗證正在進行，詢問是否確定關閉
            if (IsValidationRunning)
            {
                var result = MessageBox.Show(
                    "驗證正在進行中，確定要關閉程式嗎？",
                    "確認關閉",
                    MessageBoxButton.YesNo,
                    MessageBoxImage.Question);

                if (result == MessageBoxResult.No)
                {
                    e.Cancel = true;
                    return;
                }

                // 取消驗證
                _validationCancellationSource?.Cancel();
            }

            // 清理資源
            _apiClient?.Dispose();
            _validationCancellationSource?.Dispose();

            base.OnClosing(e);
        }
    }
} 