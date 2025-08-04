#!/bin/bash

# MaiAgent 驗證工具啟動腳本
# 自動設定環境變數以隱藏 macOS Tk 廢棄警告

echo "🚀 啟動 MaiAgent 管理工具集..."

# 設定環境變數隱藏 Tk 廢棄警告
export TK_SILENCE_DEPRECATION=1

# 檢查 Python 版本
python_version=$(python3 --version 2>&1)
echo "📍 使用 Python 版本: $python_version"

# 檢查必要套件
echo "🔍 檢查必要套件..."
python3 -c "import aiohttp, pandas, openpyxl, tkinter" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ 所有必要套件已安裝"
else
    echo "❌ 缺少必要套件，請執行："
    echo "   pip install -r requirements.txt"
    exit 1
fi

# 啟動程式
echo "▶️ 正在啟動 GUI 應用程式..."

# 檢查是否有常見的啟動問題
if ! python3 -c "import tkinter; from tkinter import ttk; import tkinter as tk; root = tk.Tk(); ttk.Scale(root, from_=0, to=5, orient='horizontal'); root.destroy()" 2>/dev/null; then
    echo "❌ tkinter 初始化測試失敗"
    echo "💡 建議："
    echo "   - 確保已安裝 Python tkinter 支援"
    echo "   - macOS 用戶請確保 XQuartz 已安裝（如果使用 SSH）"
    echo "   - 檢查系統 Python 版本是否支援 GUI"
    exit 1
fi

# 啟動主程式並捕獲錯誤
if python3 maiagent_validation_gui.py 2>&1; then
    echo "👋 程式正常結束"
else
    echo "❌ 程式啟動失敗"
    echo "💡 常見解決方案："
    echo "   1. 檢查所有必要套件是否已安裝: pip install -r requirements.txt"
    echo "   2. 確保 Python 版本 >= 3.7"
    echo "   3. macOS 用戶確保已處理 Tk 廢棄警告"
    echo "   4. 檢查是否有防火牆或權限問題"
    exit 1
fi 