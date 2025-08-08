using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using MaiAgentValidator.Models;

namespace MaiAgentValidator.Services
{
    /// <summary>
    /// 增強型文本匹配器
    /// </summary>
    public class EnhancedTextMatcher
    {
        private readonly ILogger<EnhancedTextMatcher> _logger;

        // 預設的段落分隔符
        private static readonly string[] DefaultSeparators = { "---", "|||", "\n\n", "###", "===", "..." };

        public EnhancedTextMatcher(ILogger<EnhancedTextMatcher> logger)
        {
            _logger = logger;
        }

        /// <summary>
        /// 計算兩個文本之間的相似度
        /// </summary>
        public double CalculateSimilarity(string text1, string text2, string mode = "standard", List<string> expectedSegments = null)
        {
            if (string.IsNullOrEmpty(text1) || string.IsNullOrEmpty(text2))
                return 0.0;

            switch (mode.ToLower())
            {
                case "character_ratio":
                    return CalculateCharacterRatioSimilarity(text1, text2, expectedSegments);
                default:
                    return CalculateSequenceSimilarity(text1, text2);
            }
        }

        /// <summary>
        /// 計算序列相似度（類似 Python 的 difflib.SequenceMatcher）
        /// </summary>
        private double CalculateSequenceSimilarity(string text1, string text2)
        {
            text1 = text1.Trim();
            text2 = text2.Trim();

            if (text1 == text2) return 1.0;
            if (text1.Length == 0 || text2.Length == 0) return 0.0;

            // 使用最長公共子序列算法
            var lcs = GetLongestCommonSubsequence(text1, text2);
            var similarity = (2.0 * lcs.Length) / (text1.Length + text2.Length);

            return Math.Max(0.0, Math.Min(1.0, similarity));
        }

        /// <summary>
        /// 計算字符比例相似度
        /// </summary>
        private double CalculateCharacterRatioSimilarity(string aiChunk, string expectedSegment, List<string> expectedSegments = null)
        {
            aiChunk = aiChunk.Trim();
            expectedSegment = expectedSegment.Trim();

            if (string.IsNullOrEmpty(aiChunk) || string.IsNullOrEmpty(expectedSegment))
                return 0.0;

            // 基本的字符級匹配
            var commonChars = 0;
            var minLength = Math.Min(aiChunk.Length, expectedSegment.Length);

            for (int i = 0; i < minLength; i++)
            {
                if (aiChunk[i] == expectedSegment[i])
                    commonChars++;
            }

            // 計算重疊字符比例
            var overlap = (double)commonChars / Math.Max(aiChunk.Length, expectedSegment.Length);

            // 如果有多個期望段落，考慮整體匹配
            if (expectedSegments != null && expectedSegments.Count > 1)
            {
                var allExpectedText = string.Join(" ", expectedSegments);
                var globalSimilarity = CalculateSequenceSimilarity(aiChunk, allExpectedText);
                overlap = Math.Max(overlap, globalSimilarity * 0.8); // 給予全域匹配一定權重
            }

            return Math.Max(0.0, Math.Min(1.0, overlap));
        }

        /// <summary>
        /// 獲取最長公共子序列
        /// </summary>
        private string GetLongestCommonSubsequence(string text1, string text2)
        {
            var dp = new int[text1.Length + 1, text2.Length + 1];

            // 建立 DP 表
            for (int i = 1; i <= text1.Length; i++)
            {
                for (int j = 1; j <= text2.Length; j++)
                {
                    if (text1[i - 1] == text2[j - 1])
                        dp[i, j] = dp[i - 1, j - 1] + 1;
                    else
                        dp[i, j] = Math.Max(dp[i - 1, j], dp[i, j - 1]);
                }
            }

            // 重建 LCS
            var lcs = new List<char>();
            int x = text1.Length, y = text2.Length;

            while (x > 0 && y > 0)
            {
                if (text1[x - 1] == text2[y - 1])
                {
                    lcs.Insert(0, text1[x - 1]);
                    x--;
                    y--;
                }
                else if (dp[x - 1, y] > dp[x, y - 1])
                    x--;
                else
                    y--;
            }

            return new string(lcs.ToArray());
        }

        /// <summary>
        /// 檢查是否包含關鍵字
        /// </summary>
        public bool ContainsKeywords(string text, string keywords)
        {
            if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(keywords))
                return false;

            var keywordList = keywords.Split(new char[] { ' ', ',', ';', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            return keywordList.Any(keyword => text.Contains(keyword.Trim(), StringComparison.OrdinalIgnoreCase));
        }

        /// <summary>
        /// 解析期望段落
        /// </summary>
        public List<string> ParseExpectedSegments(string expectedContent, List<string> customSeparators = null)
        {
            if (string.IsNullOrEmpty(expectedContent))
                return new List<string>();

            var separators = customSeparators ?? DefaultSeparators.ToList();
            var segments = new List<string> { expectedContent };

            foreach (var separator in separators)
            {
                var newSegments = new List<string>();
                foreach (var segment in segments)
                {
                    var parts = segment.Split(new[] { separator }, StringSplitOptions.RemoveEmptyEntries);
                    newSegments.AddRange(parts);
                }
                segments = newSegments;
            }

            return segments
                .Select(s => s.Trim())
                .Where(s => !string.IsNullOrEmpty(s))
                .ToList();
        }

        /// <summary>
        /// 檢查引用命中
        /// </summary>
        public (bool isHit, string details) CheckCitationHit(
            List<Dictionary<string, object>> citationNodes, 
            string expectedContent, 
            double similarityThreshold = 0.3)
        {
            if (citationNodes == null || citationNodes.Count == 0)
                return (false, "無引用節點");

            if (string.IsNullOrEmpty(expectedContent))
                return (false, "無期望內容");

            var expectedSegments = ParseExpectedSegments(expectedContent);
            if (expectedSegments.Count == 0)
                return (false, "無有效期望段落");

            var hitSegments = new List<string>();
            var details = new List<string>();

            foreach (var segment in expectedSegments)
            {
                var bestMatch = 0.0;
                var bestNode = "";

                foreach (var node in citationNodes)
                {
                    if (node.TryGetValue("content", out var contentObj))
                    {
                        var nodeContent = contentObj?.ToString() ?? "";
                        var similarity = CalculateSimilarity(nodeContent, segment);

                        if (similarity > bestMatch)
                        {
                            bestMatch = similarity;
                            bestNode = nodeContent.Length > 50 ? nodeContent.Substring(0, 50) + "..." : nodeContent;
                        }
                    }
                }

                if (bestMatch >= similarityThreshold)
                {
                    hitSegments.Add(segment);
                    details.Add($"段落「{segment.Substring(0, Math.Min(segment.Length, 20))}...」命中 (相似度: {bestMatch:F2})");
                }
                else
                {
                    details.Add($"段落「{segment.Substring(0, Math.Min(segment.Length, 20))}...」未命中 (最高相似度: {bestMatch:F2})");
                }
            }

            var isHit = hitSegments.Count > 0;
            var detailsText = string.Join("; ", details);

            return (isHit, detailsText);
        }

        /// <summary>
        /// 檢查 RAG 增強命中
        /// </summary>
        public (bool isHit, Dictionary<string, object> ragStats) CheckRagEnhancedHit(
            List<Dictionary<string, object>> citationNodes, 
            string expectedContent,
            double similarityThreshold = 0.3, 
            int? topK = null,
            List<string> customSeparators = null, 
            string similarityMode = "standard")
        {
            var ragStats = new Dictionary<string, object>
            {
                ["precision"] = 0.0,
                ["recall"] = 0.0,
                ["f1_score"] = 0.0,
                ["hit_rate"] = 0.0,
                ["matched_segments"] = 0,
                ["total_expected_segments"] = 0,
                ["total_citation_nodes"] = citationNodes?.Count ?? 0,
                ["relevant_nodes"] = 0
            };

            if (citationNodes == null || citationNodes.Count == 0 || string.IsNullOrEmpty(expectedContent))
                return (false, ragStats);

            var expectedSegments = ParseExpectedSegments(expectedContent, customSeparators);
            ragStats["total_expected_segments"] = expectedSegments.Count;

            if (expectedSegments.Count == 0)
                return (false, ragStats);

            var matchedSegments = 0;
            var relevantNodes = 0;
            var nodeMatches = new HashSet<int>();

            // 檢查每個期望段落
            for (int segmentIndex = 0; segmentIndex < expectedSegments.Count; segmentIndex++)
            {
                var segment = expectedSegments[segmentIndex];
                var bestMatch = 0.0;
                var bestNodeIndex = -1;

                // 檢查每個引用節點
                for (int nodeIndex = 0; nodeIndex < citationNodes.Count; nodeIndex++)
                {
                    var node = citationNodes[nodeIndex];
                    if (node.TryGetValue("content", out var contentObj))
                    {
                        var nodeContent = contentObj?.ToString() ?? "";
                        var similarity = CalculateSimilarity(nodeContent, segment, similarityMode, expectedSegments);

                        if (similarity > bestMatch)
                        {
                            bestMatch = similarity;
                            bestNodeIndex = nodeIndex;
                        }
                    }
                }

                // 如果找到匹配的節點
                if (bestMatch >= similarityThreshold && bestNodeIndex >= 0)
                {
                    matchedSegments++;
                    nodeMatches.Add(bestNodeIndex);
                }
            }

            relevantNodes = nodeMatches.Count;

            // 計算指標
            var precision = citationNodes.Count > 0 ? (double)relevantNodes / citationNodes.Count : 0.0;
            var recall = expectedSegments.Count > 0 ? (double)matchedSegments / expectedSegments.Count : 0.0;
            var f1Score = (precision + recall) > 0 ? 2 * (precision * recall) / (precision + recall) : 0.0;
            var hitRate = recall; // 命中率等於召回率

            ragStats["precision"] = Math.Round(precision, 4);
            ragStats["recall"] = Math.Round(recall, 4);
            ragStats["f1_score"] = Math.Round(f1Score, 4);
            ragStats["hit_rate"] = Math.Round(hitRate, 4);
            ragStats["matched_segments"] = matchedSegments;
            ragStats["relevant_nodes"] = relevantNodes;

            var isHit = matchedSegments > 0;

            _logger.LogDebug($"RAG 分析完成: Precision={precision:F4}, Recall={recall:F4}, F1={f1Score:F4}, 命中段落={matchedSegments}/{expectedSegments.Count}");

            return (isHit, ragStats);
        }

        /// <summary>
        /// 檢查引用文件匹配
        /// </summary>
        public (bool isMatch, Dictionary<string, object> fileStats) CheckCitationFileMatch(
            List<Dictionary<string, object>> citations, 
            string expectedFiles)
        {
            var fileStats = new Dictionary<string, object>
            {
                ["file_hit_rate"] = 0.0,
                ["expected_file_count"] = 0,
                ["matched_file_count"] = 0,
                ["matched_files"] = new List<string>(),
                ["unmatched_files"] = new List<string>()
            };

            if (string.IsNullOrEmpty(expectedFiles))
                return (true, fileStats); // 如果沒有期望文件，視為匹配

            // 解析期望文件（支援換行符分割）
            var expectedFileList = expectedFiles
                .Split(new[] { '\n', '\r' }, StringSplitOptions.RemoveEmptyEntries)
                .Select(f => f.Trim())
                .Where(f => !string.IsNullOrEmpty(f))
                .ToList();

            fileStats["expected_file_count"] = expectedFileList.Count;

            if (expectedFileList.Count == 0)
                return (true, fileStats);

            if (citations == null || citations.Count == 0)
            {
                fileStats["unmatched_files"] = expectedFileList;
                return (false, fileStats);
            }

            // 提取引用的文件標題
            var citedTitles = new HashSet<string>();
            foreach (var citation in citations)
            {
                if (citation.TryGetValue("title", out var titleObj))
                {
                    var title = titleObj?.ToString()?.Trim();
                    if (!string.IsNullOrEmpty(title))
                        citedTitles.Add(title);
                }
            }

            var matchedFiles = new List<string>();
            var unmatchedFiles = new List<string>();

            // 檢查每個期望文件
            foreach (var expectedFile in expectedFileList)
            {
                var isMatched = citedTitles.Any(title => 
                    title.Contains(expectedFile, StringComparison.OrdinalIgnoreCase) ||
                    expectedFile.Contains(title, StringComparison.OrdinalIgnoreCase) ||
                    CalculateSimilarity(title, expectedFile) >= 0.8);

                if (isMatched)
                    matchedFiles.Add(expectedFile);
                else
                    unmatchedFiles.Add(expectedFile);
            }

            var fileHitRate = expectedFileList.Count > 0 ? (double)matchedFiles.Count / expectedFileList.Count : 0.0;
            var isAllMatched = unmatchedFiles.Count == 0;

            fileStats["file_hit_rate"] = Math.Round(fileHitRate, 4);
            fileStats["matched_file_count"] = matchedFiles.Count;
            fileStats["matched_files"] = matchedFiles;
            fileStats["unmatched_files"] = unmatchedFiles;

            _logger.LogDebug($"文件匹配分析: 期望 {expectedFileList.Count} 個文件，匹配 {matchedFiles.Count} 個，命中率 {fileHitRate:F4}");

            return (isAllMatched, fileStats);
        }
    }
} 