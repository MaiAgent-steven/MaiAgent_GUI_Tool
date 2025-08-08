using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using System.Threading;
using Newtonsoft.Json;
using Microsoft.Extensions.Logging;
using MaiAgentValidator.Models;

namespace MaiAgentValidator.Services
{
    /// <summary>
    /// MaiAgent API 客戶端
    /// </summary>
    public class MaiAgentApiClient : IDisposable
    {
        private readonly HttpClient _httpClient;
        private readonly ILogger<MaiAgentApiClient> _logger;
        private readonly string _baseUrl;
        private readonly string _apiKey;
        private bool _disposed = false;

        public MaiAgentApiClient(string baseUrl, string apiKey, ILogger<MaiAgentApiClient> logger)
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _apiKey = apiKey;
            _logger = logger;

            _httpClient = new HttpClient();
            _httpClient.DefaultRequestHeaders.Add("Authorization", $"Bearer {apiKey}");
            _httpClient.DefaultRequestHeaders.Add("User-Agent", "MaiAgent-Validator-CSharp/4.2.6");
            _httpClient.Timeout = TimeSpan.FromMinutes(5);
        }

        /// <summary>
        /// 建構 API URL
        /// </summary>
        private string BuildApiUrl(string endpoint)
        {
            if (endpoint.StartsWith("/"))
                endpoint = endpoint.Substring(1);

            if (_baseUrl.Contains("/api/"))
                return $"{_baseUrl}/{endpoint}";
            else
                return $"{_baseUrl}/api/{endpoint}";
        }

        /// <summary>
        /// 獲取聊天機器人列表
        /// </summary>
        public async Task<List<Dictionary<string, object>>> GetChatbotsAsync()
        {
            try
            {
                var url = BuildApiUrl("chatbots/");
                _logger.LogInformation($"正在獲取聊天機器人列表: {url}");

                var response = await _httpClient.GetAsync(url);
                var content = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogError($"API 請求失敗: {response.StatusCode} - {content}");
                    throw new HttpRequestException($"API 請求失敗: {response.StatusCode}");
                }

                var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(content);
                if (result?.ContainsKey("results") == true)
                {
                    var resultsJson = result["results"].ToString();
                    return JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(resultsJson) ?? new List<Dictionary<string, object>>();
                }

                return new List<Dictionary<string, object>>();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "獲取聊天機器人列表時發生錯誤");
                throw;
            }
        }

        /// <summary>
        /// 發送訊息到 AI 助理
        /// </summary>
        public async Task<ApiResponse> SendMessageAsync(
            string chatbotId, 
            string message, 
            string conversationId = null, 
            int maxRetries = 3,
            Dictionary<string, object> queryMetadata = null,
            CancellationToken cancellationToken = default)
        {
            Exception lastException = null;

            for (int attempt = 1; attempt <= maxRetries; attempt++)
            {
                try
                {
                    var url = BuildApiUrl($"chatbots/{chatbotId}/chat/");
                    
                    var payload = new Dictionary<string, object>
                    {
                        ["message"] = message,
                        ["stream"] = false
                    };

                    if (!string.IsNullOrEmpty(conversationId))
                        payload["conversation_id"] = conversationId;

                    if (queryMetadata != null && queryMetadata.Count > 0)
                        payload["query_metadata"] = queryMetadata;

                    var jsonContent = JsonConvert.SerializeObject(payload);
                    var content = new StringContent(jsonContent, Encoding.UTF8, "application/json");

                    _logger.LogInformation($"發送訊息 (嘗試 {attempt}/{maxRetries}): {chatbotId}");

                    var response = await _httpClient.PostAsync(url, content, cancellationToken);
                    var responseContent = await response.Content.ReadAsStringAsync();

                    if (!response.IsSuccessStatusCode)
                    {
                        _logger.LogWarning($"API 請求失敗 (嘗試 {attempt}/{maxRetries}): {response.StatusCode} - {responseContent}");
                        
                        if (attempt == maxRetries)
                            throw new HttpRequestException($"API 請求失敗: {response.StatusCode} - {responseContent}");
                        
                        await Task.Delay(1000 * attempt, cancellationToken); // 指數退避
                        continue;
                    }

                    var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(responseContent);
                    
                    return new ApiResponse
                    {
                        ConversationId = result?.ContainsKey("conversation_id") == true ? result["conversation_id"]?.ToString() : null,
                        Content = result?.ContainsKey("content") == true ? result["content"]?.ToString() ?? string.Empty : string.Empty,
                        Citations = ExtractCitations(result),
                        CitationNodes = ExtractCitationNodes(result)
                    };
                }
                catch (OperationCanceledException)
                {
                    _logger.LogInformation("發送訊息被取消");
                    throw;
                }
                catch (Exception ex)
                {
                    lastException = ex;
                    _logger.LogWarning(ex, $"發送訊息時發生錯誤 (嘗試 {attempt}/{maxRetries})");
                    
                    if (attempt == maxRetries)
                        break;
                    
                    await Task.Delay(1000 * attempt, cancellationToken);
                }
            }

            _logger.LogError(lastException, "發送訊息失敗，已達到最大重試次數");
            throw lastException ?? new Exception("發送訊息失敗");
        }

        /// <summary>
        /// 獲取組織列表
        /// </summary>
        public async Task<List<Dictionary<string, object>>> GetOrganizationsAsync()
        {
            try
            {
                var url = BuildApiUrl("organizations/");
                _logger.LogInformation($"正在獲取組織列表: {url}");

                var response = await _httpClient.GetAsync(url);
                var content = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogError($"API 請求失敗: {response.StatusCode} - {content}");
                    throw new HttpRequestException($"API 請求失敗: {response.StatusCode}");
                }

                var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(content);
                if (result?.ContainsKey("results") == true)
                {
                    var resultsJson = result["results"].ToString();
                    return JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(resultsJson) ?? new List<Dictionary<string, object>>();
                }

                return new List<Dictionary<string, object>>();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "獲取組織列表時發生錯誤");
                throw;
            }
        }

        /// <summary>
        /// 獲取組織成員
        /// </summary>
        public async Task<List<Dictionary<string, object>>> GetOrganizationMembersAsync(string orgId)
        {
            try
            {
                var url = BuildApiUrl($"organizations/{orgId}/members/");
                _logger.LogInformation($"正在獲取組織成員: {url}");

                var response = await _httpClient.GetAsync(url);
                var content = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogError($"API 請求失敗: {response.StatusCode} - {content}");
                    throw new HttpRequestException($"API 請求失敗: {response.StatusCode}");
                }

                var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(content);
                if (result?.ContainsKey("results") == true)
                {
                    var resultsJson = result["results"].ToString();
                    return JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(resultsJson) ?? new List<Dictionary<string, object>>();
                }

                return new List<Dictionary<string, object>>();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "獲取組織成員時發生錯誤");
                throw;
            }
        }

        /// <summary>
        /// 獲取知識庫列表
        /// </summary>
        public async Task<List<Dictionary<string, object>>> GetKnowledgeBasesAsync()
        {
            try
            {
                var url = BuildApiUrl("knowledge_bases/");
                _logger.LogInformation($"正在獲取知識庫列表: {url}");

                var response = await _httpClient.GetAsync(url);
                var content = await response.Content.ReadAsStringAsync();

                if (!response.IsSuccessStatusCode)
                {
                    _logger.LogError($"API 請求失敗: {response.StatusCode} - {content}");
                    throw new HttpRequestException($"API 請求失敗: {response.StatusCode}");
                }

                var result = JsonConvert.DeserializeObject<Dictionary<string, object>>(content);
                if (result?.ContainsKey("results") == true)
                {
                    var resultsJson = result["results"].ToString();
                    return JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(resultsJson) ?? new List<Dictionary<string, object>>();
                }

                return new List<Dictionary<string, object>>();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "獲取知識庫列表時發生錯誤");
                throw;
            }
        }

        /// <summary>
        /// 測試連接
        /// </summary>
        public async Task<bool> TestConnectionAsync()
        {
            try
            {
                await GetChatbotsAsync();
                return true;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// 提取引用資訊
        /// </summary>
        private List<Dictionary<string, object>> ExtractCitations(Dictionary<string, object> result)
        {
            try
            {
                if (result?.ContainsKey("citations") == true)
                {
                    var citationsJson = result["citations"].ToString();
                    return JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(citationsJson) ?? new List<Dictionary<string, object>>();
                }
                return new List<Dictionary<string, object>>();
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "提取引用資訊時發生錯誤");
                return new List<Dictionary<string, object>>();
            }
        }

        /// <summary>
        /// 提取引用節點資訊
        /// </summary>
        private List<Dictionary<string, object>> ExtractCitationNodes(Dictionary<string, object> result)
        {
            try
            {
                if (result?.ContainsKey("citation_nodes") == true)
                {
                    var citationNodesJson = result["citation_nodes"].ToString();
                    return JsonConvert.DeserializeObject<List<Dictionary<string, object>>>(citationNodesJson) ?? new List<Dictionary<string, object>>();
                }
                return new List<Dictionary<string, object>>();
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "提取引用節點資訊時發生錯誤");
                return new List<Dictionary<string, object>>();
            }
        }

        public void Dispose()
        {
            if (!_disposed)
            {
                _httpClient?.Dispose();
                _disposed = true;
            }
        }
    }
} 