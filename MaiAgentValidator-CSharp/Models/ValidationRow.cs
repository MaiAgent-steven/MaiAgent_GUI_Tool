using System;
using System.Collections.Generic;
using System.ComponentModel;

namespace MaiAgentValidator.Models
{
    /// <summary>
    /// 驗證行數據結構
    /// </summary>
    public class ValidationRow : INotifyPropertyChanged
    {
        // 基本資料
        public string 編號 { get; set; } = string.Empty;
        public string 提問者 { get; set; } = string.Empty;
        public string 問題描述 { get; set; } = string.Empty;
        public string 建議_or_正確答案 { get; set; } = string.Empty;
        public string 應參考的文件 { get; set; } = string.Empty;
        public string 應參考的文件段落 { get; set; } = string.Empty;
        public string 應參考文件UUID { get; set; } = string.Empty;
        public string 是否檢索KM推薦 { get; set; } = string.Empty;

        // API 回覆結果（自動填入）
        private string _ai助理回覆 = string.Empty;
        public string AI助理回覆
        {
            get => _ai助理回覆;
            set
            {
                _ai助理回覆 = value;
                OnPropertyChanged(nameof(AI助理回覆));
            }
        }

        // 驗證結果（自動填入）
        private string _引用節點是否命中 = string.Empty;
        public string 引用節點是否命中
        {
            get => _引用節點是否命中;
            set
            {
                _引用節點是否命中 = value;
                OnPropertyChanged(nameof(引用節點是否命中));
            }
        }

        private string _參考文件是否正確 = string.Empty;
        public string 參考文件是否正確
        {
            get => _參考文件是否正確;
            set
            {
                _參考文件是否正確 = value;
                OnPropertyChanged(nameof(參考文件是否正確));
            }
        }

        private string _回覆是否滿意 = string.Empty;
        public string 回覆是否滿意
        {
            get => _回覆是否滿意;
            set
            {
                _回覆是否滿意 = value;
                OnPropertyChanged(nameof(回覆是否滿意));
            }
        }

        // RAG 增強指標（自動填入）
        private double _precision = 0.0;
        public double Precision
        {
            get => _precision;
            set
            {
                _precision = value;
                OnPropertyChanged(nameof(Precision));
            }
        }

        private double _recall = 0.0;
        public double Recall
        {
            get => _recall;
            set
            {
                _recall = value;
                OnPropertyChanged(nameof(Recall));
            }
        }

        private double _f1Score = 0.0;
        public double F1Score
        {
            get => _f1Score;
            set
            {
                _f1Score = value;
                OnPropertyChanged(nameof(F1Score));
            }
        }

        private double _hitRate = 0.0;
        public double HitRate
        {
            get => _hitRate;
            set
            {
                _hitRate = value;
                OnPropertyChanged(nameof(HitRate));
            }
        }

        // 參考文件命中統計
        private double _參考文件命中率 = 0.0;
        public double 參考文件命中率
        {
            get => _參考文件命中率;
            set
            {
                _參考文件命中率 = value;
                OnPropertyChanged(nameof(參考文件命中率));
            }
        }

        public int 期望文件總數 { get; set; } = 0;
        public int 命中文件數 { get; set; } = 0;
        public string 命中文件 { get; set; } = string.Empty;
        public string 未命中文件 { get; set; } = string.Empty;

        // 用於儲存原始 API 回傳數據
        public List<Dictionary<string, object>> RawCitationNodes { get; set; } = new();
        public List<Dictionary<string, object>> RawCitations { get; set; } = new();

        // 驗證狀態
        private string _驗證狀態 = "待處理";
        public string 驗證狀態
        {
            get => _驗證狀態;
            set
            {
                _驗證狀態 = value;
                OnPropertyChanged(nameof(驗證狀態));
            }
        }

        public event PropertyChangedEventHandler PropertyChanged;

        protected virtual void OnPropertyChanged(string propertyName)
        {
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
        }
    }

    /// <summary>
    /// 組織成員資料結構
    /// </summary>
    public class OrganizationMember
    {
        public string Id { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string Email { get; set; } = string.Empty;
        public bool IsOwner { get; set; }
        public DateTime CreatedAt { get; set; }
        public List<string> Groups { get; set; } = new();
        public Dictionary<string, List<string>> GroupPermissions { get; set; } = new();
    }

    /// <summary>
    /// API 回覆數據結構
    /// </summary>
    public class ApiResponse
    {
        public string? ConversationId { get; set; }
        public string Content { get; set; } = string.Empty;
        public List<Dictionary<string, object>> Citations { get; set; } = new();
        public List<Dictionary<string, object>> CitationNodes { get; set; } = new();
    }

    /// <summary>
    /// 驗證統計結果
    /// </summary>
    public class ValidationStatistics
    {
        public int 總查詢數 { get; set; }
        public int 成功數 { get; set; }
        public int 失敗數 { get; set; }
        public int 跳過數 { get; set; }
        public double 成功率 { get; set; }
        public double 平均Precision { get; set; }
        public double 平均Recall { get; set; }
        public double 平均F1Score { get; set; }
        public double 平均HitRate { get; set; }
        public double 傳統TOP10HitRate { get; set; }
        public double 段落級命中率 { get; set; }
        public double 參考文件正確率 { get; set; }
        public double 文件級整體命中率 { get; set; }
        public int 總預期段落數 { get; set; }
        public int 命中段落數 { get; set; }
        public int 總檢索塊數 { get; set; }
        public int 總期望文件數 { get; set; }
        public int 總命中文件數 { get; set; }
    }
} 