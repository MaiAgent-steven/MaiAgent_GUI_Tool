#!/usr/bin/env python3
"""
MaiAgent Django 自動化驗證工具 - GUI 版本

具有圖形化使用者界面的 AI 助理回覆品質驗證工具
支援 RAG 增強統計分析功能
"""

# 版本信息
__version__ = "4.2.6"
__app_name__ = "MaiAgent 管理工具集"
__build_date__ = "2025-01-27"
__author__ = "MaiAgent Team"
__description__ = "AI 助理回覆品質驗證與組織管理工具 - RAG 增強版"

import asyncio
import csv
import configparser
import json
import logging
import mimetypes
import os
import platform
import re
import subprocess
import sys
import threading
# 隱藏 macOS Tk 廢棄警告
os.environ['TK_SILENCE_DEPRECATION'] = '1'
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import webbrowser
import time

import aiohttp
import pandas as pd
from difflib import SequenceMatcher


# 設定日誌
def setup_logging():
    """設定增強版日誌系統"""
    # 創建日誌目錄
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # 設定日誌格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 清除現有的處理器
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 設定根日誌
    logging.basicConfig(
        level=logging.DEBUG,
        format=log_format,
        datefmt=date_format,
        handlers=[
            # 主日誌文件 - 記錄所有級別
            logging.FileHandler(
                log_dir / f'validation_main_{pd.Timestamp.now().strftime("%Y%m%d")}.log', 
                encoding='utf-8'
            ),
            # 錯誤日誌文件 - 只記錄錯誤
            logging.FileHandler(
                log_dir / f'validation_error_{pd.Timestamp.now().strftime("%Y%m%d")}.log', 
                encoding='utf-8'
            ),
            # 控制台輸出
            logging.StreamHandler()
        ]
    )
    
    # 設定錯誤處理器只記錄ERROR及以上級別
    error_handler = logging.getLogger().handlers[1]
    error_handler.setLevel(logging.ERROR)
    
    return logging.getLogger(__name__)

logger = setup_logging()


@dataclass
class ValidationRow:
    """驗證行數據結構"""
    編號: str
    提問者: str
    問題描述: str
    建議_or_正確答案: str
    應參考的文件: str
    應參考的文件段落: str
    應參考文件UUID: str = ""  # 新增欄位，用於UUID匹配
    是否檢索KM推薦: str = ""  # 新增欄位，控制是否進行驗證
    
    # API 回覆結果（自動填入）
    AI助理回覆: str = ""
    # 動態引用節點欄位（將在處理時動態添加）
    # 動態參考文件欄位（將在處理時動態添加）
    
    # 驗證結果（自動填入）
    引用節點是否命中: str = ""
    參考文件是否正確: str = ""
    回覆是否滿意: str = ""
    
    # RAG 增強指標（自動填入）
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    hit_rate: float = 0.0
    
    # 參考文件命中統計（新增）
    參考文件命中率: float = 0.0
    期望文件總數: int = 0
    命中文件數: int = 0
    命中文件: str = ""  # 新增：格式化的命中文件列表
    未命中文件: str = ""
    
    # 用於儲存原始 API 回傳數據
    _raw_citation_nodes: List[Dict] = None
    _raw_citations: List[Dict] = None
    
    def __post_init__(self):
        if self._raw_citation_nodes is None:
            self._raw_citation_nodes = []
        if self._raw_citations is None:
            self._raw_citations = []


@dataclass
class OrganizationMember:
    """組織成員資料結構"""
    id: str
    name: str
    email: str
    is_owner: bool
    created_at: str
    groups: List[str]
    group_permissions: Dict[str, List[str]]


@dataclass
class DeploymentTask:
    """部署任務資料結構"""
    task_id: str
    csv_file: str
    api_key: str
    base_url: str
    organization_name: str
    create_users: bool
    referral_code: str
    status: str = "pending"
    progress: int = 0
    log_messages: List[str] = None
    
    def __post_init__(self):
        if self.log_messages is None:
            self.log_messages = []


@dataclass
class ApiResponse:
    """API 回覆數據結構"""
    conversation_id: Optional[str]
    content: str
    citations: List[Dict]
    citation_nodes: List[Dict]


class MaiAgentApiClient:
    """MaiAgent API 客戶端"""
    
    def __init__(self, base_url: str, api_key: str, logger_callback=None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.session = None
        self.logger_callback = logger_callback
    
    def _build_api_url(self, endpoint: str) -> str:
        """智能構建API URL，避免重複的/api路徑"""
        base_url = self.base_url.rstrip('/')
        endpoint = endpoint.lstrip('/')
        
        # 如果base_url已經包含/api，直接使用
        if base_url.endswith('/api'):
            return f"{base_url}/{endpoint}"
        # 如果base_url是主域名，自動添加/api
        elif base_url.endswith('.ai') or base_url.endswith('.com') or '/api' not in base_url:
            return f"{base_url}/api/{endpoint}"
        # 其他情況直接拼接
        else:
            return f"{base_url}/{endpoint}"
        
    def _log_api_request(self, url, method, payload=None, headers=None):
        """記錄API請求 - 增強版本"""
        if self.logger_callback:
            # 記錄基本請求信息
            self.logger_callback('log_api_request', url, method, payload)
            
            # 記錄詳細的請求信息
            details = [
                f"🚀 API請求詳情:",
                f"   方法: {method}",
                f"   URL: {url}",
            ]
            
            if headers:
                details.append(f"   請求Headers:")
                for key, value in headers.items():
                    # 隱藏敏感信息
                    if 'authorization' in key.lower() or 'api-key' in key.lower():
                        details.append(f"     {key}: {value[:20]}..." if len(str(value)) > 20 else f"     {key}: {value}")
                    else:
                        details.append(f"     {key}: {value}")
            
            if payload:
                details.append(f"   請求載荷:")
                if isinstance(payload, dict):
                    import json
                    try:
                        payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
                        # 限制載荷長度以避免日誌過長 - 增加到2000字元
                        if len(payload_str) > 2000:
                            payload_str = payload_str[:2000] + "...(內容已截斷)"
                        details.append(f"     {payload_str}")
                    except:
                        details.append(f"     {str(payload)[:2000]}...")
                else:
                    details.append(f"     {str(payload)[:2000]}...")
            
            # 發送詳細日誌
            for detail in details:
                if self.logger_callback:
                    self.logger_callback('log_info', detail, 'API')
    
    def _log_api_response(self, url, status_code, response_size=0, duration=None, response_data=None, response_headers=None):
        """記錄API回應 - 增強版本"""
        if self.logger_callback:
            # 記錄基本回應信息
            self.logger_callback('log_api_response', url, status_code, response_size, duration)
            
            # 記錄詳細的回應信息
            details = [
                f"📥 API回應詳情:",
                f"   URL: {url}",
                f"   狀態碼: {status_code}",
                f"   回應大小: {response_size} 字元",
            ]
            
            if duration:
                details.append(f"   耗時: {duration:.2f}秒")
            
            if response_headers:
                details.append(f"   回應Headers:")
                for key, value in response_headers.items():
                    details.append(f"     {key}: {value}")
            
            if response_data:
                details.append(f"   回應內容:")
                if isinstance(response_data, dict):
                    import json
                    try:
                        response_str = json.dumps(response_data, indent=2, ensure_ascii=False)
                        # 限制回應長度以避免日誌過長 - 增加到5000字元
                        if len(response_str) > 5000:
                            response_str = response_str[:5000] + "...(內容已截斷)"
                        details.append(f"     {response_str}")
                    except:
                        details.append(f"     {str(response_data)[:1000]}...")
                elif isinstance(response_data, str):
                    if len(response_data) > 5000:
                        details.append(f"     {response_data[:5000]}...(內容已截斷)")
                    else:
                        details.append(f"     {response_data}")
                else:
                    details.append(f"     {str(response_data)[:5000]}...")
            
            # 發送詳細日誌
            log_level = 'log_info' if 200 <= status_code < 300 else 'log_error'
            for detail in details:
                if self.logger_callback:
                    self.logger_callback(log_level, detail, 'API')
        
    async def __aenter__(self):
        headers = {
            'Authorization': f'Api-Key {self.api_key}',
            'Content-Type': 'application/json'
        }
        # 添加超時設定和連接池配置
        timeout = aiohttp.ClientTimeout(total=90, connect=10, sock_read=60)
        connector = aiohttp.TCPConnector(
            limit=100,  # 總連接池大小
            limit_per_host=20,  # 每個主機的連接數
            enable_cleanup_closed=True,  # 啟用清理關閉的連接
            force_close=False,  # 允許連接重用以提高性能
            keepalive_timeout=30  # 保持連接的超時時間
        )
        self.session = aiohttp.ClientSession(
            headers=headers, 
            timeout=timeout,
            connector=connector
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_chatbots(self) -> List[Dict]:
        """獲取可用的聊天機器人列表（支援分頁）"""
        if not self.session:
            raise Exception("API Client session not initialized")
            
        all_chatbots = []
        url = self._build_api_url("chatbots/")
        page_number = 1
        
        while url:
            start_time = pd.Timestamp.now()
            
            self._log_api_request(url, 'GET')
            
            async with self.session.get(url) as response:
                duration = (pd.Timestamp.now() - start_time).total_seconds()
                response_text = await response.text()
                
                self._log_api_response(url, response.status, len(response_text), duration)
                
                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list):
                        # 直接返回列表（非分頁格式）
                        return data
                    elif isinstance(data, dict):
                        # 分頁格式
                        current_results = data.get('results', [])
                        all_chatbots.extend(current_results)
                        
                        # 檢查是否有下一頁
                        next_url = data.get('next')
                        if next_url:
                            url = next_url
                            page_number += 1
                            # 記錄分頁進度
                            total_count = data.get('count', 0)
                            current_count = len(all_chatbots)
                            if self.logger_callback:
                                self.logger_callback('log_info', f"📄 已載入第 {page_number-1} 頁，共 {current_count}/{total_count} 個聊天機器人")
                        else:
                            # 沒有下一頁，結束循環
                            url = None
                    else:
                        return []
                else:
                    raise Exception(f"獲取聊天機器人列表失敗: {response.status} - {response_text}")
        
        return all_chatbots
    
    async def send_message(self, chatbot_id: str, message: str, conversation_id: Optional[str] = None, max_retries: int = 3, query_metadata: Optional[Dict] = None) -> ApiResponse:
        """發送訊息到指定的聊天機器人（具備重試機制）"""
        if not self.session:
            raise Exception("API Client session not initialized")
            
        url = self._build_api_url(f"chatbots/{chatbot_id}/completions/")
        
        # 構建基本載荷
        message_data = {
            "content": message,
            "attachments": []
        }
        
        # 如果提供了 query_metadata，添加到 message 中
        if query_metadata:
            message_data["query_metadata"] = query_metadata
        
        payload = {
            "conversation": conversation_id,
            "message": message_data,
            "isStreaming": False
        }
        
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                start_time = pd.Timestamp.now()
                self._log_api_request(url, 'POST', payload)
                
                async with self.session.post(url, json=payload) as response:
                    duration = (pd.Timestamp.now() - start_time).total_seconds()
                    response_text = await response.text()
                    
                    # 記錄原始回應文本
                    self._log_api_response(url, response.status, len(response_text), duration, response_data=response_text)
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        # 額外記錄解析後的JSON結構以便於除錯
                        if self.logger_callback:
                            self.logger_callback('log_info', f"🔍 解析後的API回應結構:", 'API')
                            self.logger_callback('log_info', f"   - conversationId: {data.get('conversationId', 'N/A')}", 'API')
                            self.logger_callback('log_info', f"   - content length: {len(data.get('content', ''))}", 'API')
                            self.logger_callback('log_info', f"   - citations count: {len(data.get('citations', []))}", 'API')
                            self.logger_callback('log_info', f"   - citationNodes count: {len(data.get('citationNodes', []))}", 'API')
                            
                            # 記錄citations結構
                            citations = data.get('citations', [])
                            if citations:
                                self.logger_callback('log_info', f"   📄 Citations 詳情:", 'API')
                                for i, citation in enumerate(citations[:3], 1):  # 只顯示前3個
                                    self.logger_callback('log_info', f"     {i}. filename: {citation.get('filename', 'N/A')}", 'API')
                                    self.logger_callback('log_info', f"        labels: {citation.get('labels', [])}", 'API')
                            
                            # 記錄citationNodes結構
                            citation_nodes = data.get('citationNodes', [])
                            if citation_nodes:
                                self.logger_callback('log_info', f"   📝 CitationNodes 詳情:", 'API')
                                for i, node in enumerate(citation_nodes[:3], 1):  # 只顯示前3個
                                    if 'chatbotTextNode' in node:
                                        if 'text' in node['chatbotTextNode']:
                                            content_preview = node['chatbotTextNode'].get('text', '')[:100]
                                            self.logger_callback('log_info', f"     {i}. chatbotTextNode.text: {content_preview}...", 'API')
                                        elif 'content' in node['chatbotTextNode']:
                                            content_preview = node['chatbotTextNode'].get('content', '')[:100]
                                            self.logger_callback('log_info', f"     {i}. chatbotTextNode.content: {content_preview}...", 'API')
                                        else:
                                            self.logger_callback('log_info', f"     {i}. chatbotTextNode結構: {list(node['chatbotTextNode'].keys())}", 'API')
                                    elif 'text' in node:
                                        content_preview = node.get('text', '')[:100]
                                        self.logger_callback('log_info', f"     {i}. text: {content_preview}...", 'API')
                                    else:
                                        self.logger_callback('log_info', f"     {i}. 結構: {list(node.keys())}", 'API')
                        
                        return ApiResponse(
                            conversation_id=data.get('conversationId'),
                            content=data.get('content', ''),
                            citations=data.get('citations', []),
                            citation_nodes=data.get('citationNodes', [])
                        )
                    else:
                        raise Exception(f"發送訊息失敗: {response.status} - {response_text}")
                        
            except (aiohttp.ClientError, aiohttp.ServerTimeoutError, asyncio.TimeoutError, 
                    ConnectionError, OSError) as e:
                last_exception = e
                error_str = str(e).lower()
                
                # 特殊處理連接重置錯誤（WinError 10054）
                is_connection_reset = any(keyword in error_str for keyword in [
                    'winerror 10054', 'connection was forcibly closed', 
                    'connection reset', 'connection aborted'
                ])
                
                if self.logger_callback:
                    if is_connection_reset:
                        self.logger_callback('log_warning', f"🔌 連接被遠端主機重置 (嘗試 {attempt + 1}/{max_retries}): {str(e)}", 'API')
                        self.logger_callback('log_info', f"   💡 建議：降低併發數量或增加延遲時間", 'API')
                    else:
                        self.logger_callback('log_warning', f"⚠️ API 請求失敗 (嘗試 {attempt + 1}/{max_retries}): {str(e)}", 'API')
                
                if attempt < max_retries - 1:
                    # 對於連接重置錯誤，使用更長的等待時間
                    if is_connection_reset:
                        wait_time = (2 ** attempt) * 2  # 連接重置時等待時間翻倍
                    else:
                        wait_time = 2 ** attempt  # 指數退避策略：每次重試等待時間加倍
                    
                    if self.logger_callback:
                        # 使用安全的日誌記錄方式，避免 GUI 線程問題
                        try:
                            if is_connection_reset:
                                self.logger_callback('log_info', f"   ⏰ 連接重置錯誤，等待 {wait_time} 秒後重試...", 'API')
                            else:
                                self.logger_callback('log_info', f"   ⏰ {wait_time} 秒後重試...", 'API')
                        except Exception:
                            print(f"   ⏰ {wait_time} 秒後重試...")
                    await asyncio.sleep(wait_time)
                    
        # 所有重試都失敗了
        if last_exception:
            error_msg = f"API 請求在 {max_retries} 次重試後仍然失敗: {str(last_exception)}"
            if self.logger_callback:
                self.logger_callback('log_error', f"❌ {error_msg}", 'API')
            raise Exception(error_msg)
        else:
            raise Exception("API 請求失敗，未知錯誤")
    
    # === 組織管理功能 ===
    
    async def get_organizations(self) -> List[Dict]:
        """獲取組織列表"""
        if not self.session:
            raise Exception("API Client session not initialized")
            
        url = self._build_api_url("organizations/")
        start_time = pd.Timestamp.now()
        
        self._log_api_request(url, 'GET')
        
        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status == 200:
                data = await response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('results', [])
                else:
                    return []
            else:
                raise Exception(f"獲取組織列表失敗: {response.status} - {response_text}")
    
    async def get_organization_members(self, org_id: str) -> List[Dict]:
        """獲取組織成員"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url(f"organizations/{org_id}/members/")
        start_time = pd.Timestamp.now()

        self._log_api_request(url, 'GET')

        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()

            self._log_api_response(url, response.status, len(response_text), duration)

            if response.status == 200:
                data = await response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('results', [])
                else:
                    return []
            else:
                raise Exception(f"獲取組織成員失敗: {response.status} - {response_text}")
    
    async def get_organization_groups(self, org_id: str) -> List[Dict]:
        """獲取組織群組"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url(f"organizations/{org_id}/groups/")
        start_time = pd.Timestamp.now()

        self._log_api_request(url, 'GET')

        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()

            self._log_api_response(url, response.status, len(response_text), duration)

            if response.status == 200:
                data = await response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('results', [])
                else:
                    return []
            else:
                raise Exception(f"獲取組織群組失敗: {response.status} - {response_text}")
    
    async def get_group_members(self, org_id: str, group_id: str) -> List[Dict]:
        """獲取群組成員"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url(f"organizations/{org_id}/groups/{group_id}/group-members/")
        start_time = pd.Timestamp.now()

        self._log_api_request(url, 'GET')

        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()

            self._log_api_response(url, response.status, len(response_text), duration)

            if response.status == 200:
                data = await response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('results', [])
                else:
                    return []
            else:
                raise Exception(f"獲取群組成員失敗: {response.status} - {response_text}")
    
    async def get_permissions(self) -> List[Dict]:
        """獲取權限列表"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url("permissions/")
        start_time = pd.Timestamp.now()

        self._log_api_request(url, 'GET')

        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()

            self._log_api_response(url, response.status, len(response_text), duration)

            if response.status == 200:
                data = await response.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get('results', [])
                else:
                    return []
            else:
                raise Exception(f"獲取權限列表失敗: {response.status} - {response_text}")
    
    # === 知識庫管理功能 ===
    
    async def get_knowledge_bases(self) -> List[Dict]:
        """獲取知識庫列表（支援分頁）"""
        if not self.session:
            raise Exception("API Client session not initialized")

        all_knowledge_bases = []
        url = self._build_api_url("knowledge-bases/")
        page_number = 1
        
        while url:
            start_time = pd.Timestamp.now()

            # 記錄請求詳情（包含headers）
            request_headers = dict(self.session.headers) if hasattr(self.session, 'headers') else {}
            self._log_api_request(url, 'GET', headers=request_headers)

            async with self.session.get(url) as response:
                duration = (pd.Timestamp.now() - start_time).total_seconds()
                response_text = await response.text()
                
                # 記錄回應詳情（包含headers和內容）
                response_headers = dict(response.headers)
                try:
                    response_data = await response.json() if response_text else None
                except:
                    response_data = response_text

                self._log_api_response(url, response.status, len(response_text), duration, 
                                     response_data=response_data, response_headers=response_headers)

                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list):
                        # 直接返回列表（非分頁格式）
                        return data
                    elif isinstance(data, dict):
                        # 分頁格式
                        current_results = data.get('results', [])
                        all_knowledge_bases.extend(current_results)
                        
                        # 檢查是否有下一頁
                        next_url = data.get('next')
                        if next_url:
                            url = next_url
                            page_number += 1
                            # 記錄分頁進度
                            total_count = data.get('count', 0)
                            current_count = len(all_knowledge_bases)
                            if self.logger_callback:
                                self.logger_callback('log_info', f"📄 已載入第 {page_number-1} 頁，共 {current_count}/{total_count} 個知識庫")
                        else:
                            # 沒有下一頁，結束循環
                            url = None
                    else:
                        return []
                else:
                    raise Exception(f"獲取知識庫列表失敗: {response.status} - {response_text}")
        
        return all_knowledge_bases
    
    async def get_knowledge_base_files(self, kb_id: str, progress_callback=None, load_all_at_once=True) -> List[Dict]:
        """獲取知識庫文件列表（支援一次性載入或分頁載入）"""
        if not self.session:
            raise Exception("API Client session not initialized")

        if load_all_at_once:
            # 嘗試一次性載入所有文件
            return await self._get_all_files_at_once(kb_id, progress_callback)
        else:
            # 使用原有分頁方式
            return await self._get_files_paginated(kb_id, progress_callback)
    
    async def _get_all_files_at_once(self, kb_id: str, progress_callback=None) -> List[Dict]:
        """一次性載入所有知識庫文件"""
        # 先獲取第一頁來得到總數
        url = self._build_api_url(f"knowledge-bases/{kb_id}/files/")
        
        start_time = pd.Timestamp.now()
        self._log_api_request(url, 'GET')
        
        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status != 200:
                raise Exception(f"獲取知識庫文件列表失敗: {response.status} - {response_text}")
            
            data = await response.json()
            
            if isinstance(data, list):
                # 直接返回列表（非分頁格式）
                if progress_callback:
                    progress_callback(len(data), len(data))
                if self.logger_callback:
                    self.logger_callback('log_info', f"📄 一次性載入完成，共 {len(data)} 個文件")
                return data
            elif isinstance(data, dict):
                total_count = data.get('count', 0)
                if total_count == 0:
                    return []
                
                # 嘗試用大的 page_size 一次性獲取所有文件
                large_page_size = max(total_count, 10000)  # 至少10000，確保能獲取所有文件
                url_with_size = self._build_api_url(f"knowledge-bases/{kb_id}/files/?page_size={large_page_size}")
                
                start_time = pd.Timestamp.now()
                self._log_api_request(url_with_size, 'GET')
                
                async with self.session.get(url_with_size) as large_response:
                    duration = (pd.Timestamp.now() - start_time).total_seconds()
                    large_response_text = await large_response.text()
                    self._log_api_response(url_with_size, large_response.status, len(large_response_text), duration)
                    
                    if large_response.status == 200:
                        large_data = await large_response.json()
                        all_files = large_data.get('results', [])
                        
                        if progress_callback:
                            progress_callback(len(all_files), total_count)
                        
                        if self.logger_callback:
                            self.logger_callback('log_info', f"📄 一次性載入完成，共 {len(all_files)}/{total_count} 個文件")
                        
                        return all_files
                    else:
                        # 如果大頁面載入失敗，回退到分頁模式
                        if self.logger_callback:
                            self.logger_callback('log_warning', f"一次性載入失敗，回退到分頁模式: {large_response.status}")
                        return await self._get_files_paginated(kb_id, progress_callback)
            else:
                return []

    async def _get_files_paginated(self, kb_id: str, progress_callback=None) -> List[Dict]:
        """原有的分頁載入方式（備用）"""
        all_files = []
        url = self._build_api_url(f"knowledge-bases/{kb_id}/files/")
        page_number = 1
        total_count = 0
        
        while url:
            start_time = pd.Timestamp.now()
            self._log_api_request(url, 'GET')

            async with self.session.get(url) as response:
                duration = (pd.Timestamp.now() - start_time).total_seconds()
                response_text = await response.text()
                self._log_api_response(url, response.status, len(response_text), duration)

                if response.status == 200:
                    data = await response.json()
                    
                    if isinstance(data, list):
                        if progress_callback:
                            progress_callback(len(data), len(data))
                        return data
                    elif isinstance(data, dict):
                        current_results = data.get('results', [])
                        all_files.extend(current_results)
                        
                        next_url = data.get('next')
                        total_count = data.get('count', 0)
                        current_count = len(all_files)
                        
                        if progress_callback:
                            progress_callback(current_count, total_count)
                        
                        if next_url:
                            url = next_url
                            page_number += 1
                            if self.logger_callback:
                                self.logger_callback('log_info', f"📄 已載入第 {page_number-1} 頁，共 {current_count}/{total_count} 個文件")
                        else:
                            url = None
                    else:
                        if progress_callback:
                            progress_callback(0, 0)
                        return []
                else:
                    raise Exception(f"獲取知識庫文件列表失敗: {response.status} - {response_text}")
        
        return all_files
    
    async def download_knowledge_base_file(self, kb_id: str, file_id: str, max_retries: int = 3) -> bytes:
        """下載知識庫文件（支援重試機制）"""
        if not self.session:
            raise Exception("API Client session not initialized")

        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # 等待一段時間再重試
                    await asyncio.sleep(2 ** attempt)  # 指數退避：2, 4, 8 秒
                    # 使用安全的日誌記錄方式，避免 GUI 線程問題
                    try:
                        self.logger_callback('log_info', f"重試下載文件 {file_id}，第 {attempt + 1} 次嘗試")
                    except Exception:
                        print(f"重試下載文件 {file_id}，第 {attempt + 1} 次嘗試")
                
                # 先獲取文件的詳細信息，包含文件的 URL
                file_detail_url = self._build_api_url(f"knowledge-bases/{kb_id}/files/{file_id}/")
                start_time = pd.Timestamp.now()
                
                self._log_api_request(file_detail_url, 'GET')
                
                async with self.session.get(file_detail_url) as response:
                    duration = (pd.Timestamp.now() - start_time).total_seconds()
                    self._log_api_response(file_detail_url, response.status, 0, duration)
                    
                    if response.status == 200:
                        file_data = await response.json()
                        
                        # 從文件詳細信息中獲取文件 URL
                        file_url = None
                        if 'file' in file_data and file_data['file']:
                            file_url = file_data['file']
                        
                        if not file_url:
                            raise Exception(f"文件 {file_id} 沒有可用的下載 URL")
                        
                        # 檢查文件狀態
                        file_status = file_data.get('status', '')
                        if file_status in ['deleting', 'failed']:
                            raise Exception(f"文件 {file_id} 狀態為 {file_status}，無法下載")
                        
                        # 直接下載文件 URL
                        self._log_api_request(file_url, 'GET')
                        download_start_time = pd.Timestamp.now()
                        
                        async with self.session.get(file_url) as download_response:
                            download_duration = (pd.Timestamp.now() - download_start_time).total_seconds()
                            
                            if download_response.status == 200:
                                file_content = await download_response.read()
                                self._log_api_response(file_url, download_response.status, len(file_content), download_duration)
                                if attempt > 0:
                                    # 使用安全的日誌記錄方式，避免 GUI 線程問題
                                    try:
                                        self.logger_callback('log_info', f"文件 {file_id} 重試成功")
                                    except Exception:
                                        print(f"文件 {file_id} 重試成功")
                                return file_content
                            else:
                                response_text = await download_response.text()
                                self._log_api_response(file_url, download_response.status, len(response_text), download_duration)
                                
                                # 如果是 502/503/504 等服務器錯誤，可以重試
                                if download_response.status in [502, 503, 504] and attempt < max_retries - 1:
                                    last_error = Exception(f"下載文件失敗: HTTP {download_response.status} - {response_text}")
                                    continue
                                else:
                                    raise Exception(f"下載文件失敗: HTTP {download_response.status} - {response_text}")
                    
                    elif response.status == 404:
                        raise Exception(f"文件 {file_id} 不存在")
                    elif response.status in [502, 503, 504] and attempt < max_retries - 1:
                        # 服務器錯誤，可以重試
                        response_text = await response.text()
                        last_error = Exception(f"獲取文件信息失敗: HTTP {response.status} - {response_text}")
                        continue
                    else:
                        response_text = await response.text()
                        raise Exception(f"獲取文件信息失敗: HTTP {response.status} - {response_text}")
                        
            except asyncio.TimeoutError:
                last_error = Exception(f"下載文件 {file_id} 超時")
                if attempt < max_retries - 1:
                    # 使用安全的日誌記錄方式，避免 GUI 線程問題
                    try:
                        self.logger_callback('log_warning', f"文件 {file_id} 下載超時，將重試")
                    except Exception:
                        print(f"文件 {file_id} 下載超時，將重試")
                    continue
                else:
                    break
            except Exception as e:
                last_error = e
                # 對於某些錯誤，不需要重試
                if "不存在" in str(e) or "無法下載" in str(e):
                    break
                elif attempt < max_retries - 1:
                    # 使用安全的日誌記錄方式，避免 GUI 線程問題
                    try:
                        self.logger_callback('log_warning', f"下載文件 {file_id} 失敗: {str(e)}")
                    except Exception:
                        print(f"下載文件 {file_id} 失敗: {str(e)}")
                    continue
                else:
                    break
        
        # 所有重試都失敗了
        error_msg = str(last_error) if last_error else f"無法下載文件 {file_id}"
        # 使用安全的日誌記錄方式，避免 GUI 線程問題
        try:
            self.logger_callback('log_error', f"下載文件 {file_id} 最終失敗: {error_msg}")
        except Exception:
            print(f"下載文件 {file_id} 最終失敗: {error_msg}")
        raise Exception(f"無法下載文件 {file_id}: {error_msg}")
    
    async def get_knowledge_base_file_content(self, kb_id: str, file_id: str) -> Dict:
        """取得知識庫檔案內容"""
        url = self._build_api_url(f"knowledge-bases/{kb_id}/files/{file_id}/")
        
        headers = {"Authorization": f"Api-Key {self.api_key}"}
        self._log_api_request(url, "GET")
        
        start_time = time.time()
        
        async with self.session.get(url, headers=headers) as response:
            if response.status == 200:
                result = await response.json()
                self._log_api_response(url, response.status, len(str(result)), time.time() - start_time)
                return result
            else:
                self._log_api_response(url, response.status, 0, time.time() - start_time)
                response.raise_for_status()

    async def get_upload_presigned_url(self, model_name: str, field_name: str, filename: str, file_size: int) -> Dict:
        """取得檔案上傳的預簽名URL"""
        url = self._build_api_url("upload-presigned-url/")
        
        print(f"🔍 調試信息 - 原始base_url: {self.base_url}")
        print(f"🔍 調試信息 - 預簽名URL: {url}")
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model_name": model_name,
            "field_name": field_name,
            "filename": filename,
            "file_size": file_size
        }
        
        # 記錄詳細請求信息（包含headers）
        self._log_api_request(url, "POST", payload=payload, headers=headers)
        
        start_time = time.time()
        
        async with self.session.post(url, headers=headers, json=payload) as response:
            response_text = await response.text()
            response_headers = dict(response.headers)
            
            try:
                response_data = await response.json() if response_text else None
            except:
                response_data = response_text
            
            # 記錄詳細回應信息
            self._log_api_response(url, response.status, len(response_text), time.time() - start_time,
                                 response_data=response_data, response_headers=response_headers)
            
            if response.status == 200:
                result = await response.json()
                return result
            else:
                print(f"❌ 預簽名URL請求失敗: {response.status}")
                print(f"❌ 響應內容: {response_text}")
                response.raise_for_status()

    async def upload_file_to_s3(self, presigned_data: Dict, file_path: str) -> bool:
        """使用預簽名URL上傳檔案到S3 - 修正文件處理方式"""
        url = presigned_data["url"]
        fields = presigned_data["fields"]
        
        print(f"🔍 S3上傳調試 - URL: {url}")
        print(f"🔍 S3上傳調試 - 字段數量: {len(fields)}")
        print(f"🔍 S3上傳調試 - 文件路徑: {file_path}")
        print(f"🔍 S3上傳調試 - 文件大小: {os.path.getsize(file_path)} bytes")
        
        # 獲取文件相關信息
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(file_path)[0] or 'application/octet-stream'
        
        print(f"🔍 文件信息: filename={filename}, content_type={content_type}")
        
        # 先讀取文件內容到內存，避免文件描述符問題
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        print(f"🔍 文件內容讀取完成: {len(file_content)} bytes")
        
        # 使用aiohttp.FormData - 關鍵：不在with語句中處理請求
        data = aiohttp.FormData()
        
        # 添加所有預簽名字段
        for key, value in fields.items():
            data.add_field(key, str(value))
            print(f"🔍 添加字段: {key} = {value}")
        
        # 添加文件內容（不是文件對象）
        data.add_field('file', file_content, 
                      filename=filename, 
                      content_type=content_type)
        
        print(f"🔍 添加文件內容: filename={filename}, content_type={content_type}, size={len(file_content)}")
        
        start_time = time.time()
        # 記錄S3上傳請求詳情
        s3_request_payload = {"fields": fields, "file": filename, "size": len(file_content)}
        self._log_api_request(url, "POST", payload=s3_request_payload, headers={"Content-Type": "multipart/form-data"})
        
        # 為S3上傳創建獨立的session，避免默認headers污染
        try:
            # 創建臨時session，不包含任何默認headers
            timeout = aiohttp.ClientTimeout(total=60)  # 60秒超時
            async with aiohttp.ClientSession(timeout=timeout) as s3_session:
                # 明確不設置任何headers，讓aiohttp自動處理multipart/form-data
                print(f"🔍 使用獨立S3 session進行上傳")
                async with s3_session.post(url, data=data) as response:
                    response_text = await response.text()
                    response_headers = dict(response.headers)
                    request_headers = dict(response.request_info.headers) if hasattr(response, 'request_info') else {}
                    success = response.status in [200, 201, 204]
                    
                    # 記錄詳細S3上傳回應
                    self._log_api_response(url, response.status, len(response_text), time.time() - start_time,
                                         response_data=response_text, response_headers=response_headers)
                    
                    if not success:
                        print(f"❌ S3上傳失敗: 狀態碼 {response.status}")
                        print(f"❌ S3響應: {response_text}")
                        print(f"🔍 請求headers: {request_headers}")
                    else:
                        print(f"✅ S3上傳成功: 狀態碼 {response.status}")
                    
                    return success
                 
        except Exception as e:
            print(f"❌ S3上傳異常: {e}")
            self._log_api_response(url, 0, 0, time.time() - start_time)
            return False

    async def create_knowledge_base_file(self, kb_id: str, filename: str, file_path_in_storage: str, parser_id: str = None) -> Dict:
        """在知識庫中創建檔案記錄"""
        url = self._build_api_url(f"knowledge-bases/{kb_id}/files/")
        
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "files": [
                {
                    "filename": filename,
                    "file": file_path_in_storage,
                    "parser": parser_id
                }
            ]
        }
        
        # 記錄詳細請求信息
        self._log_api_request(url, "POST", payload=payload, headers=headers)
        
        start_time = time.time()
        
        async with self.session.post(url, headers=headers, json=payload) as response:
            response_text = await response.text()
            response_headers = dict(response.headers)
            
            try:
                response_data = await response.json() if response_text else None
            except:
                response_data = response_text
            
            # 記錄詳細回應信息
            self._log_api_response(url, response.status, len(response_text), time.time() - start_time,
                                 response_data=response_data, response_headers=response_headers)
            
            if response.status == 201:
                result = await response.json()
                return result
            else:
                response.raise_for_status()

    async def upload_file_to_knowledge_base(self, kb_id: str, file_path: str, parser_id: str = None) -> Dict:
        """完整的檔案上傳到知識庫流程"""
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # 1. 取得預簽名URL
        presigned_data = await self.get_upload_presigned_url(
            model_name="chatbot-file",
            field_name="file",
            filename=filename,
            file_size=file_size
        )
        
        # 2. 上傳檔案到S3
        upload_success = await self.upload_file_to_s3(presigned_data, file_path)
        
        if not upload_success:
            raise Exception("檔案上傳到S3失敗")
        
        # 3. 從預簽名URL的fields中取得檔案路徑
        file_key = presigned_data["fields"]["key"]
        # 將完整路徑轉為相對路徑（移除 media/ 前綴）
        relative_path = file_key.replace('media/', '', 1) if file_key.startswith('media/') else file_key
        
        # 4. 在知識庫中創建檔案記錄
        result = await self.create_knowledge_base_file(kb_id, filename, relative_path, parser_id)
        
        return result
    
    # === 創建功能 ===
    
    async def create_user(self, email: str, name: str, password: str = "TempPassword123!", 
                         company: str = "Default Company", referral_code: str = None) -> Optional[Dict]:
        """創建用戶帳號"""
        if not self.session:
            raise Exception("API Client session not initialized")
        
        if not referral_code:
            print("⚠️  未提供推薦碼，將略過用戶創建（假設用戶已存在）")
            return None
        
        user_data = {
            'email': email,
            'password1': password,
            'password2': password,
            'name': name,
            'company': company,
            'referralCode': referral_code
        }
        
        url = self._build_api_url("auth/registration/")
        start_time = pd.Timestamp.now()
        
        self._log_api_request(url, 'POST', user_data)
        
        try:
            async with self.session.post(url, json=user_data) as response:
                duration = (pd.Timestamp.now() - start_time).total_seconds()
                response_text = await response.text()
                
                self._log_api_response(url, response.status, len(response_text), duration)
                
                if response.status in [200, 201]:
                    print(f"✅ 用戶創建成功: {name}")
                    return await response.json()
                else:
                    print(f"⚠️  用戶 {email} 創建失敗（可能已存在）: {response.status}")
                    return None
        except Exception as e:
            print(f"⚠️  用戶 {email} 創建失敗: {e}")
            return None
    
    async def create_organization(self, name: str) -> Dict:
        """創建組織"""
        if not self.session:
            raise Exception("API Client session not initialized")
        
        org_data = {'name': name}
        
        url = self._build_api_url("organizations/")
        start_time = pd.Timestamp.now()
        
        self._log_api_request(url, 'POST', org_data)
        
        async with self.session.post(url, json=org_data) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status in [200, 201]:
                return await response.json()
            else:
                raise Exception(f"創建組織失敗: {response.status} - {response_text}")
    
    async def create_group(self, organization_id: str, name: str, permission_names: List[str]) -> Dict:
        """創建群組"""
        if not self.session:
            raise Exception("API Client session not initialized")
        
        # 先獲取所有權限
        permissions = await self.get_permissions()
        permission_map = {p['name']: p['id'] for p in permissions if isinstance(p, dict)}
        
        # 轉換權限名稱為 ID
        permission_ids = []
        for perm_name in permission_names:
            if perm_name in permission_map:
                permission_ids.append(permission_map[perm_name])
        
        group_data = {
            'name': name,
            'permissions': permission_ids
        }
        
        url = self._build_api_url(f"organizations/{organization_id}/groups/")
        start_time = pd.Timestamp.now()
        
        self._log_api_request(url, 'POST', group_data)
        
        async with self.session.post(url, json=group_data) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status in [200, 201]:
                return await response.json()
            else:
                raise Exception(f"創建群組失敗: {response.status} - {response_text}")
    
    async def add_member_to_organization(self, organization_id: str, email: str) -> Dict:
        """添加成員到組織"""
        if not self.session:
            raise Exception("API Client session not initialized")
        
        member_data = {'email': email}
        
        url = self._build_api_url(f"organizations/{organization_id}/members/")
        start_time = pd.Timestamp.now()
        
        self._log_api_request(url, 'POST', member_data)
        
        async with self.session.post(url, json=member_data) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status in [200, 201]:
                return await response.json()
            else:
                raise Exception(f"添加成員到組織失敗: {response.status} - {response_text}")
    
    async def add_members_to_group(self, organization_id: str, group_id: str, member_ids: List[str]) -> List[Dict]:
        """批量添加成員到群組"""
        if not self.session:
            raise Exception("API Client session not initialized")
        
        results = []
        for member_id in member_ids:
            member_data = {'member': member_id}
            
            url = self._build_api_url(f"organizations/{organization_id}/groups/{group_id}/group-members/")
            start_time = pd.Timestamp.now()
            
            self._log_api_request(url, 'POST', member_data)
            
            try:
                async with self.session.post(url, json=member_data) as response:
                    duration = (pd.Timestamp.now() - start_time).total_seconds()
                    response_text = await response.text()
                    
                    self._log_api_response(url, response.status, len(response_text), duration)
                    
                    if response.status in [200, 201]:
                        result = await response.json()
                        results.append(result)
                    else:
                        print(f"⚠️  添加成員 {member_id} 到群組失敗: {response.status}")
            except Exception as e:
                print(f"⚠️  添加成員 {member_id} 到群組時發生錯誤: {e}")
        
        return results


class ConversationManager:
    """對話管理器，處理相同提問者的對話會話"""
    
    def __init__(self):
        self.conversations: Dict[str, str] = {}
        self.questioner_context: Dict[str, List[str]] = {}  # 儲存每個提問者的問題上下文
    
    def get_conversation_id(self, questioner: str) -> Optional[str]:
        return self.conversations.get(questioner)
    
    def set_conversation_id(self, questioner: str, conversation_id: str):
        self.conversations[questioner] = conversation_id
    
    def add_question_to_context(self, questioner: str, question: str):
        """添加問題到提問者的上下文中"""
        if questioner not in self.questioner_context:
            self.questioner_context[questioner] = []
        self.questioner_context[questioner].append(question)
    
    def get_context_questions(self, questioner: str) -> List[str]:
        """獲取提問者的上下文問題列表"""
        return self.questioner_context.get(questioner, [])
    
    def build_context_message(self, questioner: str, current_question: str) -> str:
        """構建包含上下文的完整問題"""
        previous_questions = self.get_context_questions(questioner)
        
        if not previous_questions:
            # 如果沒有前面的問題，直接返回當前問題
            return current_question
        
        # 構建上下文訊息
        context_parts = []
        context_parts.append("這是一系列相關的問題：")
        context_parts.append("")
        
        # 添加前面的問題
        for i, prev_question in enumerate(previous_questions, 1):
            context_parts.append(f"問題 {i}：{prev_question}")
        
        # 添加當前問題
        context_parts.append(f"問題 {len(previous_questions) + 1}：{current_question}")
        context_parts.append("")
        context_parts.append("請針對這一系列問題提供完整的回答，特別是最後一個問題。")
        
        return "\n".join(context_parts)


class CSVParser:
    """CSV 文件解析器 - 整合自 deploy_from_csv.py"""
    
    def __init__(self, csv_file: str):
        self.csv_file = csv_file
        self.members = []
        self.groups_info = {}
        
    def parse(self) -> Tuple[List[Dict], Dict[str, List[str]]]:
        """解析 CSV 文件，返回成員列表和群組信息"""
        print(f"📄 正在解析 CSV 文件: {self.csv_file}")
        
        # 使用編碼檢測讀取CSV文件
        encoding = self._detect_file_encoding(self.csv_file)
        with open(self.csv_file, 'r', encoding=encoding) as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                member = {
                    'id': row.get('成員 ID', ''),
                    'name': row.get('姓名', ''),
                    'email': row.get('電子郵件', ''),
                    'is_owner': row.get('是否為擁有者', '否') == '是',
                    'groups': row.get('所屬群組', ''),
                    'group_permissions': row.get('群組權限配置', '')
                }
                
                self.members.append(member)
                
                # 解析群組權限配置
                self._parse_group_permissions(member['group_permissions'])
        
        print(f"✅ CSV 解析完成，找到 {len(self.members)} 個成員")
        print(f"📋 找到群組: {', '.join(self.groups_info.keys())}")
        
        return self.members, self.groups_info
    
    def _parse_group_permissions(self, group_permissions_str: str):
        """解析群組權限配置字符串"""
        if not group_permissions_str or group_permissions_str == '無':
            return
        
        # 先按分號分割不同的群組配置
        group_configs = [config.strip() for config in group_permissions_str.split(';') if config.strip()]
        
        for group_config in group_configs:
            # 解析每個群組配置：群組名稱(權限1, 權限2, ...)
            pattern = r'^(.+?)\(([^)]*)\)$'
            match = re.match(pattern, group_config.strip())
            
            if match:
                group_name = match.group(1).strip()
                permissions_str = match.group(2).strip()
                
                if permissions_str == '無權限':
                    permissions = []
                else:
                    permissions = [p.strip() for p in permissions_str.split(',') if p.strip()]
                
                if group_name not in self.groups_info:
                    self.groups_info[group_name] = permissions
            else:
                print(f"⚠️ 無法解析群組配置: {group_config}")
    
    def _detect_file_encoding(self, file_path):
        """檢測文件編碼"""
        import chardet
        
        # 常見編碼格式
        encodings_to_try = ['utf-8-sig', 'utf-8', 'big5', 'gbk', 'cp950', 'cp1252']
        
        try:
            with open(file_path, 'rb') as file:
                raw_data = file.read()
                detected = chardet.detect(raw_data)
                detected_encoding = detected.get('encoding', '')
                confidence = detected.get('confidence', 0)
                
                print(f"🔍 檢測到文件編碼: {detected_encoding} (信心度: {confidence:.2f})")
                
                if confidence > 0.7 and detected_encoding:
                    return detected_encoding.lower()
        except Exception as e:
            print(f"編碼檢測失敗: {e}")
        
        # 逐一嘗試編碼
        for encoding in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=encoding) as test_file:
                    test_file.read(1024)  # 讀取前1024字節測試
                print(f"✅ 使用編碼: {encoding}")
                return encoding
            except UnicodeDecodeError:
                continue
        
        # 默認返回utf-8-sig
        print("⚠️ 無法確定編碼，使用默認: utf-8-sig")
        return 'utf-8-sig'


class BatchImportProcessor:
    """批量匯入處理器 - 整合自 deploy_from_csv.py"""
    
    def __init__(self, api_client: MaiAgentApiClient, csv_file: str, referral_code: str = None):
        self.api_client = api_client
        self.parser = CSVParser(csv_file)
        self.referral_code = referral_code
        self.users_cache = {}
        
    async def execute_import(self, organization_name: str = None, create_users: bool = False, 
                           log_callback=None) -> bool:
        """執行批量匯入"""
        try:
            if log_callback:
                log_callback("🚀 開始 MaiAgent 帳號批量匯入")
                log_callback("=" * 60)
            
            # 1. 解析 CSV
            members, groups_info = self.parser.parse()
            
            if not organization_name:
                organization_name = f"導入組織_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 2. 創建組織
            if log_callback:
                log_callback(f"\n🏢 創建組織: {organization_name}")
            
            organization = await self.api_client.create_organization(organization_name)
            organization_id = organization['id']
            
            if log_callback:
                log_callback(f"✅ 組織創建成功，ID: {organization_id}")
            
            # 3. 創建用戶（可選）
            if create_users and self.referral_code:
                if log_callback:
                    log_callback(f"\n👤 開始創建用戶帳號...")
                
                for member in members:
                    if member['email']:
                        await self.api_client.create_user(
                            member['email'], 
                            member['name'], 
                            referral_code=self.referral_code
                        )
            
            # 4. 創建群組
            if log_callback:
                log_callback(f"\n🏷️ 創建群組...")
            
            group_id_map = {}
            for group_name, permissions in groups_info.items():
                try:
                    group = await self.api_client.create_group(organization_id, group_name, permissions)
                    group_id_map[group_name] = group['id']
                    if log_callback:
                        log_callback(f"✅ 群組 '{group_name}' 創建成功")
                except Exception as e:
                    if log_callback:
                        log_callback(f"⚠️ 群組 '{group_name}' 創建失敗: {e}")
            
            # 5. 添加成員到組織
            if log_callback:
                log_callback(f"\n👥 添加成員到組織...")
            
            member_email_to_id = {}
            for member in members:
                if member['email']:
                    try:
                        org_member = await self.api_client.add_member_to_organization(organization_id, member['email'])
                        if isinstance(org_member, dict) and 'id' in org_member:
                            member_email_to_id[member['email']] = org_member['id']
                        elif isinstance(org_member, dict) and 'member' in org_member:
                            member_email_to_id[member['email']] = org_member['member']['id']
                        if log_callback:
                            log_callback(f"✅ 成員 {member['name']} 已添加到組織")
                    except Exception as e:
                        if log_callback:
                            log_callback(f"⚠️ 添加成員 {member['name']} 失敗: {e}")
            
            # 6. 添加成員到群組
            if log_callback:
                log_callback(f"\n🔗 建立群組成員關係...")
            
            for member in members:
                if member['email'] in member_email_to_id and member['groups']:
                    member_id = member_email_to_id[member['email']]
                    member_groups = [g.strip() for g in member['groups'].split(';') if g.strip()]
                    
                    for group_name in member_groups:
                        if group_name in group_id_map:
                            try:
                                await self.api_client.add_members_to_group(
                                    organization_id, 
                                    group_id_map[group_name], 
                                    [member_id]
                                )
                                if log_callback:
                                    log_callback(f"✅ 成員 {member['name']} 已加入群組 {group_name}")
                            except Exception as e:
                                if log_callback:
                                    log_callback(f"⚠️ 添加成員 {member['name']} 到群組 {group_name} 失敗: {e}")
            
            if log_callback:
                log_callback(f"\n✅ MaiAgent 帳號批量匯入完成！")
                log_callback(f"📊 匯入統計:")
                log_callback(f"   創建組織: {organization_name}")
                log_callback(f"   創建群組數量: {len(group_id_map)}")
                log_callback(f"   成功添加成員數量: {len(member_email_to_id)}")
            
            return True
            
        except Exception as e:
            if log_callback:
                log_callback(f"❌ 批量匯入失敗: {str(e)}")
            return False


class EnhancedTextMatcher:
    """增強版文字比對工具，支援 RAG 系統優化"""
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str, mode: str = "standard", expected_segments: List[str] = None) -> float:
        """計算兩個文字的相似度（0-1之間）
        
        Args:
            text1: 第一個文字（通常是AI回覆段落）
            text2: 第二個文字（通常是預期段落）
            mode: 計算模式，"standard" 或 "character_ratio"
            expected_segments: 所有預期段落列表（僅在character_ratio模式下使用）
        """
        if not text1 or not text2:
            return 0.0
            
        if mode == "character_ratio":
            # 新的字符比例模式：匹配字符數 / 應參考的文件節點總長度
            return EnhancedTextMatcher._calculate_character_ratio_similarity(text1, text2, expected_segments)
        else:
            # 標準模式：使用SequenceMatcher
            return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()
    
    @staticmethod
    def _calculate_character_ratio_similarity(ai_chunk: str, expected_segment: str, expected_segments: List[str] = None) -> float:
        """計算字符比例相似度：匹配字符數 / 應參考的文件節點總長度
        
        Args:
            ai_chunk: AI回覆的文字段落
            expected_segment: 預期的文字段落
            expected_segments: 所有預期段落列表
        """
        if not ai_chunk or not expected_segment:
            return 0.0
            
        # 預處理文字
        ai_text = ai_chunk.lower().strip()
        expected_text = expected_segment.lower().strip()
        
        # 計算匹配的字符數
        matcher = SequenceMatcher(None, ai_text, expected_text)
        matching_blocks = matcher.get_matching_blocks()
        matched_chars = sum(block.size for block in matching_blocks)
        
        # 計算應參考的文件節點總長度
        if expected_segments:
            total_expected_length = sum(len(seg.strip()) for seg in expected_segments)
        else:
            total_expected_length = len(expected_text)
        
        # 避免除零錯誤
        if total_expected_length == 0:
            return 0.0
            
        # 計算比例
        ratio = matched_chars / total_expected_length
        
        # 確保結果在0-1之間
        return min(1.0, max(0.0, ratio))
    
    @staticmethod
    def contains_keywords(text: str, keywords: str) -> bool:
        """檢查文字是否包含關鍵詞（支持多個關鍵詞，用逗號分隔）"""
        if not keywords:
            return False
        text_lower = text.lower()
        keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
        return any(keyword.lower() in text_lower for keyword in keyword_list)
    
    @staticmethod
    def parse_expected_segments(expected_content: str, custom_separators: List[str] = None) -> List[str]:
        """解析預期文件段落（支援多個段落和自定義分隔符）"""
        if not expected_content:
            return []
        
        # 支援多種分隔方式（預設）
        default_separators = ['---', '|||', '\n\n']
        separators = custom_separators if custom_separators else default_separators
        
        segments = [expected_content]
        for sep in separators:
            new_segments = []
            for segment in segments:
                parts = segment.split(sep)
                new_segments.extend([s.strip() for s in parts if s.strip()])
            segments = new_segments
        
        return segments if len(segments) > 1 else [expected_content.strip()]
    
    @classmethod
    def check_citation_hit(cls, citation_nodes: List[Dict], expected_content: str, similarity_threshold: float = 0.3) -> Tuple[bool, str]:
        """檢查引用節點命中（向後兼容方法）"""
        if not citation_nodes or not expected_content:
            return False, "無引用節點或預期內容為空"
        
        best_match_score = 0.0
        best_match_content = ""
        
        for node in citation_nodes:
            if 'chatbotTextNode' in node and 'text' in node['chatbotTextNode']:
                node_content = node['chatbotTextNode']['text']
            elif 'chatbotTextNode' in node and 'content' in node['chatbotTextNode']:
                node_content = node['chatbotTextNode']['content']
            else:
                continue
                
            similarity = cls.calculate_similarity(node_content, expected_content)  # 使用預設standard模式

                
            

                
            if similarity > best_match_score:
                best_match_score = similarity
                best_match_content = node_content
        
        is_hit = best_match_score >= similarity_threshold
        result_detail = f"最佳匹配分數: {best_match_score:.2f}"
        
        return is_hit, result_detail
    
    @classmethod
    def check_rag_enhanced_hit(cls, citation_nodes: List[Dict], expected_content: str, 
                             similarity_threshold: float = 0.3, top_k: Optional[int] = None,
                             custom_separators: List[str] = None, similarity_mode: str = "standard") -> Tuple[bool, Dict]:
        """RAG 增強的命中檢查，支援多段落和詳細指標"""
        if not citation_nodes or not expected_content:
            return False, {
                "error": "無引用節點或預期內容為空",
                "hit_rate": 0.0,
                "hit_count": 0,
                "total_expected": 0,
                "total_chunks": 0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0
            }
        
        # 解析預期段落
        expected_segments = cls.parse_expected_segments(expected_content, custom_separators)
        if not expected_segments:
            # 如果解析失敗，使用原始邏輯
            is_hit, detail = cls.check_citation_hit(citation_nodes, expected_content, similarity_threshold)
            return is_hit, {
                "hit_rate": 1.0 if is_hit else 0.0,
                "hit_count": 1 if is_hit else 0,
                "total_expected": 1,
                "total_chunks": len(citation_nodes),
                "precision": 1.0 if is_hit else 0.0,
                "recall": 1.0 if is_hit else 0.0,
                "f1_score": 1.0 if is_hit else 0.0,
                "detail": detail
            }
        
        # 提取 RAG chunks（動態使用所有可用節點或指定數量）
        effective_top_k = top_k if top_k is not None else len(citation_nodes)
        rag_chunks = []
        for i, node in enumerate(citation_nodes[:effective_top_k]):
            if 'chatbotTextNode' in node and 'text' in node['chatbotTextNode']:
                chunk_content = node['chatbotTextNode']['text']
            elif 'chatbotTextNode' in node and 'content' in node['chatbotTextNode']:
                chunk_content = node['chatbotTextNode']['content']
            else:
                continue
            
            rag_chunks.append({
                'index': i,
                'content': chunk_content,
                'matched': False
            })
        
        if not rag_chunks:
            return False, {
                "error": "無有效的 RAG chunks",
                "hit_rate": 0.0,
                "hit_count": 0,
                "total_expected": len(expected_segments),
                "total_chunks": 0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0
            }
        
        # 計算匹配
        hit_count = 0
        matches = []
        
        for exp_idx, expected_seg in enumerate(expected_segments):
            segment_hit = False
            best_match = {"chunk_idx": -1, "similarity": 0.0}
            
            for chunk in rag_chunks:
                similarity = cls.calculate_similarity(chunk['content'], expected_seg, similarity_mode, expected_segments)
                
                if similarity >= similarity_threshold:
                    if not segment_hit:  # 第一次找到匹配
                        hit_count += 1
                        segment_hit = True
                        chunk['matched'] = True
                    
                    if similarity > best_match['similarity']:
                        best_match = {
                            'chunk_idx': chunk['index'],
                            'similarity': similarity
                        }
            
            if segment_hit:
                matches.append({
                    'expected_idx': exp_idx,
                    'expected_segment': expected_seg[:50] + "..." if len(expected_seg) > 50 else expected_seg,
                    'best_match': best_match
                })
        
        # 計算詳細指標
        relevant_chunks = sum(1 for chunk in rag_chunks if chunk['matched'])
        precision = relevant_chunks / len(rag_chunks) if rag_chunks else 0.0
        recall = hit_count / len(expected_segments) if expected_segments else 0.0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
        hit_rate = hit_count / len(expected_segments) if expected_segments else 0.0
        
        is_hit = hit_rate > 0
        
        result = {
            "hit_rate": hit_rate,
            "hit_count": hit_count,
            "total_expected": len(expected_segments),
            "total_chunks": len(rag_chunks),
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "relevant_chunks": relevant_chunks,
            "threshold_used": similarity_threshold,
            "top_k_used": top_k,
            "matches": matches
        }
        
        return is_hit, result
    
    @classmethod
    def check_citation_file_match(cls, citations: List[Dict], expected_files: str) -> Tuple[bool, Dict]:
        """檢查參考文件是否正確（僅支援UUID匹配，逗號和換行符分割，全部命中制）"""
        if not citations or not expected_files:
            return False, {
                "detail": "無引用文件或預期文件為空",
                "total_expected": 0,
                "total_matched": 0,
                "hit_rate": 0.0,
                "matched_files": [],
                "unmatched_files": [],
                "all_matched": False
            }
        
        # 先用換行符分割，再用逗號分割，去除重複
        expected_file_list = []
        
        # 先按換行符分割
        lines = expected_files.split('\n')
        for line in lines:
            line = line.strip()
            if line:
                # 每行內部可能還有逗號分割的文件
                files_in_line = [f.strip() for f in line.split(',') if f.strip()]
                expected_file_list.extend(files_in_line)
        
        # 去除重複的文件名稱/UUID
        expected_file_list = list(set(expected_file_list))
        
        # 收集引用文件的UUID
        cited_uuids = []
        
        for citation in citations:
            if 'id' in citation:
                cited_uuids.append(citation['id'])
        
        # 記錄每個期望文件的匹配情況
        matched_expected_files = set()
        matches = []
        
        for expected_file in expected_file_list:
            # 只進行UUID精確匹配
            if expected_file in cited_uuids:
                matches.append(f"{expected_file} -> UUID匹配")
                matched_expected_files.add(expected_file)
        
        # 計算統計數據
        total_expected = len(expected_file_list)
        total_matched = len(matched_expected_files)
        hit_rate = total_matched / total_expected if total_expected > 0 else 0.0
        
        # 找出未匹配的文件
        unmatched_files = [f for f in expected_file_list if f not in matched_expected_files]
        
        # 新的判斷邏輯：所有期望文件都必須被匹配
        all_matched = total_matched == total_expected
        is_correct = all_matched
        
        result_detail = {
            "detail": f"匹配文件: {total_matched}/{total_expected} 個 (命中率: {hit_rate:.1%})",
            "total_expected": total_expected,
            "total_matched": total_matched,
            "hit_rate": hit_rate,
            "matched_files": list(matched_expected_files),
            "unmatched_files": unmatched_files,
            "all_matched": all_matched,
            "matches": matches
        }
        
        return is_correct, result_detail


class ScrollableFrame(ttk.Frame):
    """可滾動的框架組件"""
    
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        
        # 創建 Canvas 和 Scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        # 配置滾動區域
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        # 創建canvas窗口
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # 配置canvas的yscrollcommand
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # 布局
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # 綁定canvas寬度調整
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        
        # 綁定滑鼠滾輪事件
        self._bind_mousewheel()
    
    def _on_canvas_configure(self, event):
        """當canvas大小改變時調整scrollable_frame的寬度"""
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas_window, width=canvas_width)
    
    def _bind_mousewheel(self):
        """綁定滑鼠滾輪事件（支援 Windows 和 macOS）"""
        # 防止重複綁定的標記
        self._mousewheel_bound = False
        
        def _on_mousewheel(event):
            # 檢查滾動條是否可見/需要
            if self.canvas.bbox("all"):
                canvas_height = self.canvas.winfo_height()
                content_height = self.canvas.bbox("all")[3]
                if content_height > canvas_height:
                    # Windows 滾輪事件
                    if event.delta:
                        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                    # macOS 滾輪事件
                    elif event.num == 4:
                        self.canvas.yview_scroll(-1, "units")
                    elif event.num == 5:
                        self.canvas.yview_scroll(1, "units")
        
        def _bind_to_mousewheel(event):
            # 避免重複綁定
            if not self._mousewheel_bound:
                self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
                # macOS 滾輪事件
                self.canvas.bind_all("<Button-4>", _on_mousewheel)
                self.canvas.bind_all("<Button-5>", _on_mousewheel)
                self._mousewheel_bound = True
        
        def _unbind_from_mousewheel(event):
            if self._mousewheel_bound:
                self.canvas.unbind_all("<MouseWheel>")
                # macOS 滾輪事件
                self.canvas.unbind_all("<Button-4>")
                self.canvas.unbind_all("<Button-5>")
                self._mousewheel_bound = False
        
        # 滑鼠進入和離開時綁定/解綁滾輪事件
        self.canvas.bind('<Enter>', _bind_to_mousewheel)
        self.canvas.bind('<Leave>', _unbind_from_mousewheel)


class MaiAgentValidatorGUI:
    """MaiAgent 驗證工具 GUI 主類"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{__app_name__} v{__version__} - RAG 增強版")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        
        # 修復 macOS 剪貼板和事件重複問題
        self._setup_macos_fixes()
        
        # 設定樣式
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # 獲取主題背景色用於 tk 組件
        self.bg_color = self.style.lookup('TFrame', 'background') or self.root.cget('bg')
        
        # 變數
        self.csv_file_path = tk.StringVar()
        self.api_base_url = tk.StringVar(value="http://localhost:8000")
        self.api_key = tk.StringVar()
        self.similarity_threshold = tk.DoubleVar(value=0.3)
        self.max_concurrent = tk.IntVar(value=5)
        self.api_delay = tk.DoubleVar(value=1.0)  # API 呼叫間隔延遲時間（秒）
        self.max_retries = tk.IntVar(value=3)  # API 請求重試次數
        # 固定使用 RAG 模式，不再提供開關
        self.top_k = None  # 動態：根據 API 回傳的引用節點數量決定
        self.selected_chatbot_id = None
        self.validation_data = []
        self.conversation_manager = ConversationManager()
        self.text_matcher = EnhancedTextMatcher()
        
        # query_metadata 相關參數
        self.knowledge_base_id = tk.StringVar()
        self.label_id = tk.StringVar()
        self.enable_query_metadata = tk.BooleanVar(value=False)
        
        # 上下文組合相關參數
        self.enable_context_combination = tk.BooleanVar(value=True)
        
        # 驗證控制變數
        self.validation_stopped = False
        self.completed_questions = 0
        
        # 段落分隔符設定
        self.separator_vars = {
            '---': tk.BooleanVar(value=True),      # 三個連字符
            '|||': tk.BooleanVar(value=True),      # 三個豎線
            '\n\n': tk.BooleanVar(value=True),     # 雙換行
            '###': tk.BooleanVar(value=False),     # 三個井號
            '===': tk.BooleanVar(value=False),     # 三個等號
            '...': tk.BooleanVar(value=False),     # 三個點
        }
        
        # 相似度計算模式設定
        self.similarity_mode = tk.StringVar(value="standard")  # standard 或 character_ratio
        
        # 組織管理相關變數
        self.org_export_api_key = tk.StringVar()
        self.org_export_base_url = tk.StringVar(value="https://api.maiagent.ai/api/v1/")
        self.deploy_csv_file = tk.StringVar()
        self.deploy_api_key = tk.StringVar()
        self.deploy_base_url = tk.StringVar(value="http://localhost:8000/api/v1/")
        self.deploy_org_name = tk.StringVar()
        self.deploy_create_users = tk.BooleanVar(value=False)
        self.deploy_referral_code = tk.StringVar()
        self.current_deployment_task = None
        self.export_organizations = []
        self.selected_export_org_id = None
        
        # 知識庫管理相關變數
        self.kb_api_key = tk.StringVar()
        self.kb_base_url = tk.StringVar(value="http://localhost:8000/api/v1/")
        self.kb_export_dir = tk.StringVar()
        self.knowledge_bases = []
        self.selected_kb_id = None
        self.kb_files = []
        self.selected_files = {}  # 用於存儲文件選擇狀態
        
        # 日誌管理
        self.gui_logger = logging.getLogger(f"{__name__}.GUI")
        self.api_logger = logging.getLogger(f"{__name__}.API")
        self.validation_logger = logging.getLogger(f"{__name__}.Validation")
        
        # GUI 運行狀態標誌
        self.gui_running = True
        self._in_logger_callback = False
        self._in_log_message = False
        
        # 日誌限流機制 - 更嚴格的控制
        self._log_queue_size = 0
        self._max_concurrent_logs = 2  # 降低到2個並發
        self._last_log_time = 0
        self._log_throttle_active = False
        self._emergency_throttle = False  # 緊急限流標誌
        self._consecutive_errors = 0  # 連續錯誤計數
        
        # 簡化日誌函數（緊急使用）
        self._emergency_log = lambda msg: print(f"[EMERGENCY] {msg}") if hasattr(self, '_emergency_throttle') and self._emergency_throttle else None
        
        # 靜默模式 - 完全禁用GUI日誌更新
        self._silent_mode = False
        self._simple_console_log = lambda msg: print(f"[SIMPLE] {msg}")
        self._download_in_progress = False
        
        self.create_widgets()
        
        # 記錄啟動日誌
        self.log_info(f"{__app_name__} v{__version__} 已啟動")
        self.log_info(f"日誌系統已初始化，日誌目錄: {Path('logs').absolute()}")
    
    def _setup_macos_fixes(self):
        """設定 macOS 特定的修復"""
        if platform.system() == 'Darwin':  # macOS
            # 設定剪貼板更新間隔
            self.root.after(100, self._periodic_clipboard_update)
            
            # 修復文本組件的重複輸入問題
            self.root.option_add('*Text.highlightThickness', 1)
            
    def _periodic_clipboard_update(self):
        """定期更新剪貼板狀態以防止重複（線程安全）"""
        if not self.gui_running:
            return
            
        try:
            # 定期清理剪貼板狀態，但只在 GUI 運行時
            if self.gui_running:
                self.root.after(1000, self._periodic_clipboard_update)
        except:
            pass
    
    def api_logger_callback(self, method_name, *args, **kwargs):
        """API日誌回調函數 - 啟用詳細日誌版本（帶安全保護）"""
        
        # 檢查是否已初始化完成，避免初始化期間的調用
        if not hasattr(self, 'root') or not hasattr(self, 'log_text'):
            return
        
        # 下載期間靜默模式 - 完全禁用API日誌處理
        if getattr(self, '_download_in_progress', False):
            # 完全跳過API日誌處理，避免任何GUI更新
            return
        
        # 防止遞歸調用和 GUI 關閉後的調用
        if not getattr(self, 'gui_running', True):
            return
            
        # 添加遞歸保護
        if getattr(self, '_in_logger_callback', False):
            return
            
        # 增強緊急限流檢查
        if getattr(self, '_emergency_throttle', False):
            return
            
        # 日誌限流 - API日誌激進限制
        if getattr(self, '_log_queue_size', 0) > 0:  # API日誌不允許任何並發
            return
            
        # 添加調用深度檢查
        try:
            frame_count = len([frame for frame in __import__('inspect').stack()])
            if frame_count > 30:  # 降低閾值，更早返回
                return
        except:
            # 如果檢查失敗，返回而不是繼續
            return
            
        try:
            self._in_logger_callback = True
            
            if method_name == 'log_api_request' and len(args) >= 2:
                url, method = args[0], args[1]
                payload = args[2] if len(args) > 2 else None
                try:
                    self.log_api_request(url, method, payload)
                except:
                    # 如果日誌失敗，直接打印
                    print(f"API請求: {method} {url}")
            elif method_name == 'log_api_response' and len(args) >= 2:
                url, status_code = args[0], args[1]
                response_size = args[2] if len(args) > 2 else 0
                duration = args[3] if len(args) > 3 else None
                try:
                    self.log_api_response(url, status_code, response_size, duration)
                except:
                    # 如果日誌失敗，直接打印
                    print(f"API回應: {url} | 狀態碼: {status_code}")
            elif method_name == 'log_info' and len(args) >= 1:
                message = args[0]
                logger_name = args[1] if len(args) > 1 else 'API'
                try:
                    self.log_info(message, logger_name)
                except:
                    # 如果日誌失敗，直接打印
                    print(f"INFO: {message}")
            elif method_name == 'log_error' and len(args) >= 1:
                message = args[0]
                logger_name = args[1] if len(args) > 1 else 'API'
                try:
                    self.log_error(message, logger_name)
                except:
                    # 如果日誌失敗，直接打印
                    print(f"ERROR: {message}")
        except Exception as e:
            # 完全靜默的錯誤處理，避免任何可能的遞歸調用
            # 只有在開發模式下才打印
            try:
                print(f"Logger callback silent error: {type(e).__name__}")
            except:
                pass
        finally:
            self._in_logger_callback = False
    
    def create_widgets(self):
        """創建 GUI 組件"""
        # 創建筆記本標籤頁
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 設定頁面
        self.create_settings_tab(notebook)
        
        # 驗證頁面
        self.create_validation_tab(notebook)
        
        # 結果頁面
        self.create_results_tab(notebook)
        
        # 組織管理頁面
        self.create_organization_tab(notebook)
        
    def create_settings_tab(self, notebook):
        """創建設定標籤頁（帶滾動條）"""
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="設定")
        
        # 創建可滾動的主框架
        scrollable_container = ScrollableFrame(settings_frame)
        scrollable_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 主框架（在滾動區域內）
        main_frame = scrollable_container.scrollable_frame
        
        # 添加內邊距
        padding_frame = ttk.Frame(main_frame)
        padding_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 文件選擇
        file_frame = ttk.LabelFrame(padding_frame, text="測試文件", padding=10)
        file_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(file_frame, text="測試文件路徑 (CSV/Excel)：").pack(anchor='w')
        file_path_frame = ttk.Frame(file_frame)
        file_path_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Entry(file_path_frame, textvariable=self.csv_file_path, width=60).pack(side='left', fill='x', expand=True)
        ttk.Button(file_path_frame, text="瀏覽", command=self.browse_csv_file).pack(side='right', padx=(5, 0))
        
        # API 設定
        api_frame = ttk.LabelFrame(padding_frame, text="API 設定", padding=10)
        api_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(api_frame, text="API 基礎 URL：").pack(anchor='w')
        ttk.Entry(api_frame, textvariable=self.api_base_url, width=60).pack(fill='x', pady=(5, 10))
        
        ttk.Label(api_frame, text="API 金鑰：").pack(anchor='w')
        ttk.Entry(api_frame, textvariable=self.api_key, width=60, show="*").pack(fill='x', pady=(5, 0))
        
        # Query Metadata 設定
        query_metadata_frame = ttk.LabelFrame(padding_frame, text="查詢元數據設定 (Query Metadata)", padding=10)
        query_metadata_frame.pack(fill='x', pady=(0, 10))
        
        # 啟用/停用 query_metadata
        enable_checkbox = tk.Checkbutton(
            query_metadata_frame,
            text="啟用 Query Metadata（指定知識庫和標籤過濾）",
            variable=self.enable_query_metadata,
            indicatoron=1,
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            bg=self.bg_color,
            activebackground=self.bg_color,
            font=('Arial', 9),
            cursor='hand2',
            anchor='w',
            pady=2,
            command=self.on_query_metadata_toggle
        )
        enable_checkbox.pack(anchor='w', pady=(0, 10))
        
        # 知識庫ID輸入
        self.kb_id_frame = ttk.Frame(query_metadata_frame)
        self.kb_id_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(self.kb_id_frame, text="知識庫 ID：").pack(anchor='w')
        kb_id_entry = ttk.Entry(self.kb_id_frame, textvariable=self.knowledge_base_id, width=60)
        kb_id_entry.pack(fill='x', pady=(5, 0))
        
        # 標籤ID輸入
        self.label_id_frame = ttk.Frame(query_metadata_frame)
        self.label_id_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Label(self.label_id_frame, text="標籤 ID（選填）：").pack(anchor='w')
        label_id_entry = ttk.Entry(self.label_id_frame, textvariable=self.label_id, width=60)
        label_id_entry.pack(fill='x', pady=(5, 0))
        
        # 說明文字
        help_text = ttk.Label(
            query_metadata_frame,
            text="  ↳ 知識庫ID和標籤ID用於限制RAG檢索範圍。不填寫標籤ID則使用知識庫所有內容。",
            font=('Arial', 8),
            foreground='gray'
        )
        help_text.pack(anchor='w', pady=(5, 0))
        
        # 初始狀態設定為停用
        self.on_query_metadata_toggle()
        
        # 上下文組合設定
        context_frame = ttk.LabelFrame(padding_frame, text="對話上下文設定", padding=10)
        context_frame.pack(fill='x', pady=(0, 10))
        
        # 啟用/停用上下文組合
        context_checkbox = tk.Checkbutton(
            context_frame,
            text="啟用同一提問者問題上下文組合",
            variable=self.enable_context_combination,
            indicatoron=1,
            relief='flat',
            borderwidth=0,
            highlightthickness=0,
            bg=self.bg_color,
            activebackground=self.bg_color,
            font=('Arial', 9),
            cursor='hand2',
            anchor='w',
            pady=2
        )
        context_checkbox.pack(anchor='w', pady=(0, 5))
        
        # 說明文字
        context_help = ttk.Label(
            context_frame,
            text="  ↳ 當同一提問者有多個問題時，在開始新對話時會將前面的問題一起發送給AI作為上下文",
            font=('Arial', 8),
            foreground='gray'
        )
        context_help.pack(anchor='w', pady=(0, 0))
        
        # 驗證參數
        param_frame = ttk.LabelFrame(padding_frame, text="驗證參數", padding=10)
        param_frame.pack(fill='x', pady=(0, 10))
        
        # 系統固定使用 RAG 增強模式，檢索片段數量動態調整
        
        # 相似度計算模式選擇
        ttk.Label(param_frame, text="相似度計算模式：").pack(anchor='w', pady=(0, 5))
        similarity_mode_frame = ttk.Frame(param_frame)
        similarity_mode_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Radiobutton(similarity_mode_frame, text="標準模式 (SequenceMatcher)", 
                       variable=self.similarity_mode, value="standard").pack(anchor='w')
        ttk.Radiobutton(similarity_mode_frame, text="字符比例模式 (匹配字符數/應參考節點)", 
                       variable=self.similarity_mode, value="character_ratio").pack(anchor='w')
        
        # 添加模式說明
        mode_help = ttk.Label(param_frame, text="  ↳ 標準模式：基於最長公共子序列 | 字符比例模式：匹配字符數除以預期段落總長度", 
                             font=('Arial', 8), foreground='gray')
        mode_help.pack(anchor='w', pady=(0, 10))
        
        ttk.Label(param_frame, text="相似度閾值 (0.0-1.0)：").pack(anchor='w')
        ttk.Scale(param_frame, from_=0.0, to=1.0, variable=self.similarity_threshold, orient='horizontal').pack(fill='x', pady=(5, 5))
        threshold_label = ttk.Label(param_frame, text="")
        threshold_label.pack(anchor='w')
        self.similarity_threshold.trace_add('write', lambda *args: threshold_label.config(text=f"當前值: {self.similarity_threshold.get():.2f}"))
        
        ttk.Label(param_frame, text="最大並發提問者數：").pack(anchor='w')
        ttk.Scale(param_frame, from_=1, to=20, variable=self.max_concurrent, orient='horizontal').pack(fill='x', pady=(5, 5))
        concurrent_label = ttk.Label(param_frame, text="")
        concurrent_label.pack(anchor='w')
        self.max_concurrent.trace_add('write', lambda *args: concurrent_label.config(text=f"當前值: {self.max_concurrent.get()}"))
        
        ttk.Label(param_frame, text="API 呼叫延遲時間 (秒)：").pack(anchor='w', pady=(10, 0))
        ttk.Scale(param_frame, from_=0.0, to=5.0, variable=self.api_delay, orient='horizontal').pack(fill='x', pady=(5, 5))
        delay_label = ttk.Label(param_frame, text="")
        delay_label.pack(anchor='w')
        self.api_delay.trace_add('write', lambda *args: delay_label.config(text=f"當前值: {self.api_delay.get():.1f} 秒"))
        
        # 添加說明文字
        delay_help = ttk.Label(param_frame, text="  ↳ 連續 API 呼叫之間的延遲時間，有助於避免限流", 
                              font=('Arial', 8), foreground='gray')
        delay_help.pack(anchor='w')
        
        ttk.Label(param_frame, text="API 請求重試次數：").pack(anchor='w', pady=(10, 0))
        ttk.Scale(param_frame, from_=1, to=10, variable=self.max_retries, orient='horizontal').pack(fill='x', pady=(5, 5))
        retries_label = ttk.Label(param_frame, text="")
        retries_label.pack(anchor='w')
        self.max_retries.trace_add('write', lambda *args: retries_label.config(text=f"當前值: {self.max_retries.get()} 次"))
        
        # 添加說明文字
        retries_help = ttk.Label(param_frame, text="  ↳ 遇到網路錯誤時的重試次數，有助於處理臨時連接問題", 
                               font=('Arial', 8), foreground='gray')
        retries_help.pack(anchor='w')
        
        # 段落分隔符選擇
        separator_frame = ttk.LabelFrame(padding_frame, text="段落分隔符設定", padding=10)
        separator_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(separator_frame, text="選擇用於分割預期文件段落的分隔符：").pack(anchor='w', pady=(0, 5))
        
        # 創建兩欄的複選框布局
        checkbox_frame = ttk.Frame(separator_frame)
        checkbox_frame.pack(fill='x')
        
        left_column = ttk.Frame(checkbox_frame)
        left_column.pack(side='left', fill='both', expand=True)
        
        right_column = ttk.Frame(checkbox_frame)
        right_column.pack(side='right', fill='both', expand=True)
        
        # 分隔符選項配置
        separator_configs = [
            ('---', '三個連字符 (---)', '用於標記段落分界'),
            ('|||', '三個豎線 (|||)', '垂直分隔符號'),
            ('\n\n', '雙換行符 (\\n\\n)', '空行分隔段落'),
            ('###', '三個井號 (###)', 'Markdown 標題格式'),
            ('===', '三個等號 (===)', '水平分隔線'),
            ('...', '三個點號 (...)', '省略號分隔符')
        ]
        
        # 添加複選框
        for i, (sep_key, display_text, description) in enumerate(separator_configs):
            parent_frame = left_column if i < 3 else right_column
            
            checkbox_item_frame = ttk.Frame(parent_frame)
            checkbox_item_frame.pack(fill='x', pady=2)
            
            # 使用標準 Checkbutton 以獲得打勾樣式
            checkbox = tk.Checkbutton(
                checkbox_item_frame, 
                text=display_text,
                variable=self.separator_vars[sep_key],
                indicatoron=1,  # 顯示標準的勾選框而非按鈕樣式
                relief='flat',  # 平面風格
                borderwidth=0,  # 無邊框
                highlightthickness=0,  # 無高亮邊框
                bg=self.bg_color,  # 使用主題背景色
                activebackground=self.bg_color,  # 滑鼠懸停時的背景色
                font=('Arial', 9),  # 設定字體
                cursor='hand2',  # 滑鼠指標變為手型
                anchor='w',  # 文字左對齊
                pady=2  # 垂直間距
            )
            checkbox.pack(anchor='w')
            
            # 添加描述標籤
            desc_label = ttk.Label(
                checkbox_item_frame, 
                text=f"  ↳ {description}",
                font=('Arial', 8),
                foreground='gray'
            )
            desc_label.pack(anchor='w', padx=(20, 0))
        
        # 分隔符預覽和測試
        preview_frame = ttk.Frame(separator_frame)
        preview_frame.pack(fill='x', pady=(10, 0))
        
        ttk.Button(preview_frame, text="測試分隔符", command=self.test_separators).pack(side='left')
        ttk.Button(preview_frame, text="重設為預設", command=self.reset_separators).pack(side='left', padx=(10, 0))
        
        # 操作按鈕
        button_frame = ttk.Frame(padding_frame)
        button_frame.pack(fill='x', pady=(20, 0))
        
        ttk.Button(button_frame, text="測試連接", command=self.test_connection).pack(side='left')
        ttk.Button(button_frame, text="載入設定", command=self.load_config).pack(side='left', padx=(10, 0))
        ttk.Button(button_frame, text="儲存設定", command=self.save_config).pack(side='left', padx=(10, 0))
        ttk.Button(button_frame, text="關於程式", command=self.show_about).pack(side='right')
        
    def create_validation_tab(self, notebook):
        """創建驗證標籤頁（帶滾動條）"""
        validation_frame = ttk.Frame(notebook)
        notebook.add(validation_frame, text="驗證")
        
        # 創建可滾動的主框架
        scrollable_container = ScrollableFrame(validation_frame)
        scrollable_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 主框架（在滾動區域內）
        main_frame = scrollable_container.scrollable_frame
        
        # 添加內邊距
        padding_frame = ttk.Frame(main_frame)
        padding_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 聊天機器人選擇
        bot_frame = ttk.LabelFrame(padding_frame, text="聊天機器人選擇", padding=10)
        bot_frame.pack(fill='x', pady=(0, 10))
        
        self.bot_listbox = tk.Listbox(bot_frame, height=5)
        self.bot_listbox.pack(fill='x', pady=(0, 10))
        
        ttk.Button(bot_frame, text="重新載入機器人列表", command=self.refresh_chatbots).pack(side='left')
        
        # 驗證控制
        control_frame = ttk.LabelFrame(padding_frame, text="驗證控制", padding=10)
        control_frame.pack(fill='x', pady=(0, 10))
        
        self.start_button = ttk.Button(control_frame, text="開始驗證", command=self.start_validation)
        self.start_button.pack(side='left')
        
        self.stop_button = ttk.Button(control_frame, text="停止驗證", command=self.stop_validation, state='disabled')
        self.stop_button.pack(side='left', padx=(10, 0))
        
        self.retry_failed_button = ttk.Button(control_frame, text="重測失敗問題", command=self.retry_failed_from_csv)
        self.retry_failed_button.pack(side='left', padx=(10, 0))
        
        # 進度顯示
        progress_frame = ttk.LabelFrame(padding_frame, text="進度", padding=10)
        progress_frame.pack(fill='x', pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill='x', pady=(0, 5))
        
        self.progress_label = ttk.Label(progress_frame, text="準備中...")
        self.progress_label.pack(anchor='w')
        
        # 日誌顯示（優化版）
        log_frame = ttk.LabelFrame(padding_frame, text="📋 執行日誌", padding=10)
        log_frame.pack(fill='both', expand=True)
        
        # 日誌控制按鈕（第一行）
        log_control_frame1 = ttk.Frame(log_frame)
        log_control_frame1.pack(fill='x', pady=(0, 5))
        
        ttk.Button(log_control_frame1, text="🗑️ 清空日誌", command=self.clear_log_display).pack(side='left')
        ttk.Button(log_control_frame1, text="📤 匯出日誌", command=self.export_logs).pack(side='left', padx=(5, 0))
        ttk.Button(log_control_frame1, text="📁 開啟日誌資料夾", command=self.open_log_folder).pack(side='left', padx=(5, 0))
        
        # 自動滾動控制
        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_control_frame1, text="🔄 自動滾動", variable=self.auto_scroll_var).pack(side='left', padx=(20, 0))
        
        # 日誌過濾控制（第二行）
        log_control_frame2 = ttk.Frame(log_frame)
        log_control_frame2.pack(fill='x', pady=(0, 5))
        
        # 日誌級別過濾
        ttk.Label(log_control_frame2, text="🎚️ 顯示級別:").pack(side='left')
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_combo = ttk.Combobox(log_control_frame2, textvariable=self.log_level_var, 
                                      values=["ALL", "DEBUG", "INFO", "WARNING", "ERROR"], 
                                      width=8, state="readonly")
        log_level_combo.pack(side='left', padx=(5, 0))
        log_level_combo.bind('<<ComboboxSelected>>', self.on_log_level_changed)
        
        # 日誌類型過濾
        ttk.Label(log_control_frame2, text="📂 日誌類型:").pack(side='left', padx=(15, 5))
        self.log_type_var = tk.StringVar(value="ALL")
        log_type_combo = ttk.Combobox(log_control_frame2, textvariable=self.log_type_var,
                                     values=["ALL", "GUI", "API", "Validation", "Retry"],
                                     width=8, state="readonly")
        log_type_combo.pack(side='left')
        log_type_combo.bind('<<ComboboxSelected>>', self.on_log_type_changed)
        
        # 搜索功能
        ttk.Label(log_control_frame2, text="🔍 搜索:").pack(side='left', padx=(15, 5))
        self.log_search_var = tk.StringVar()
        search_entry = ttk.Entry(log_control_frame2, textvariable=self.log_search_var, width=15)
        search_entry.pack(side='left')
        search_entry.bind('<KeyRelease>', self.on_log_search_changed)
        ttk.Button(log_control_frame2, text="❌", command=self.clear_log_search, width=3).pack(side='left', padx=(2, 0))
        
        # 統計信息
        self.log_stats_label = ttk.Label(log_control_frame2, text="", font=('Arial', 8))
        self.log_stats_label.pack(side='right')
        
        # 創建日誌文本框（優化版）
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state='disabled', wrap='word')
        self.log_text.pack(fill='both', expand=True)
        
        # 配置日誌文本框的字體和顏色
        self.setup_log_text_styling()
        
        # 初始化日誌統計
        self.log_stats = {
            'DEBUG': 0,
            'INFO': 0,
            'WARNING': 0,
            'ERROR': 0,
            'total': 0
        }
        
    def create_results_tab(self, notebook):
        """創建結果標籤頁（帶滾動條）"""
        results_frame = ttk.Frame(notebook)
        notebook.add(results_frame, text="結果")
        
        # 創建可滾動的主框架
        scrollable_container = ScrollableFrame(results_frame)
        scrollable_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 主框架（在滾動區域內）
        main_frame = scrollable_container.scrollable_frame
        
        # 添加內邊距
        padding_frame = ttk.Frame(main_frame)
        padding_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 統計結果
        stats_frame = ttk.LabelFrame(padding_frame, text="統計結果", padding=10)
        stats_frame.pack(fill='x', pady=(0, 10))
        
        self.stats_text = tk.Text(stats_frame, height=10, state='disabled')
        self.stats_text.pack(fill='x')
        
        # 操作按鈕
        button_frame = ttk.Frame(padding_frame)
        button_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Button(button_frame, text="開啟結果文件", command=self.open_results_file).pack(side='left')
        ttk.Button(button_frame, text="開啟結果資料夾", command=self.open_results_folder).pack(side='left', padx=(10, 0))
        ttk.Button(button_frame, text="輸出 Excel", command=self.export_to_excel).pack(side='left', padx=(10, 0))
        ttk.Button(button_frame, text="檢視日誌統計", command=self.show_log_stats).pack(side='left', padx=(10, 0))
        
        # 詳細結果
        details_frame = ttk.LabelFrame(padding_frame, text="詳細結果", padding=10)
        details_frame.pack(fill='both', expand=True)
        
        # 創建樹狀檢視
        columns = ('編號', '提問者', '問題', 'AI回覆', '引用命中', '文件正確')
        self.results_tree = ttk.Treeview(details_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.results_tree.heading(col, text=col)
            if col == '問題' or col == 'AI回覆':
                self.results_tree.column(col, width=200)
            else:
                self.results_tree.column(col, width=80)
        
        # 添加滾動條
        scrollbar = ttk.Scrollbar(details_frame, orient='vertical', command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=scrollbar.set)
        
        self.results_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def browse_csv_file(self):
        """瀏覽選擇 CSV 或 Excel 文件"""
        filename = filedialog.askopenfilename(
            title="選擇測試文件 (CSV 或 Excel)",
            filetypes=[
                ("支援的文件", "*.csv *.xlsx *.xls"), 
                ("CSV files", "*.csv"), 
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*")
            ]
        )
        if filename:
            self.csv_file_path.set(filename)
            
    def test_connection(self):
        """測試 API 連接"""
        if not self.api_key.get():
            messagebox.showerror("錯誤", "請輸入 API 金鑰")
            return
            
        def test_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def test():
                    async with MaiAgentApiClient(self.api_base_url.get(), self.api_key.get(), self.api_logger_callback) as client:
                        chatbots = await client.get_chatbots()
                        return len(chatbots)
                
                count = loop.run_until_complete(test())
                loop.close()
                
                self.root.after(0, lambda: messagebox.showinfo("成功", f"連接成功！找到 {count} 個聊天機器人"))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"連接失敗：{error_msg}"))
        
        threading.Thread(target=test_async, daemon=True).start()
        
    def refresh_chatbots(self):
        """重新載入聊天機器人列表"""
        if not self.api_key.get():
            messagebox.showerror("錯誤", "請先設定 API 金鑰")
            return
            
        def refresh_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def fetch():
                    async with MaiAgentApiClient(self.api_base_url.get(), self.api_key.get(), self.api_logger_callback) as client:
                        return await client.get_chatbots()
                
                chatbots = loop.run_until_complete(fetch())
                loop.close()
                
                # 更新 UI
                self.root.after(0, lambda: self.update_chatbot_list(chatbots))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入失敗：{error_msg}"))
        
        threading.Thread(target=refresh_async, daemon=True).start()
        
    def update_chatbot_list(self, chatbots):
        """更新聊天機器人列表"""
        self.bot_listbox.delete(0, tk.END)
        self.chatbots = chatbots
        
        for i, bot in enumerate(chatbots):
            self.bot_listbox.insert(tk.END, f"{bot.get('name', 'Unknown')} (ID: {bot.get('id')})")
            
    def start_validation(self):
        """開始驗證"""
        # 檢查設定
        if not self.csv_file_path.get():
            messagebox.showerror("錯誤", "請選擇測試文件 (CSV 或 Excel)")
            return
            
        if not self.api_key.get():
            messagebox.showerror("錯誤", "請設定 API 金鑰")
            return
            
        selection = self.bot_listbox.curselection()
        if not selection:
            messagebox.showerror("錯誤", "請選擇聊天機器人")
            return
            
        self.selected_chatbot_id = self.chatbots[selection[0]]['id']
        
        # 重設停止標志和進度計數器
        self.validation_stopped = False
        self.completed_questions = 0
        
        # 更新 UI 狀態
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.progress_bar['value'] = 0
        self.progress_label.config(text="準備中...")
        
        # 清空日誌
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # 開始驗證
        threading.Thread(target=self.run_validation, daemon=True).start()
        
    def stop_validation(self):
        """停止驗證"""
        self.validation_stopped = True
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.log_warning("正在停止驗證，請稍候...")
        
    def run_validation(self):
        """執行驗證（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 載入數據
            self.log_info("正在載入測試數據...")
            validation_data = self.load_csv_data()
            
            total_questions = len(validation_data)
            self.progress_bar['maximum'] = total_questions
            self.log_info(f"載入完成，共 {total_questions} 個問題")
            
            # 執行驗證
            selected_seps = self.get_selected_separators()
            self.log_info(f"開始執行驗證...")
            self.log_info(f"使用的分隔符: {', '.join(selected_seps)}")
            results = loop.run_until_complete(self.process_validation(validation_data))
            
            # 計算統計
            self.log_info("計算統計結果...")
            stats = self.calculate_statistics(results)
            
            # 輸出結果（預設為 CSV 格式）
            output_file = f"validation_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self.log_info(f"匯出結果到 CSV: {output_file}")
            self.export_results(results, output_file, stats)
            
            # 更新 UI
            self.log_info("驗證完成，更新結果顯示")
            self.root.after(0, lambda: self.show_results(results, stats, output_file))
            
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"驗證過程發生錯誤：{error_msg}"))
        finally:
            # 檢查是否是正常完成還是被停止
            if self.validation_stopped:
                self.root.after(0, lambda: self.log_warning("驗證已停止"))
            # 重設 UI 狀態
            self.root.after(0, lambda: self.reset_validation_ui())
            
    def load_csv_data(self):
        """載入 CSV 或 Excel 數據"""
        file_path = self.csv_file_path.get()
        file_extension = os.path.splitext(file_path)[1].lower()
        
        try:
            # 根據文件擴展名選擇適當的讀取方法
            if file_extension == '.csv':
                df = self._read_csv_with_encoding_detection(file_path)
            elif file_extension in ['.xlsx', '.xls']:
                df = pd.read_excel(file_path, engine='openpyxl' if file_extension == '.xlsx' else None)
            else:
                raise ValueError(f"不支援的文件格式: {file_extension}")
            
            # 檢查必要的欄位 - 支援多種欄位名稱
            required_columns = ['編號', '提問者']
            actual_columns = list(df.columns)
            missing_columns = [col for col in required_columns if col not in actual_columns]
            
            # 檢查問題內容欄位（支援多種名稱）
            question_column = None
            for possible_name in ['問題描述', '對話內容', '問題內容', '內容']:
                if possible_name in actual_columns:
                    question_column = possible_name
                    break
            
            if not question_column:
                missing_columns.append('問題描述/對話內容')
            
            if missing_columns:
                self.log_error(f"文件缺少必要欄位: {', '.join(missing_columns)}")
                self.log_error(f"實際欄位: {', '.join(actual_columns)}")
                raise ValueError(f"文件缺少必要欄位: {', '.join(missing_columns)}\\n\\n實際欄位: {', '.join(actual_columns)}\\n\\n請確保文件包含以下欄位：編號、提問者、問題描述/對話內容")
            
            self.log_info(f"成功載入文件，共 {len(df)} 行數據")
            self.log_info(f"使用 '{question_column}' 作為問題內容欄位")
            self.log_info(f"文件欄位: {', '.join(actual_columns)}")
            
            validation_rows = []
            for _, row in df.iterrows():
                validation_row = ValidationRow(
                    編號=str(row['編號']),
                    提問者=str(row['提問者']),
                    問題描述=str(row[question_column]),  # 使用動態檢測到的欄位名稱
                    建議_or_正確答案=str(row.get('建議 or 正確答案 (if have)', '')),
                    應參考的文件=str(row.get('應參考的文件', '')),
                    應參考的文件段落=str(row.get('應參考的文件段落', '')),
                    應參考文件UUID=str(row.get('應參考文件UUID', '')),  # 新增UUID欄位
                    是否檢索KM推薦=str(row.get('是否檢索KM推薦', ''))  # 新增欄位
                )
                validation_rows.append(validation_row)
                
            return validation_rows
            
        except Exception as e:
            self.log_error(f"載入文件失敗: {str(e)}")
            raise
        
    async def process_validation(self, validation_data):
        """處理驗證 - 支援併發處理多個提問者"""
        # 清空對話管理器的上下文（新的驗證開始）
        self.conversation_manager.conversations.clear()
        self.conversation_manager.questioner_context.clear()
        self.log_info("已清空對話上下文，開始新的驗證")
        
        # 篩選需要檢索KM推薦的記錄
        filtered_data = []
        skipped_count = 0
        
        for row in validation_data:
            if row.是否檢索KM推薦.strip() == "是":
                filtered_data.append(row)
            else:
                skipped_count += 1
                # 為跳過的記錄設置預設值
                row.AI助理回覆 = "跳過驗證（未標記為檢索KM推薦）"
                row.引用節點是否命中 = "跳過"
                row.參考文件是否正確 = "跳過"
                row.回覆是否滿意 = "跳過"
        
        self.log_info(f"總共 {len(validation_data)} 筆記錄")
        self.log_info(f"需要驗證的記錄: {len(filtered_data)} 筆（標記為「是」）")
        self.log_info(f"跳過的記錄: {skipped_count} 筆（未標記為「是」）")
        
        if len(filtered_data) == 0:
            self.log_warning("沒有標記為「是」的記錄需要驗證")
            return validation_data  # 返回原始數據（包含跳過的記錄）
        
        # 按提問者分組（只處理需要驗證的記錄）
        user_groups = {}
        for row in filtered_data:
            user = row.提問者
            if user not in user_groups:
                user_groups[user] = []
            user_groups[user].append(row)
        
        self.log_info(f"發現 {len(user_groups)} 個不同的提問者")
        self.log_info(f"提問者列表: {', '.join(user_groups.keys())}")
        max_concurrent_users = self.max_concurrent.get()
        self.log_info(f"開始併發處理，最多同時處理 {max_concurrent_users} 個提問者")
        
        # 創建進度追蹤鎖
        progress_lock = asyncio.Lock()
        
        # 創建結果字典，用於快速查找
        results_dict = {}
        
        async with MaiAgentApiClient(self.api_base_url.get(), self.api_key.get(), self.api_logger_callback) as client:
            # 使用 Semaphore 控制併發數量
            semaphore = asyncio.Semaphore(max_concurrent_users)
            
            # 創建每個提問者的處理任務
            tasks = []
            for user, user_questions in user_groups.items():
                task = self.process_user_questions(client, user, user_questions, semaphore, len(validation_data), progress_lock, results_dict)
                tasks.append(task)
            
            # 併發執行所有提問者的任務
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # === 重試失敗問題檢查與重新測試 ===
            await self.check_and_retry_failed_questions(client, filtered_data, results_dict, progress_lock, len(validation_data))
        
        # 按原始順序整理結果（包含所有記錄：驗證的和跳過的）
        results = []
        for row in validation_data:
            if row.編號 in results_dict:
                # 使用驗證結果
                results.append(results_dict[row.編號])
            else:
                # 檢查是否為跳過的記錄
                if row.是否檢索KM推薦.strip() != "是":
                    # 已經在篩選階段設置了跳過狀態，直接使用
                    # 確保跳過的記錄具有所有統計屬性
                    row.precision = 0.0
                    row.recall = 0.0
                    row.f1_score = 0.0
                    row.hit_rate = 0.0
                else:
                    # 標記為「是」但未處理的記錄（可能因為停止或錯誤）
                    if not row.AI助理回覆 or row.AI助理回覆 == "":
                        row.AI助理回覆 = "未處理（驗證中斷）"
                    
                    # 確保未處理的 row 具有所有統計屬性
                    row.precision = 0.0
                    row.recall = 0.0
                    row.f1_score = 0.0
                    row.hit_rate = 0.0
                    if not row.引用節點是否命中:
                        row.引用節點是否命中 = "否"
                    if not row.參考文件是否正確:
                        row.參考文件是否正確 = "否"
                    if not row.回覆是否滿意:
                        row.回覆是否滿意 = "否"
                
                results.append(row)
                    
        return results
    
    async def check_and_retry_failed_questions(self, client, filtered_data, results_dict, progress_lock, total_questions):
        """檢查並重試失敗的問題"""
        if self.validation_stopped:
            self.log_info("驗證已停止，跳過失敗問題重試檢查")
            return
            
        # 識別失敗的問題
        failed_questions = []
        for row in filtered_data:
            if row.編號 in results_dict:
                result = results_dict[row.編號]
                # 檢查是否為重試失敗的問題
                if (hasattr(result, 'AI助理回覆') and 
                    result.AI助理回覆 and 
                    (result.AI助理回覆.startswith("錯誤:") or 
                     "API 請求在" in result.AI助理回覆 or 
                     "次重試後仍然失敗" in result.AI助理回覆)):
                    failed_questions.append(row)
            else:
                # 未處理的問題也算失敗
                failed_questions.append(row)
        
        if not failed_questions:
            self.log_info("✅ 所有問題都已成功驗證，無需重試")
            return
        
        # 記錄失敗問題統計
        self.log_warning(f"🔍 發現 {len(failed_questions)} 個失敗問題，準備進行重試...")
        
        # 按提問者分組失敗問題
        failed_user_groups = {}
        for row in failed_questions:
            user = row.提問者
            if user not in failed_user_groups:
                failed_user_groups[user] = []
            failed_user_groups[user].append(row)
        
        self.log_info(f"📊 失敗問題分布：{', '.join([f'{user}({len(questions)}題)' for user, questions in failed_user_groups.items()])}")
        
        # 重試配置：降低併發數，增加延遲和重試次數
        retry_max_concurrent = max(1, self.max_concurrent.get() // 2)  # 降低併發數
        retry_delay = self.api_delay.get() * 2  # 增加延遲
        retry_attempts = min(self.max_retries.get() + 2, 8)  # 增加重試次數，最多8次
        
        self.log_info(f"🔄 重試配置：併發數={retry_max_concurrent}, 延遲={retry_delay}秒, 重試次數={retry_attempts}")
        
        # 使用更保守的併發控制進行重試
        retry_semaphore = asyncio.Semaphore(retry_max_concurrent)
        retry_tasks = []
        
        for user, user_questions in failed_user_groups.items():
            if self.validation_stopped:
                break
            task = self.retry_user_questions(client, user, user_questions, retry_semaphore, 
                                           total_questions, progress_lock, results_dict, 
                                           retry_delay, retry_attempts)
            retry_tasks.append(task)
        
        if retry_tasks:
            self.log_info(f"🚀 開始重試 {len(retry_tasks)} 個提問者的失敗問題...")
            await asyncio.gather(*retry_tasks, return_exceptions=True)
            
            # 檢查重試結果
            still_failed = []
            retry_success = 0
            for row in failed_questions:
                if row.編號 in results_dict:
                    result = results_dict[row.編號]
                    if (hasattr(result, 'AI助理回覆') and 
                        result.AI助理回覆 and 
                        not (result.AI助理回覆.startswith("錯誤:") or 
                             "API 請求在" in result.AI助理回覆 or 
                             "次重試後仍然失敗" in result.AI助理回覆)):
                        retry_success += 1
                    else:
                        still_failed.append(row.編號)
                else:
                    still_failed.append(row.編號)
            
            # 報告重試結果
            self.log_info(f"📈 重試完成統計：")
            self.log_info(f"   ✅ 重試成功：{retry_success} 題")
            self.log_info(f"   ❌ 仍然失敗：{len(still_failed)} 題")
            
            if still_failed:
                self.log_warning(f"⚠️ 以下問題經重試後仍然失敗：{', '.join(still_failed[:10])}" + 
                               (f" 等{len(still_failed)}題" if len(still_failed) > 10 else ""))
            else:
                self.log_info("🎉 所有失敗問題都已成功重試完成！")
        else:
            self.log_warning("重試任務創建失敗或驗證已停止")
    
    async def retry_user_questions(self, client, user, user_questions, semaphore, total_questions, 
                                 progress_lock, results_dict, retry_delay, retry_attempts):
        """重試特定提問者的失敗問題"""
        async with semaphore:
            if self.validation_stopped:
                return
                
            self.log_info(f"🔄 開始重試提問者 '{user}' 的 {len(user_questions)} 個失敗問題")
            
            for row in user_questions:
                if self.validation_stopped:
                    break
                    
                try:
                    # 清除之前的錯誤狀態
                    row.AI助理回覆 = ""
                    row.引用節點是否命中 = ""
                    row.參考文件是否正確 = ""
                    
                    # 使用更保守的重試設定處理問題
                    result = await self.process_single_question_with_retry(
                        client, row, retry_attempts, retry_delay)
                    
                    # 更新結果
                    async with progress_lock:
                        # 標記為重試成功
                        result._retry_info = "重試成功"
                        results_dict[row.編號] = result
                        
                        # 更新進度顯示（重試）
                        progress_msg = f"[重試-{user}] 完成問題 {row.編號} | 失敗問題重試中"
                        self.root.after(0, lambda msg=progress_msg: self.update_progress(
                            self.completed_questions, total_questions, msg))
                    
                    self.log_validation_result(row.編號, True, 
                                             f"[重試-{user}] 重試成功，回覆長度: {len(result.AI助理回覆)} 字元")
                    
                except Exception as e:
                    self.log_error(f"重試提問者 '{user}' 的問題 {row.編號} 仍然失敗: {str(e)}", 'Retry')
                    
                    # 標記為最終失敗
                    async with progress_lock:
                        row.AI助理回覆 = f"重試失敗: {str(e)}"
                        row.precision = 0.0
                        row.recall = 0.0
                        row.f1_score = 0.0
                        row.hit_rate = 0.0
                        row.引用節點是否命中 = "否"
                        row.參考文件是否正確 = "否"
                        row.回覆是否滿意 = "否"
                        
                        results_dict[row.編號] = row
                        
                        progress_msg = f"[重試-{user}] 問題 {row.編號} 最終失敗 | 失敗問題重試中"
                        self.root.after(0, lambda msg=progress_msg: self.update_progress(
                            self.completed_questions, total_questions, msg))
                
                # 重試間隔延遲
                if not self.validation_stopped:
                    await asyncio.sleep(retry_delay)
            
            self.log_info(f"🏁 提問者 '{user}' 的失敗問題重試完成")
    
    async def process_single_question_with_retry(self, client, validation_row, max_retries, delay):
        """使用自定義重試參數處理單個問題"""
        # 獲取或創建對話
        conversation_id = self.conversation_manager.get_conversation_id(validation_row.提問者)
        
        # 構建要發送的問題內容（重試時使用原始問題，因為上下文已經在初次處理時建立）
        message_content = validation_row.問題描述
        
        # 如果這是重試且沒有對話ID，說明是重新開始對話，需要構建上下文
        if conversation_id is None and self.enable_context_combination.get():
            # 檢查是否有之前的問題需要組合（排除當前問題本身）
            previous_questions = self.conversation_manager.get_context_questions(validation_row.提問者)
            # 移除最後一個問題（當前問題），只使用前面的問題作為上下文
            if previous_questions and len(previous_questions) > 1:
                context_questions = previous_questions[:-1]  # 排除當前問題
                if context_questions:
                    context_parts = []
                    context_parts.append("這是一系列相關的問題：")
                    context_parts.append("")
                    
                    # 添加前面的問題
                    for i, prev_question in enumerate(context_questions, 1):
                        context_parts.append(f"問題 {i}：{prev_question}")
                    
                    # 添加當前問題
                    context_parts.append(f"問題 {len(context_questions) + 1}：{validation_row.問題描述}")
                    context_parts.append("")
                    context_parts.append("請針對這一系列問題提供完整的回答，特別是最後一個問題。")
                    
                    message_content = "\n".join(context_parts)
                    
                    self.log_info(
                        f"重試時為提問者 '{validation_row.提問者}' 重新構建上下文，包含 {len(context_questions)} 個前面的問題", 
                        'Validation'
                    )
        
        # 構建 query_metadata（如果啟用）
        query_metadata = None
        if self.enable_query_metadata.get() and self.knowledge_base_id.get().strip():
            knowledge_bases = [
                {
                    "knowledge_base_id": self.knowledge_base_id.get().strip(),
                    "has_user_selected_all": True
                }
            ]
            
            query_metadata = {
                "knowledge_bases": knowledge_bases
            }
            
            # 如果提供了標籤ID，添加標籤過濾
            if self.label_id.get().strip():
                query_metadata["label_relations"] = {
                    "operator": "OR",
                    "conditions": [
                        {"label_id": self.label_id.get().strip()}
                    ]
                }
        
        # 發送問題（使用自定義重試機制）
        response = await client.send_message(
            self.selected_chatbot_id,
            message_content,  # 使用構建的內容
            conversation_id,
            max_retries=max_retries,
            query_metadata=query_metadata
        )
        
        # 設定對話 ID（如果是新對話）
        if not conversation_id and response.conversation_id:
            self.conversation_manager.set_conversation_id(validation_row.提問者, response.conversation_id)
        
        # 進行 RAG 增強驗證
        actual_chunks_count = len(response.citations) if response.citations else 0
        citation_hit, rag_metrics = self.text_matcher.check_rag_enhanced_hit(
            response.citations,
            validation_row.應參考的文件段落,
            self.similarity_threshold.get(),
            actual_chunks_count,  # 使用實際回傳的節點數量
            self.get_selected_separators(),  # 使用用戶選擇的分隔符
            self.similarity_mode.get()  # 使用用戶選擇的相似度計算模式
        )
        
        # 更新驗證行的結果
        validation_row.AI助理回覆 = response.content
        validation_row.precision = rag_metrics['precision']
        validation_row.recall = rag_metrics['recall']
        validation_row.f1_score = rag_metrics['f1_score']
        validation_row.hit_rate = rag_metrics['hit_rate']
        validation_row.引用節點是否命中 = "是" if citation_hit else "否"
        
        # 僅使用應參考文件UUID進行匹配
        expected_files = validation_row.應參考文件UUID.strip()
        
        if expected_files:
            file_match, file_stats = self.text_matcher.check_citation_file_match(
                response.citations,
                expected_files
            )
            validation_row.參考文件是否正確 = "是" if file_match else "否"
        else:
            # 如果沒有UUID，跳過文件匹配
            file_match = False
            file_stats = {
                "detail": "無UUID資料，跳過文件匹配",
                "total_expected": 0,
                "total_matched": 0,
                "hit_rate": 0.0,
                "matched_files": [],
                "unmatched_files": [],
                "all_matched": False
            }
            validation_row.參考文件是否正確 = "未檢測"
        
        # 儲存參考文件命中統計數據
        validation_row.參考文件命中率 = file_stats.get('hit_rate', 0.0)
        validation_row.期望文件總數 = file_stats.get('total_expected', 0)
        validation_row.命中文件數 = file_stats.get('total_matched', 0)
        
        # UUID格式的命中和未命中文件信息
        matched_files = file_stats.get('matched_files', [])
        validation_row.命中文件 = ', '.join(matched_files) if matched_files else ""
        
        unmatched_files = file_stats.get('unmatched_files', [])
        validation_row.未命中文件 = ', '.join(unmatched_files) if unmatched_files else ""
        
        # 動態添加參考文件欄位
        self._add_citation_file_fields(validation_row, response.citations)
        
        # 添加延遲
        await asyncio.sleep(delay)
        
        return validation_row
    
    def _read_csv_with_encoding_detection(self, file_path):
        """使用編碼檢測讀取CSV文件"""
        import chardet
        
        # 常見的編碼格式列表（按優先級排序）
        encodings_to_try = [
            'utf-8-sig',    # UTF-8 with BOM (Excel常用)
            'utf-8',        # 標準UTF-8
            'big5',         # 繁體中文
            'gbk',          # 簡體中文
            'cp950',        # Windows繁體中文
            'cp1252',       # Windows Western
            'iso-8859-1',   # Latin-1
            'ascii'         # 純ASCII
        ]
        
        # 先嘗試檢測文件編碼
        try:
            with open(file_path, 'rb') as file:
                raw_data = file.read()
                detected = chardet.detect(raw_data)
                detected_encoding = detected.get('encoding', '')
                confidence = detected.get('confidence', 0)
                
                self.log_info(f"🔍 檢測到文件編碼: {detected_encoding} (信心度: {confidence:.2f})")
                
                # 如果檢測信心度較高，優先使用檢測到的編碼
                if confidence > 0.7 and detected_encoding:
                    encodings_to_try.insert(0, detected_encoding.lower())
        except Exception as e:
            self.log_warning(f"編碼檢測失敗: {e}")
        
        # 逐一嘗試不同編碼
        last_error = None
        for encoding in encodings_to_try:
            try:
                self.log_info(f"🔄 嘗試使用編碼: {encoding}")
                df = pd.read_csv(file_path, encoding=encoding)
                self.log_info(f"✅ 成功使用編碼 {encoding} 讀取文件")
                return df
            except UnicodeDecodeError as e:
                last_error = e
                self.log_warning(f"❌ 編碼 {encoding} 讀取失敗: {str(e)[:100]}")
                continue
            except Exception as e:
                last_error = e
                self.log_warning(f"❌ 使用編碼 {encoding} 時發生錯誤: {str(e)[:100]}")
                continue
        
        # 如果所有編碼都失敗，拋出錯誤
        raise ValueError(f"無法讀取CSV文件，已嘗試多種編碼格式。最後錯誤: {last_error}")
    
    def setup_log_text_styling(self):
        """設置日誌文本框的樣式"""
        # 設置字體
        self.log_text.configure(font=('Consolas', 9))
        
        # 配置日誌級別顏色和樣式
        self.log_text.tag_config('debug', foreground='#808080', font=('Consolas', 9, 'italic'))
        self.log_text.tag_config('info', foreground='#000000', font=('Consolas', 9))
        self.log_text.tag_config('warning', foreground='#FF8C00', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('error', foreground='#DC143C', font=('Consolas', 9, 'bold'))
        self.log_text.tag_config('critical', foreground='#8B0000', font=('Consolas', 9, 'bold'))
        
        # 配置日誌類型樣式
        self.log_text.tag_config('gui_tag', foreground='#4169E1')
        self.log_text.tag_config('api_tag', foreground='#32CD32')
        self.log_text.tag_config('validation_tag', foreground='#FF69B4')
        self.log_text.tag_config('retry_tag', foreground='#FFD700')
        
        # 配置時間戳樣式
        self.log_text.tag_config('timestamp', foreground='#696969', font=('Consolas', 8))
        
        # 配置高亮搜索結果
        self.log_text.tag_config('search_highlight', background='#FFFF00', foreground='#000000')
    
    def on_log_level_changed(self, event=None):
        """日誌級別過濾變更處理"""
        self.refresh_log_display()
    
    def on_log_type_changed(self, event=None):
        """日誌類型過濾變更處理"""
        self.refresh_log_display()
    
    def on_log_search_changed(self, event=None):
        """搜索內容變更處理"""
        self.refresh_log_display()
    
    def clear_log_search(self):
        """清空搜索"""
        self.log_search_var.set("")
        self.refresh_log_display()
    
    def on_query_metadata_toggle(self):
        """切換 Query Metadata 輸入欄位的啟用狀態"""
        state = 'normal' if self.enable_query_metadata.get() else 'disabled'
        
        # 設定知識庫ID欄位
        for widget in self.kb_id_frame.winfo_children():
            if isinstance(widget, ttk.Entry):
                widget.config(state=state)
        
        # 設定標籤ID欄位
        for widget in self.label_id_frame.winfo_children():
            if isinstance(widget, ttk.Entry):
                widget.config(state=state)
    
    def refresh_log_display(self):
        """刷新日誌顯示（根據過濾條件）"""
        if not hasattr(self, 'log_text'):
            return
            
        try:
            # 獲取過濾條件
            level_filter = self.log_level_var.get()
            type_filter = self.log_type_var.get()
            search_text = self.log_search_var.get().lower()
            
            # 清空當前顯示
            self.log_text.config(state='normal')
            self.log_text.delete('1.0', tk.END)
            
            # 重新顯示符合條件的日誌（這裡應該從內存中的日誌緩存重新載入）
            # 由於原始實現沒有日誌緩存，這裡先實現基本功能
            self.log_text.config(state='disabled')
            
            self.update_log_stats()
            
        except Exception as e:
            pass  # 靜默處理刷新錯誤
    
    def update_log_stats(self):
        """更新日誌統計信息"""
        if hasattr(self, 'log_stats_label'):
            stats_text = f"📊 DEBUG:{self.log_stats['DEBUG']} | INFO:{self.log_stats['INFO']} | WARNING:{self.log_stats['WARNING']} | ERROR:{self.log_stats['ERROR']} | 總計:{self.log_stats['total']}"
            self.log_stats_label.config(text=stats_text)
    
    def get_log_level_icon(self, level):
        """獲取日誌級別圖標"""
        icons = {
            'DEBUG': '🔍',
            'INFO': 'ℹ️',
            'WARNING': '⚠️',
            'ERROR': '❌',
            'CRITICAL': '🚨'
        }
        return icons.get(level.upper(), 'ℹ️')
    
    def get_log_type_icon(self, logger_name):
        """獲取日誌類型圖標"""
        icons = {
            'GUI': '🖥️',
            'API': '🌐',
            'Validation': '✅',
            'Retry': '🔄'
        }
        return icons.get(logger_name, '📝')
    
    def retry_failed_from_csv(self):
        """從CSV文件載入並重測失敗問題"""
        # 選擇之前的驗證結果CSV文件
        from tkinter import filedialog, messagebox
        
        csv_file = filedialog.askopenfilename(
            title="選擇驗證結果CSV文件",
            filetypes=[
                ("CSV files", "*.csv"),
                ("All files", "*.*")
            ]
        )
        
        if not csv_file:
            return
        
        try:
            # 檢查API設定
            if not self.api_key.get():
                messagebox.showerror("錯誤", "請先在設定頁面中設定 API 金鑰")
                return
            
            # 檢查是否選擇了Chatbot
            selection = self.bot_listbox.curselection()
            if not selection:
                messagebox.showerror("錯誤", "請選擇聊天機器人")
                return
            
            self.selected_chatbot_id = self.chatbots[selection[0]]['id']
            
            # 載入CSV並識別失敗問題
            self.log_info(f"正在載入驗證結果文件: {csv_file}")
            failed_data = self.load_failed_questions_from_csv(csv_file)
            
            if not failed_data:
                messagebox.showinfo("資訊", "沒有發現需要重測的失敗問題")
                return
            
            # 確認重測
            result = messagebox.askyesno(
                "確認重測", 
                f"發現 {len(failed_data)} 個失敗問題需要重測。\n\n"
                f"這將會：\n"
                f"• 重新發送這些問題到AI助理\n"
                f"• 使用當前的驗證參數設定\n"
                f"• 覆蓋原始的失敗結果\n\n"
                f"是否繼續？"
            )
            
            if not result:
                return
            
            # 重設驗證狀態
            self.validation_stopped = False
            self.completed_questions = 0
            
            # 更新UI狀態
            self.retry_failed_button.config(state='disabled')
            self.start_button.config(state='disabled')
            self.stop_button.config(state='normal')
            self.progress_bar['value'] = 0
            self.progress_bar['maximum'] = len(failed_data)
            self.progress_label.config(text="正在重測失敗問題...")
            
            # 清空日誌
            self.log_text.config(state='normal')
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state='disabled')
            
            # 開始重測（傳遞原始CSV文件路徑用於整合）
            import threading
            self.original_csv_file = csv_file  # 保存原始CSV文件路徑
            threading.Thread(target=self.run_retry_validation, args=(failed_data, csv_file), daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("錯誤", f"載入失敗問題時發生錯誤：{str(e)}")
    
    def load_failed_questions_from_csv(self, csv_file):
        """從CSV文件中載入失敗的問題"""
        import pandas as pd
        
        try:
            # 讀取CSV文件（使用編碼檢測）
            df = self._read_csv_with_encoding_detection(csv_file)
            
            # 檢查必要欄位
            required_columns = ['編號', '提問者', 'AI助理回覆']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise ValueError(f"CSV文件缺少必要欄位: {', '.join(missing_columns)}")
            
            # 識別失敗問題
            failed_rows = []
            debug_info = []
            
            for _, row in df.iterrows():
                ai_reply = str(row.get('AI助理回覆', ''))
                row_id = str(row.get('編號', 'Unknown'))
                
                # 檢查是否為失敗問題（增強版）
                failure_reasons = []
                
                if ai_reply.startswith("錯誤:"):
                    failure_reasons.append("錯誤開頭")
                if ai_reply.startswith("重試失敗:"):
                    failure_reasons.append("重試失敗開頭")
                if "API 請求在" in ai_reply:
                    failure_reasons.append("API請求失敗")
                if "次重試後仍然失敗" in ai_reply:
                    failure_reasons.append("重試次數用盡")
                if ai_reply.strip() == "" or ai_reply.lower() == "nan" or pd.isna(row.get('AI助理回覆')):
                    failure_reasons.append("空回覆")
                if ai_reply == "未處理（驗證中斷）":
                    failure_reasons.append("驗證中斷")
                if "連接" in ai_reply and ("錯誤" in ai_reply or "失敗" in ai_reply):
                    failure_reasons.append("連接問題")
                if "逾時" in ai_reply or "timeout" in ai_reply.lower():
                    failure_reasons.append("逾時問題")
                if "伺服器" in ai_reply and "錯誤" in ai_reply:
                    failure_reasons.append("伺服器錯誤")
                
                is_failed = len(failure_reasons) > 0
                
                # 記錄調試信息
                debug_info.append({
                    '編號': row_id,
                    '提問者': str(row.get('提問者', '')),
                    'AI回覆前50字': ai_reply[:50] + ('...' if len(ai_reply) > 50 else ''),
                    '是否失敗': is_failed,
                    '失敗原因': ', '.join(failure_reasons) if failure_reasons else '無'
                })
                
                if is_failed:
                    # 查找問題描述欄位
                    question_column = None
                    for possible_name in ['問題描述', '對話內容', '問題內容', '內容']:
                        if possible_name in df.columns:
                            question_column = possible_name
                            break
                    
                    if not question_column:
                        self.log_warning(f"無法找到問題描述欄位，跳過問題 {row.get('編號', 'Unknown')}")
                        continue
                    
                    # 創建ValidationRow對象
                    validation_row = ValidationRow(
                        編號=str(row.get('編號', '')),
                        提問者=str(row.get('提問者', '')),
                        問題描述=str(row.get(question_column, '')),
                        建議_or_正確答案=str(row.get('建議 or 正確答案 (if have)', '')),
                        應參考的文件=str(row.get('應參考的文件', '')),
                        應參考的文件段落=str(row.get('應參考的文件段落', '')),
                        是否檢索KM推薦=str(row.get('是否檢索KM推薦', '是'))  # 默認為是，因為是失敗問題
                    )
                    
                    failed_rows.append(validation_row)
            
            # 輸出詳細的識別結果
            self.log_info(f"🔍 CSV失敗問題識別結果：")
            self.log_info(f"📊 總記錄數: {len(df)} 筆")
            self.log_info(f"❌ 識別出失敗問題: {len(failed_rows)} 個")
            self.log_info(f"✅ 成功問題: {len(df) - len(failed_rows)} 個")
            
            # 輸出每筆記錄的識別詳情
            self.log_info("📋 詳細識別結果：")
            for info in debug_info:
                status_icon = "❌" if info['是否失敗'] else "✅"
                self.log_info(f"{status_icon} {info['編號']} | {info['提問者']} | {info['失敗原因']} | {info['AI回覆前50字']}")
            
            self.log_info(f"🎯 總結：從 {len(df)} 筆記錄中識別出 {len(failed_rows)} 個失敗問題")
            
            # 顯示失敗問題的詳細信息
            if failed_rows:
                failed_users = {}
                for row in failed_rows:
                    user = row.提問者
                    if user not in failed_users:
                        failed_users[user] = 0
                    failed_users[user] += 1
                
                user_info = ', '.join([f"{user}({count}題)" for user, count in failed_users.items()])
                self.log_info(f"失敗問題分布: {user_info}")
            
            return failed_rows
            
        except Exception as e:
            self.log_error(f"載入CSV文件失敗: {str(e)}")
            raise
    
    def run_retry_validation(self, failed_data, original_csv_file):
        """執行重測驗證（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            self.log_info(f"開始重測 {len(failed_data)} 個失敗問題...")
            
            # 執行重測驗證
            results = loop.run_until_complete(self.process_retry_validation(failed_data))
            
            # 計算統計
            self.log_info("計算重測統計結果...")
            stats = self.calculate_retry_statistics(results)
            
            # 輸出整合結果（重測結果與原始CSV整合）
            import os
            import pandas as pd
            base_name = os.path.splitext(original_csv_file)[0]
            
            # 生成兩個文件：重測結果和整合結果
            retry_only_file = f"{base_name}_retry_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
            integrated_file = f"{base_name}_integrated_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            self.log_info(f"匯出重測結果到 CSV: {retry_only_file}")
            self.export_retry_results(results, retry_only_file, stats)
            
            self.log_info(f"整合重測結果與原始數據: {integrated_file}")
            self.export_integrated_results(results, original_csv_file, integrated_file, stats)
            
            # 更新 UI
            self.log_info("重測完成，更新結果顯示")
            self.root.after(0, lambda: self.show_retry_results(results, stats, retry_only_file, integrated_file))
            
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"重測過程發生錯誤：{error_msg}"))
        finally:
            # 重設 UI 狀態
            self.root.after(0, lambda: self.reset_retry_ui())
    
    async def process_retry_validation(self, failed_data):
        """處理重測驗證 - 專門用於重測失敗問題"""
        if not failed_data:
            return []
        
        self.log_info(f"開始重測 {len(failed_data)} 個失敗問題")
        
        # 按提問者分組
        user_groups = {}
        for row in failed_data:
            user = row.提問者
            if user not in user_groups:
                user_groups[user] = []
            user_groups[user].append(row)
        
        self.log_info(f"重測目標: {len(user_groups)} 個提問者")
        
        # 使用更保守的併發設定進行重測
        max_concurrent_users = max(1, self.max_concurrent.get() // 2)
        self.log_info(f"重測併發設定: {max_concurrent_users} 個提問者")
        
        # 創建進度追蹤鎖
        progress_lock = asyncio.Lock()
        
        # 創建結果字典
        results_dict = {}
        
        async with MaiAgentApiClient(self.api_base_url.get(), self.api_key.get(), self.api_logger_callback) as client:
            # 使用 Semaphore 控制併發數量
            semaphore = asyncio.Semaphore(max_concurrent_users)
            
            # 創建每個提問者的處理任務
            tasks = []
            for user, user_questions in user_groups.items():
                task = self.process_retry_user_questions(client, user, user_questions, semaphore, 
                                                       len(failed_data), progress_lock, results_dict)
                tasks.append(task)
            
            # 併發執行所有提問者的任務
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # 整理結果
        results = []
        for row in failed_data:
            if row.編號 in results_dict:
                results.append(results_dict[row.編號])
            else:
                # 未處理的問題，保持原狀
                row.AI助理回覆 = "重測未完成（可能被停止）"
                results.append(row)
        
        return results
    
    async def process_retry_user_questions(self, client, user, user_questions, semaphore, 
                                         total_questions, progress_lock, results_dict):
        """處理重測用戶問題"""
        async with semaphore:
            if self.validation_stopped:
                return
                
            self.log_info(f"🔄 開始重測提問者 '{user}' 的 {len(user_questions)} 個問題")
            
            for row in user_questions:
                if self.validation_stopped:
                    break
                    
                try:
                    # 使用更保守的設定處理問題
                    retry_delay = self.api_delay.get() * 2
                    retry_attempts = min(self.max_retries.get() + 3, 10)
                    
                    result = await self.process_single_question_with_retry(
                        client, row, retry_attempts, retry_delay)
                    
                    # 更新結果
                    async with progress_lock:
                        # 標記為重測成功
                        result._retry_info = "CSV重測成功"
                        results_dict[row.編號] = result
                        self.completed_questions += 1
                        
                        # 更新進度顯示
                        progress_msg = f"[重測-{user}] 完成問題 {row.編號} | 進度 {self.completed_questions}/{total_questions}"
                        self.root.after(0, lambda msg=progress_msg: self.update_progress(
                            self.completed_questions, total_questions, msg))
                    
                    self.log_validation_result(row.編號, True, 
                                             f"[重測-{user}] 成功，回覆長度: {len(result.AI助理回覆)} 字元")
                    
                except Exception as e:
                    self.log_error(f"重測提問者 '{user}' 的問題 {row.編號} 失敗: {str(e)}", 'Retry')
                    
                    # 標記為重測失敗
                    async with progress_lock:
                        row.AI助理回覆 = f"重測仍失敗: {str(e)}"
                        row.precision = 0.0
                        row.recall = 0.0
                        row.f1_score = 0.0
                        row.hit_rate = 0.0
                        row.引用節點是否命中 = "否"
                        row.參考文件是否正確 = "否"
                        row.回覆是否滿意 = "否"
                        
                        results_dict[row.編號] = row
                        self.completed_questions += 1
                        
                        progress_msg = f"[重測-{user}] 問題 {row.編號} 仍失敗 | 進度 {self.completed_questions}/{total_questions}"
                        self.root.after(0, lambda msg=progress_msg: self.update_progress(
                            self.completed_questions, total_questions, msg))
                
                # 重測間隔延遲
                if not self.validation_stopped:
                    await asyncio.sleep(retry_delay)
            
            self.log_info(f"🏁 提問者 '{user}' 的重測完成")
    
    def calculate_retry_statistics(self, results):
        """計算重測統計結果"""
        total_queries = len(results)
        if total_queries == 0:
            return {
                'total_retry_queries': 0,
                'retry_success_count': 0,
                'retry_failed_count': 0,
                'retry_success_rate': 0.0
            }
        
        retry_success_count = 0
        retry_failed_count = 0
        
        for row in results:
            if hasattr(row, 'AI助理回覆') and row.AI助理回覆:
                if (row.AI助理回覆.startswith("重測仍失敗:") or 
                    row.AI助理回覆 == "重測未完成（可能被停止）"):
                    retry_failed_count += 1
                else:
                    retry_success_count += 1
        
        return {
            'total_retry_queries': total_queries,
            'retry_success_count': retry_success_count,
            'retry_failed_count': retry_failed_count,
            'retry_success_rate': (retry_success_count / total_queries * 100) if total_queries > 0 else 0.0
        }
    
    def export_retry_results(self, results, output_file, stats):
        """輸出重測結果到 CSV"""
        import pandas as pd
        
        output_data = []
        
        try:
            for row in results:
                try:
                    # 基本信息
                    row_data = {
                        '編號': str(row.編號),
                        '提問者': str(row.提問者),
                        '問題描述': str(row.問題描述),
                        '建議 or 正確答案 (if have)': str(row.建議_or_正確答案),
                        '應參考的文件': str(row.應參考的文件),
                        '應參考的文件段落': str(row.應參考的文件段落),
                        '是否檢索KM推薦': str(row.是否檢索KM推薦),
                        'AI助理回覆': str(row.AI助理回覆),
                        '引用節點是否命中': str(row.引用節點是否命中),
                        '參考文件是否正確': str(row.參考文件是否正確),
                        '回覆是否滿意': str(row.回覆是否滿意),
                        # 重測標記
                        '重測狀態': '成功' if not (row.AI助理回覆.startswith("重測仍失敗:") or 
                                                  row.AI助理回覆 == "重測未完成（可能被停止）") else '失敗'
                    }
                    
                    output_data.append(row_data)
                    
                except Exception as e:
                    self.log_warning(f"輸出重測記錄失敗 [{row.編號 if hasattr(row, '編號') else 'Unknown'}]: {str(e)}")
                    continue
            
            # 創建 DataFrame 並寫入 CSV
            df = pd.DataFrame(output_data)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            
            self.log_info(f"重測結果已輸出到: {output_file}")
            self.log_info(f"重測統計: 成功 {stats['retry_success_count']} 題, 失敗 {stats['retry_failed_count']} 題")
            
        except Exception as e:
            self.log_error(f"輸出重測結果失敗: {str(e)}")
            raise
    
    def export_integrated_results(self, retry_results, original_csv_file, output_file, stats):
        """輸出整合結果到CSV（重測結果與原始數據整合）"""
        import pandas as pd
        
        try:
            # 讀取原始CSV文件
            self.log_info("讀取原始CSV文件...")
            original_df = self._read_csv_with_encoding_detection(original_csv_file)
            
            # 創建重測結果映射（以編號為鍵）
            retry_map = {}
            for row in retry_results:
                retry_map[str(row.編號)] = row
            
            # 整合數據
            integrated_data = []
            updated_count = 0
            
            for _, original_row in original_df.iterrows():
                row_id = str(original_row.get('編號', ''))
                
                # 檢查是否有重測結果
                if row_id in retry_map:
                    retry_row = retry_map[row_id]
                    updated_count += 1
                    
                    # 使用重測後的數據
                    row_data = {
                        '編號': str(retry_row.編號),
                        '提問者': str(retry_row.提問者),
                        '問題描述': str(retry_row.問題描述),
                        '建議 or 正確答案 (if have)': str(retry_row.建議_or_正確答案),
                        '應參考的文件': str(retry_row.應參考的文件),
                        '應參考的文件段落': str(retry_row.應參考的文件段落),
                        '是否檢索KM推薦': str(retry_row.是否檢索KM推薦),
                        'AI助理回覆': str(retry_row.AI助理回覆),
                        '引用節點是否命中': str(retry_row.引用節點是否命中),
                        '參考文件是否正確': str(retry_row.參考文件是否正確),
                        '回覆是否滿意': str(retry_row.回覆是否滿意),
                        '重測狀態': '重測成功' if not (retry_row.AI助理回覆.startswith("重測仍失敗:") or 
                                                  retry_row.AI助理回覆 == "重測未完成（可能被停止）") else '重測失敗'
                    }
                    
                    # 如果有RAG指標，也要更新
                    if hasattr(retry_row, 'Precision'):
                        row_data['Precision'] = getattr(retry_row, 'Precision', 0.0)
                        row_data['Recall'] = getattr(retry_row, 'Recall', 0.0)
                        row_data['F1-Score'] = getattr(retry_row, 'F1-Score', 0.0)
                        row_data['Hit Rate'] = getattr(retry_row, 'Hit Rate', 0.0)
                    
                else:
                    # 使用原始數據，但添加重測狀態標記
                    row_data = {}
                    for col in original_df.columns:
                        row_data[col] = str(original_row.get(col, ''))
                    
                    # 如果沒有重測狀態欄位，新增一個
                    if '重測狀態' not in row_data:
                        row_data['重測狀態'] = '未重測'
                
                integrated_data.append(row_data)
            
            # 創建 DataFrame 並寫入 CSV
            df = pd.DataFrame(integrated_data)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            
            self.log_info(f"✅ 整合結果已輸出到: {output_file}")
            self.log_info(f"📊 整合統計: 原始記錄 {len(original_df)} 筆, 重測更新 {updated_count} 筆")
            self.log_info(f"🔄 重測結果: 成功 {stats['retry_success_count']} 題, 失敗 {stats['retry_failed_count']} 題")
            
            return output_file
            
        except Exception as e:
            self.log_error(f"輸出整合結果失敗: {str(e)}")
            raise
    
    def show_retry_results(self, results, stats, retry_file, integrated_file=None):
        """顯示重測結果"""
        if hasattr(self, 'stats_text'):
            self.stats_text.config(state='normal')
            self.stats_text.delete(1.0, tk.END)
            
            # 根據是否有整合文件決定顯示內容
            if integrated_file:
                stats_str = f"""=== 重測驗證統計結果 ===
總重測問題數: {stats['total_retry_queries']}
重測成功數: {stats['retry_success_count']}
重測失敗數: {stats['retry_failed_count']}
重測成功率: {stats['retry_success_rate']:.2f}%

🔄 重測結果文件: {retry_file}
📋 整合完整文件: {integrated_file}
"""
            else:
                stats_str = f"""=== 重測驗證統計結果 ===
總重測問題數: {stats['total_retry_queries']}
重測成功數: {stats['retry_success_count']}
重測失敗數: {stats['retry_failed_count']}
重測成功率: {stats['retry_success_rate']:.2f}%

重測結果已輸出到: {retry_file}
"""
            
            self.stats_text.insert(1.0, stats_str)
            self.stats_text.config(state='disabled')
        
        # 顯示成功訊息
        if integrated_file:
            messagebox.showinfo(
                "重測完成", 
                f"重測完成！\n\n"
                f"總問題數: {stats['total_retry_queries']}\n"
                f"成功: {stats['retry_success_count']} 題\n"
                f"失敗: {stats['retry_failed_count']} 題\n"
                f"成功率: {stats['retry_success_rate']:.1f}%\n\n"
                f"🔄 重測結果文件: {retry_file}\n"
                f"📋 整合完整文件: {integrated_file}\n\n"
                f"整合文件包含所有原始記錄和重測更新！"
            )
        else:
            messagebox.showinfo(
                "重測完成", 
                f"重測完成！\n\n"
                f"總問題數: {stats['total_retry_queries']}\n"
                f"成功: {stats['retry_success_count']} 題\n"
                f"失敗: {stats['retry_failed_count']} 題\n"
                f"成功率: {stats['retry_success_rate']:.1f}%\n\n"
                f"結果已保存到: {retry_file}"
            )
    
    def reset_retry_ui(self):
        """重設重測UI狀態"""
        self.retry_failed_button.config(state='normal')
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.progress_label.config(text="重測完成")
    
    async def process_user_questions(self, client, user, user_questions, semaphore, total_questions, progress_lock, results_dict):
        """處理單個提問者的所有問題"""
        async with semaphore:  # 控制併發數量
            self.log_info(f"開始處理提問者 '{user}' 的 {len(user_questions)} 個問題")
            
            for i, row in enumerate(user_questions):
                # 檢查是否需要停止
                if self.validation_stopped:
                    self.log_warning(f"提問者 '{user}' 的處理已停止")
                    break
                
                try:
                    # 處理單個問題
                    result = await self.process_single_question(client, row)
                    
                    # 線程安全地更新結果和進度
                    async with progress_lock:
                        results_dict[row.編號] = result
                        self.completed_questions += 1
                        
                        # 更新進度顯示
                        progress_msg = f"[{user}] 完成問題 {row.編號} | 總進度 {self.completed_questions}/{total_questions}"
                        self.root.after(0, lambda msg=progress_msg: self.update_progress(self.completed_questions, total_questions, msg))
                    
                    # 記錄成功
                    self.log_validation_result(row.編號, True, f"[{user}] 回覆長度: {len(result.AI助理回覆)} 字元")
                    
                except Exception as e:
                    self.log_error(f"處理提問者 '{user}' 的問題 {row.編號} 時發生錯誤: {str(e)}", 'Validation')
                    # 即使出錯也要更新進度，並確保 row 具有所有必要的屬性
                    async with progress_lock:
                        row.AI助理回覆 = f"錯誤: {str(e)}"
                        
                        # 確保錯誤的 row 具有所有統計屬性
                        row.precision = 0.0
                        row.recall = 0.0
                        row.f1_score = 0.0
                        row.hit_rate = 0.0
                        row.引用節點是否命中 = "否"
                        row.參考文件是否正確 = "否"
                        row.回覆是否滿意 = "否"
                        
                        results_dict[row.編號] = row
                        self.completed_questions += 1
                        
                        progress_msg = f"[{user}] 處理問題 {row.編號} (錯誤) | 總進度 {self.completed_questions}/{total_questions}"
                        self.root.after(0, lambda msg=progress_msg: self.update_progress(self.completed_questions, total_questions, msg))
            
            self.log_info(f"提問者 '{user}' 處理完成")
        
    async def process_single_question(self, client, validation_row):
        """處理單個問題"""
        # 獲取或創建對話
        conversation_id = self.conversation_manager.get_conversation_id(validation_row.提問者)
        
        # 構建要發送的問題內容
        if conversation_id is None:
            # 這是新對話，檢查是否需要組合前面的問題
            if self.enable_context_combination.get():
                message_content = self.conversation_manager.build_context_message(
                    validation_row.提問者, 
                    validation_row.問題描述
                )
                
                # 記錄上下文構建情況
                previous_questions = self.conversation_manager.get_context_questions(validation_row.提問者)
                if previous_questions:
                    self.log_info(
                        f"提問者 '{validation_row.提問者}' 開始新對話，組合了 {len(previous_questions)} 個前面的問題", 
                        'Validation'
                    )
                else:
                    self.log_info(
                        f"提問者 '{validation_row.提問者}' 開始新對話，沒有前面的問題", 
                        'Validation'
                    )
            else:
                # 上下文組合已停用，直接使用當前問題
                message_content = validation_row.問題描述
                self.log_info(
                    f"提問者 '{validation_row.提問者}' 開始新對話（上下文組合已停用）", 
                    'Validation'
                )
        else:
            # 這是已存在對話的延續，直接使用當前問題
            message_content = validation_row.問題描述
            self.log_info(
                f"提問者 '{validation_row.提問者}' 繼續現有對話 {conversation_id}", 
                'Validation'
            )
        
        # 將當前問題添加到上下文中（用於後續問題）
        self.conversation_manager.add_question_to_context(validation_row.提問者, validation_row.問題描述)
        
        # 構建 query_metadata（如果啟用）
        query_metadata = None
        if self.enable_query_metadata.get() and self.knowledge_base_id.get().strip():
            knowledge_bases = [
                {
                    "knowledge_base_id": self.knowledge_base_id.get().strip(),
                    "has_user_selected_all": True
                }
            ]
            
            query_metadata = {
                "knowledge_bases": knowledge_bases
            }
            
            # 如果提供了標籤ID，添加標籤過濾
            if self.label_id.get().strip():
                query_metadata["label_relations"] = {
                    "operator": "OR",
                    "conditions": [
                        {"label_id": self.label_id.get().strip()}
                    ]
                }
            
            self.log_info(f"使用 Query Metadata: {query_metadata}", 'Validation')
        
        # 發送問題（使用重試機制）
        response = await client.send_message(
            self.selected_chatbot_id, 
            message_content,  # 使用構建的完整內容
            conversation_id,
            max_retries=self.max_retries.get(),
            query_metadata=query_metadata
        )
        
        # 更新對話 ID
        self.conversation_manager.set_conversation_id(validation_row.提問者, response.conversation_id)
        
        # 填入回覆結果
        validation_row.AI助理回覆 = response.content
        validation_row._raw_citation_nodes = response.citation_nodes
        validation_row._raw_citations = response.citations
        
        # 動態添加引用節點欄位
        self._add_citation_node_fields(validation_row, response.citation_nodes)
        
        # 動態添加參考文件欄位
        self._add_citation_file_fields(validation_row, response.citations)
        
        # 進行文字比對驗證（固定使用 RAG 增強模式）
        # 動態根據實際回傳的引用節點數量決定片段數
        actual_chunks_count = len(response.citation_nodes) if response.citation_nodes else 0
        
        citation_hit, rag_result = self.text_matcher.check_rag_enhanced_hit(
            response.citation_nodes, 
            validation_row.應參考的文件段落,
            self.similarity_threshold.get(),
            actual_chunks_count,  # 使用實際回傳的節點數量
            self.get_selected_separators(),  # 使用用戶選擇的分隔符
            self.similarity_mode.get()  # 使用用戶選擇的相似度計算模式
        )
        
        # 儲存詳細指標
        validation_row.precision = rag_result.get('precision', 0.0)
        validation_row.recall = rag_result.get('recall', 0.0)
        validation_row.f1_score = rag_result.get('f1_score', 0.0)
        validation_row.hit_rate = rag_result.get('hit_rate', 0.0)
        
        validation_row.引用節點是否命中 = "是" if citation_hit else "否"
        
        # 僅使用應參考文件UUID進行匹配
        expected_files = validation_row.應參考文件UUID.strip()
        
        if expected_files:
            file_match, file_stats = self.text_matcher.check_citation_file_match(
                response.citations,
                expected_files
            )
            validation_row.參考文件是否正確 = "是" if file_match else "否"
        else:
            # 如果沒有UUID，跳過文件匹配
            file_match = False
            file_stats = {
                "detail": "無UUID資料，跳過文件匹配",
                "total_expected": 0,
                "total_matched": 0,
                "hit_rate": 0.0,
                "matched_files": [],
                "unmatched_files": [],
                "all_matched": False
            }
            validation_row.參考文件是否正確 = "未檢測"
        
        # 儲存參考文件命中統計數據
        validation_row.參考文件命中率 = file_stats.get('hit_rate', 0.0)
        validation_row.期望文件總數 = file_stats.get('total_expected', 0)
        validation_row.命中文件數 = file_stats.get('total_matched', 0)
        
        # UUID格式的命中和未命中文件信息
        matched_files = file_stats.get('matched_files', [])
        validation_row.命中文件 = ', '.join(matched_files) if matched_files else ""
        
        unmatched_files = file_stats.get('unmatched_files', [])
        validation_row.未命中文件 = ', '.join(unmatched_files) if unmatched_files else ""
        
        # 回覆是否滿意保持空白，供客戶手動輸入
        # validation_row.回覆是否滿意 預設為空字串，不自動填寫
        
        # API 呼叫延遲（避免觸發限流）
        delay_time = self.api_delay.get()
        if delay_time > 0:
            await asyncio.sleep(delay_time)
                        
        return validation_row

    def _add_citation_node_fields(self, validation_row, citation_nodes):
        """動態添加引用節點欄位"""
        for i, node in enumerate(citation_nodes, 1):
            chinese_num = self.get_chinese_number(i)
            field_name = f'引用節點{chinese_num}'
            
            # 提取節點文本內容
            content = ""
            if 'chatbotTextNode' in node and 'text' in node['chatbotTextNode']:
                content = node['chatbotTextNode']['text']
            elif 'content' in node.get('chatbotTextNode', {}):
                content = node['chatbotTextNode']['content']
            elif 'text' in node:
                content = node['text']
            
            # 動態添加到 validation_row 物件
            setattr(validation_row, field_name, content)

    def _add_citation_file_fields(self, validation_row, citations):
        """動態添加參考文件欄位（使用文件UUID，過濾重複）"""
        # 收集所有文件UUID，自動過濾重複
        unique_file_ids = set()
        
        for citation in citations:
            file_id = citation.get('id', '').strip()
            if file_id:  # 只添加非空UUID
                unique_file_ids.add(file_id)
        
        # 將UUID轉換為排序的列表
        file_id_list = sorted(list(unique_file_ids))
        
        # 為每個文件UUID添加獨立欄位
        for i, file_id in enumerate(file_id_list, 1):
            chinese_num = self.get_chinese_number(i)
            field_name = f'參考文件{chinese_num}'
            setattr(validation_row, field_name, file_id)

    def calculate_statistics(self, results):
        """計算增強統計結果"""
        total_queries = len(results)
        if total_queries == 0:
            return {
                'total_queries': 0, 
                'citation_hit_rate': 0.0, 
                'file_match_rate': 0.0, 
                'top_10_hit_rate': 0.0,
                'avg_precision': 0.0,
                'avg_recall': 0.0,
                'avg_f1_score': 0.0,
                'avg_hit_rate': 0.0,
                'total_expected_segments': 0,
                'total_hit_segments': 0,
                'total_retrieved_chunks': 0,
                # 參考文件統計
                'avg_file_hit_rate': 0.0,
                'total_expected_files': 0,
                'total_matched_files': 0,
                'file_level_hit_rate': 0.0,
                # 重試統計
                'retry_success_count': 0,
                'retry_failed_count': 0,
                'original_failed_count': 0
            }
        
        # 基本統計
        citation_hits = sum(1 for row in results if row.引用節點是否命中 == "是")
        file_matches = sum(1 for row in results if row.參考文件是否正確 == "是")
        
        # RAG 增強統計
        total_precision = sum(row.precision for row in results)
        total_recall = sum(row.recall for row in results)
        total_f1_score = sum(row.f1_score for row in results)
        total_hit_rate = sum(row.hit_rate for row in results)
        
        # 計算段落級統計
        total_expected_segments = 0
        total_hit_segments = 0
        total_retrieved_chunks = 0
        total_relevant_chunks = 0
        
        for row in results:
            if row.應參考的文件段落:
                expected_segments = self.text_matcher.parse_expected_segments(row.應參考的文件段落)
                total_expected_segments += len(expected_segments)
                total_hit_segments += int(row.hit_rate * len(expected_segments))
                
                # 累計檢索相關統計（RAG 模式固定啟用）
                if row.precision > 0:
                    # 注：retrieved_chunks 數量在各個查詢中可能不同（動態調整）
                    # 這裡只記錄有效的精確度和召回率
                    pass
        
        # 計算參考文件統計
        total_expected_files = sum(row.期望文件總數 for row in results)
        total_matched_files = sum(row.命中文件數 for row in results)
        total_file_hit_rate = sum(row.參考文件命中率 for row in results)
        
        # 計算重試統計
        retry_success_count = 0
        retry_failed_count = 0
        original_failed_count = 0
        
        for row in results:
            if hasattr(row, 'AI助理回覆') and row.AI助理回覆:
                if row.AI助理回覆.startswith("錯誤:") or "API 請求在" in row.AI助理回覆:
                    original_failed_count += 1
                elif row.AI助理回覆.startswith("重試失敗:"):
                    retry_failed_count += 1
                elif "重試成功" in getattr(row, '_retry_info', ''):  # 如果有重試標記
                    retry_success_count += 1
        
        return {
            'total_queries': total_queries,
            'citation_hit_rate': citation_hits / total_queries * 100,
            'file_match_rate': file_matches / total_queries * 100,
            'top_10_hit_rate': citation_hits / total_queries * 100,  # 傳統計算
            'avg_precision': total_precision / total_queries * 100,
            'avg_recall': total_recall / total_queries * 100,
            'avg_f1_score': total_f1_score / total_queries * 100,
            'avg_hit_rate': total_hit_rate / total_queries * 100,  # 段落級命中率
            'segment_level_hit_rate': (total_hit_segments / total_expected_segments * 100) if total_expected_segments > 0 else 0.0,
            'total_expected_segments': total_expected_segments,
            'total_hit_segments': total_hit_segments,
            'total_retrieved_chunks': total_retrieved_chunks,
            # 新增參考文件統計
            'avg_file_hit_rate': total_file_hit_rate / total_queries * 100,
            'total_expected_files': total_expected_files,
            'total_matched_files': total_matched_files,
            'file_level_hit_rate': (total_matched_files / total_expected_files * 100) if total_expected_files > 0 else 0.0,
            # 重試統計
            'retry_success_count': retry_success_count,
            'retry_failed_count': retry_failed_count,
            'original_failed_count': original_failed_count,
            'rag_mode_enabled': True  # 固定啟用 RAG 模式
        }
        
    def export_results(self, results, output_file, stats):
        """輸出結果到 CSV（包含分割的段落欄位和動態引用節點/參考文件欄位）"""
        selected_separators = self.get_selected_separators()
        output_data = []
        failed_rows = 0
        
        try:
            # 先分析所有行，找出最大段落數量
            max_segments = 1
            for row in results:
                try:
                    segments = self.split_segments_for_export(row.應參考的文件段落, selected_separators)
                    max_segments = max(max_segments, len(segments))
                except Exception as e:
                    self.log_warning(f"分析段落失敗 [{row.編號}]: {str(e)}")
                    continue
            
            # 分析所有行，找出最大引用節點和參考文件數量
            max_citation_nodes = 0
            max_citation_files = 0
            
            for row in results:
                try:
                    # 計算引用節點數量
                    citation_count = 0
                    for i in range(1, 20):  # 假設最多不會超過20個
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'引用節點{chinese_num}'
                        if hasattr(row, field_name):
                            citation_count = i
                        else:
                            break
                    max_citation_nodes = max(max_citation_nodes, citation_count)
                    
                    # 計算參考文件數量
                    file_count = 0
                    for i in range(1, 20):  # 假設最多不會超過20個
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'參考文件{chinese_num}'
                        if hasattr(row, field_name):
                            file_count = i
                        else:
                            break
                    max_citation_files = max(max_citation_files, file_count)
                except Exception as e:
                    self.log_warning(f"分析引用節點失敗 [{row.編號}]: {str(e)}")
                    continue
            
            self.log_info(f"檢測到最大段落數量: {max_segments}，引用節點數量: {max_citation_nodes}，參考文件數量: {max_citation_files}")
            
            for row in results:
                try:
                    # 清理和安全化字符串內容
                    def safe_string(value):
                        if value is None:
                            return ''
                        str_value = str(value)
                        
                        # 按正確順序轉義特殊字符，避免重複轉義
                        str_value = str_value.replace('&', '&amp;')  # 首先處理 & 字符
                        str_value = str_value.replace('<', '&lt;')   # 轉義小於號（防止 XML 標籤錯誤）
                        str_value = str_value.replace('>', '&gt;')   # 轉義大於號
                        str_value = str_value.replace('"', '&quot;') # 轉義雙引號
                        
                        # 移除可能造成 CSV 問題的字符
                        str_value = str_value.replace('\r\n', '\n').replace('\r', '\n')
                        
                        # 限制超長內容
                        if len(str_value) > 32000:  # Excel 單元格限制
                            str_value = str_value[:32000] + "...(內容已截斷)"
                        return str_value
                    
                    # 基本欄位
                    row_data = {
                        '編號': safe_string(row.編號),
                        '提問者': safe_string(row.提問者),
                        '問題描述': safe_string(row.問題描述),
                        '是否檢索KM推薦': safe_string(row.是否檢索KM推薦),  # 新增欄位
                        'AI 助理回覆': safe_string(row.AI助理回覆),
                        '建議 or 正確答案 (if have)': safe_string(row.建議_or_正確答案),
                        '應參考的文件': safe_string(row.應參考的文件),
                        '應參考的文件段落(原始)': safe_string(row.應參考的文件段落),  # 保留原始完整內容
                        '引用節點是否命中': safe_string(row.引用節點是否命中),
                        '參考文件是否正確': safe_string(row.參考文件是否正確),
                        '回覆是否滿意': safe_string(row.回覆是否滿意),
                        # 參考文件詳細信息（不包含命中率）
                        '期望文件總數': str(row.期望文件總數),
                        '命中文件數': str(row.命中文件數),
                        '未命中文件': safe_string(row.未命中文件)
                    }
                    
                    # 添加動態引用節點欄位
                    for i in range(1, max_citation_nodes + 1):
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'引用節點{chinese_num}'
                        content = getattr(row, field_name, '') if hasattr(row, field_name) else ''
                        row_data[field_name] = safe_string(content)
                    
                    # 添加動態參考文件欄位
                    for i in range(1, max_citation_files + 1):
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'參考文件{chinese_num}'
                        content = getattr(row, field_name, '') if hasattr(row, field_name) else ''
                        row_data[field_name] = safe_string(content)
                    
                    # 分割段落並添加到獨立欄位
                    segments = self.split_segments_for_export(row.應參考的文件段落, selected_separators)
                    
                    for i in range(max_segments):
                        chinese_num = self.get_chinese_number(i + 1)
                        column_name = f'應參考的文件段落({chinese_num})'
                        
                        if i < len(segments):
                            row_data[column_name] = safe_string(segments[i])
                        else:
                            row_data[column_name] = ''  # 空欄位用於沒有那麼多段落的行
                    
                    output_data.append(row_data)
                    
                except Exception as e:
                    failed_rows += 1
                    self.log_error(f"處理驗證結果失敗 [{getattr(row, '編號', 'Unknown')}]: {str(e)}")
                    self.log_error(f"錯誤詳情: {type(e).__name__}")
                    continue
            
            # 確保輸出文件是 CSV 格式
            if not output_file.lower().endswith('.csv'):
                output_file = os.path.splitext(output_file)[0] + '.csv'
            
            # 輸出到 CSV
            df = pd.DataFrame(output_data)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')  # 使用 BOM 確保中文正確顯示
            self.output_file = output_file
            
            # 記錄分割統計
            self.log_info(f"已匯出 {len(output_data)} 筆記錄到 CSV 檔案，最多 {max_segments} 個段落")
            if failed_rows > 0:
                self.log_warning(f"跳過 {failed_rows} 筆有問題的記錄")
            self.log_info(f"使用的分隔符: {', '.join(selected_separators)}")
            self.log_info(f"輸出檔案: {output_file}")
            
        except Exception as e:
            self.log_error(f"匯出結果失敗: {str(e)}")
            self.log_error(f"錯誤類型: {type(e).__name__}")
            raise
    
    def export_excel(self, results, stats):
        """輸出結果到 Excel 格式"""
        try:
            if not hasattr(self, 'output_file') or not self.output_file:
                self.log_error("沒有可用的輸出檔案路徑")
                messagebox.showerror("錯誤", "沒有可用的輸出檔案路徑")
                return
            
            # 生成 Excel 檔案路徑
            csv_file = self.output_file
            excel_file = os.path.splitext(csv_file)[0] + '.xlsx'
            
            self.log_info(f"開始輸出 Excel 檔案: {excel_file}")
            
            selected_separators = self.get_selected_separators()
            output_data = []
            failed_rows = 0
            
            # 先分析所有行，找出最大段落數量
            max_segments = 1
            for row in results:
                try:
                    segments = self.split_segments_for_export(row.應參考的文件段落, selected_separators)
                    max_segments = max(max_segments, len(segments))
                except Exception as e:
                    self.log_warning(f"Excel 輸出 - 分析段落失敗 [{row.編號}]: {str(e)}")
                    continue
            
            # 分析所有行，找出最大引用節點和參考文件數量
            max_citation_nodes = 0
            max_citation_files = 0
            
            for row in results:
                try:
                    # 計算引用節點數量
                    citation_count = 0
                    for i in range(1, 20):
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'引用節點{chinese_num}'
                        if hasattr(row, field_name):
                            citation_count = i
                        else:
                            break
                    max_citation_nodes = max(max_citation_nodes, citation_count)
                    
                    # 計算參考文件數量
                    file_count = 0
                    for i in range(1, 20):
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'參考文件{chinese_num}'
                        if hasattr(row, field_name):
                            file_count = i
                        else:
                            break
                    max_citation_files = max(max_citation_files, file_count)
                except Exception as e:
                    self.log_warning(f"Excel 輸出 - 分析引用節點失敗 [{row.編號}]: {str(e)}")
                    continue
            
            for row in results:
                try:
                    # Excel 安全化字符串內容
                    def excel_safe_string(value):
                        if value is None:
                            return ''
                        str_value = str(value)
                        
                        # 按正確順序轉義特殊字符，避免重複轉義
                        str_value = str_value.replace('&', '&amp;')  # 首先處理 & 字符
                        str_value = str_value.replace('<', '&lt;')   # 轉義小於號（防止 XML 標籤錯誤）
                        str_value = str_value.replace('>', '&gt;')   # 轉義大於號
                        str_value = str_value.replace('"', '&quot;') # 轉義雙引號
                        
                        # 移除可能造成 Excel 問題的字符
                        str_value = str_value.replace('\r\n', '\n').replace('\r', '\n')
                        
                        # Excel 特殊字符處理
                        if str_value.startswith('='):
                            str_value = "'" + str_value  # 防止被解釋為公式
                        if str_value.startswith('+') or str_value.startswith('-') or str_value.startswith('@'):
                            str_value = "'" + str_value  # 防止被解釋為公式或指令
                        
                        # 限制超長內容
                        if len(str_value) > 32000:  # Excel 單元格限制
                            str_value = str_value[:32000] + "...(內容已截斷)"
                        return str_value
                    
                    # 基本欄位
                    row_data = {
                        '編號': excel_safe_string(row.編號),
                        '提問者': excel_safe_string(row.提問者),
                        '問題描述': excel_safe_string(row.問題描述),
                        '是否檢索KM推薦': excel_safe_string(row.是否檢索KM推薦),  # 新增欄位
                        'AI 助理回覆': excel_safe_string(row.AI助理回覆),
                        '建議 or 正確答案 (if have)': excel_safe_string(row.建議_or_正確答案),
                        '應參考的文件': excel_safe_string(row.應參考的文件),
                        '應參考的文件段落(原始)': excel_safe_string(row.應參考的文件段落),
                        '引用節點是否命中': excel_safe_string(row.引用節點是否命中),
                        '參考文件是否正確': excel_safe_string(row.參考文件是否正確),
                        '回覆是否滿意': excel_safe_string(row.回覆是否滿意)
                    }
                    
                    # 添加動態引用節點欄位
                    for i in range(1, max_citation_nodes + 1):
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'引用節點{chinese_num}'
                        content = getattr(row, field_name, '') if hasattr(row, field_name) else ''
                        row_data[field_name] = excel_safe_string(content)
                    
                    # 添加動態參考文件欄位
                    for i in range(1, max_citation_files + 1):
                        chinese_num = self.get_chinese_number(i)
                        field_name = f'參考文件{chinese_num}'
                        content = getattr(row, field_name, '') if hasattr(row, field_name) else ''
                        row_data[field_name] = excel_safe_string(content)
                    
                    # 分割段落並添加到獨立欄位
                    segments = self.split_segments_for_export(row.應參考的文件段落, selected_separators)
                    
                    for i in range(max_segments):
                        chinese_num = self.get_chinese_number(i + 1)
                        column_name = f'應參考的文件段落({chinese_num})'
                        
                        if i < len(segments):
                            row_data[column_name] = excel_safe_string(segments[i])
                        else:
                            row_data[column_name] = ''
                    
                    output_data.append(row_data)
                    
                except Exception as e:
                    failed_rows += 1
                    self.log_error(f"Excel 輸出 - 處理驗證結果失敗 [{getattr(row, '編號', 'Unknown')}]: {str(e)}")
                    continue
            
            # 輸出到 Excel
            df = pd.DataFrame(output_data)
            df.to_excel(excel_file, index=False, engine='openpyxl')
            
            # 記錄統計
            self.log_info(f"已輸出 {len(output_data)} 筆記錄到 Excel 檔案")
            if failed_rows > 0:
                self.log_warning(f"Excel 輸出時跳過 {failed_rows} 筆有問題的記錄")
            self.log_info(f"Excel 檔案: {excel_file}")
            
            messagebox.showinfo("成功", f"Excel 檔案已成功輸出到：\n{excel_file}")
            
        except Exception as e:
            error_msg = f"Excel 輸出失敗: {str(e)}"
            self.log_error(error_msg)
            self.log_error(f"錯誤類型: {type(e).__name__}")
            messagebox.showerror("Excel 輸出錯誤", error_msg)
    
    def export_to_excel(self):
        """觸發 Excel 輸出的按鈕回調"""
        if not hasattr(self, 'latest_results') or not self.latest_results:
            messagebox.showwarning("警告", "沒有可用的驗證結果數據，請先完成驗證")
            return
        
        if not hasattr(self, 'latest_stats') or not self.latest_stats:
            messagebox.showwarning("警告", "沒有可用的統計數據，請先完成驗證")
            return
        
        try:
            self.export_excel(self.latest_results, self.latest_stats)
        except Exception as e:
            error_msg = f"Excel 輸出過程發生錯誤：{str(e)}"
            self.log_error(error_msg)
            messagebox.showerror("Excel 輸出錯誤", error_msg)
        
    def show_results(self, results, stats, output_file):
        """顯示增強結果"""
        # 保存最新的結果數據，用於 Excel 輸出
        self.latest_results = results
        self.latest_stats = stats
        
        # 切換到結果頁面
        notebook = self.root.nametowidget(self.root.winfo_children()[0])
        notebook.select(2)  # 選擇結果頁面
        
        # 更新統計
        self.stats_text.config(state='normal')
        self.stats_text.delete(1.0, tk.END)
        
        if stats['rag_mode_enabled']:
            stats_str = f"""=== RAG 增強驗證統計結果 ===
總查詢數: {stats['total_queries']}
傳統 TOP 10 Hit Rate: {stats['top_10_hit_rate']:.2f}%
段落級命中率: {stats['segment_level_hit_rate']:.2f}%

=== RAG 詳細指標 ===
平均 Precision: {stats['avg_precision']:.2f}%
平均 Recall: {stats['avg_recall']:.2f}%
平均 F1-Score: {stats['avg_f1_score']:.2f}%

=== 段落級統計 ===
總預期段落數: {stats['total_expected_segments']}
命中段落數: {stats['total_hit_segments']}
總檢索塊數: {stats['total_retrieved_chunks']}

=== 文件匹配統計 ===
參考文件正確率: {stats['file_match_rate']:.2f}%
文件級整體命中率: {stats['file_level_hit_rate']:.2f}%
總期望文件數: {stats['total_expected_files']}
總命中文件數: {stats['total_matched_files']}

=== 重試處理統計 ===
重試成功問題數: {stats['retry_success_count']}
重試失敗問題數: {stats['retry_failed_count']}
原始失敗問題數: {stats['original_failed_count']}

結果已輸出到: {output_file}
"""
        else:
            stats_str = f"""=== 標準驗證統計結果 ===
總查詢數: {stats['total_queries']}
引用節點命中率: {stats['citation_hit_rate']:.2f}%
參考文件正確率: {stats['file_match_rate']:.2f}%
TOP 10 Hit Rate: {stats['top_10_hit_rate']:.2f}%

結果已輸出到: {output_file}
"""
        
        self.stats_text.insert(1.0, stats_str)
        self.stats_text.config(state='disabled')
        
        # 更新詳細結果
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
            
        for row in results:
            self.results_tree.insert('', 'end', values=(
                row.編號,
                row.提問者,
                row.問題描述[:50] + "..." if len(row.問題描述) > 50 else row.問題描述,
                row.AI助理回覆[:50] + "..." if len(row.AI助理回覆) > 50 else row.AI助理回覆,
                row.引用節點是否命中,
                row.參考文件是否正確
            ))
        
        self.output_file = output_file
        
    def update_progress(self, current, total, message):
        """更新進度"""
        self.progress_bar['value'] = current
        self.progress_label.config(text=f"{message} ({current}/{total})")
        
    def log_message(self, message, level='INFO', logger_name='GUI'):
        """超強化日誌記錄方法（完全安全版本 - 最大化遞歸保護）"""
        
        # 完全安全模式 - 在下載期間禁用所有日誌處理
        if getattr(self, '_download_in_progress', False):
            # 只使用最簡單的控制台輸出，避免任何複雜處理
            if level == 'ERROR':
                print(f"[SAFE-ERROR] {message}")
            return
        
        # 緊急保護 - 如果程序不穩定，立即停止日誌處理
        if getattr(self, '_emergency_throttle', False):
            return
        
        # 緊急限流 - 如果連續錯誤過多，直接禁用日誌
        if getattr(self, '_emergency_throttle', False):
            return
            
        # 防止遞歸調用和 GUI 關閉後的調用
        if not getattr(self, 'gui_running', True):
            return
            
        # 添加遞歸保護
        if getattr(self, '_in_log_message', False):
            # 連續錯誤計數
            self._consecutive_errors = getattr(self, '_consecutive_errors', 0) + 1
            if self._consecutive_errors > 5:
                self._emergency_throttle = True
            return
            
        # 激進的調用棧檢查
        try:
            import sys
            if len(sys._current_frames()) > 20:  # 如果有太多活躍線程
                return
        except:
            return
            
        # 日誌限流機制 - 更嚴格的控制
        import time
        current_time = time.time()
        
        # 檢查是否需要限流（更嚴格）
        if getattr(self, '_log_queue_size', 0) > getattr(self, '_max_concurrent_logs', 2):
            return  # 跳過此日誌，防止遞歸
        
        # 檢查時間間隔限流（更嚴格）
        if current_time - getattr(self, '_last_log_time', 0) < 0.05:  # 50ms 間隔
            return  # 跳過此日誌
        
        # 對API日誌進行特殊限制
        if logger_name == 'API' and getattr(self, '_log_queue_size', 0) > 1:
            return  # API日誌只允許1個並發
        
        try:
            self._in_log_message = True
            self._log_queue_size = getattr(self, '_log_queue_size', 0) + 1
            self._last_log_time = current_time
            
            # 重置連續錯誤計數
            self._consecutive_errors = 0
            
            # 選擇對應的日誌記錄器
            if logger_name == 'API':
                log_instance = self.api_logger
            elif logger_name == 'Validation':
                log_instance = self.validation_logger
            else:
                log_instance = self.gui_logger
            
            # 根據級別記錄到文件
            timestamp = pd.Timestamp.now().strftime('%H:%M:%S')
            formatted_message = f"[{timestamp}] {message}"
            
            if level.upper() == 'DEBUG':
                log_instance.debug(message)
            elif level.upper() == 'INFO':
                log_instance.info(message)
            elif level.upper() == 'WARNING':
                log_instance.warning(message)
            elif level.upper() == 'ERROR':
                log_instance.error(message)
            elif level.upper() == 'CRITICAL':
                log_instance.critical(message)
            
            # 更新 GUI 顯示（優化版）
            def update_log():
                if not self.gui_running:
                    return
                    
                try:
                    if not hasattr(self, 'log_text') or not self.log_text.winfo_exists():
                        return
                    
                    # 檢查日誌級別過濾
                    level_filter = getattr(self, 'log_level_var', None)
                    if level_filter and level_filter.get() != "ALL":
                        level_priority = {'DEBUG': 0, 'INFO': 1, 'WARNING': 2, 'ERROR': 3, 'CRITICAL': 4}
                        if level_priority.get(level.upper(), 1) < level_priority.get(level_filter.get(), 1):
                            return  # 跳過低級別日誌
                    
                    # 檢查日誌類型過濾
                    type_filter = getattr(self, 'log_type_var', None)
                    if type_filter and type_filter.get() != "ALL" and type_filter.get() != logger_name:
                        return  # 跳過不匹配的類型
                        
                    self.log_text.config(state='normal')
                    
                    # 創建優化的日誌格式
                    level_icon = self.get_log_level_icon(level)
                    type_icon = self.get_log_type_icon(logger_name)
                    timestamp = pd.Timestamp.now().strftime('%H:%M:%S.%f')[:-3]  # 包含毫秒
                    
                    # 格式化消息
                    formatted_line = f"[{timestamp}] {type_icon} {level_icon} {logger_name.upper():<10} | {message}\n"
                    
                    # 插入時間戳（灰色小字）
                    timestamp_start = self.log_text.index(tk.END + "-1c")
                    self.log_text.insert(tk.END, f"[{timestamp}] ")
                    timestamp_end = self.log_text.index(tk.END + "-1c")
                    self.log_text.tag_add('timestamp', timestamp_start, timestamp_end)
                    
                    # 插入類型圖標（彩色）
                    type_start = self.log_text.index(tk.END + "-1c")
                    self.log_text.insert(tk.END, f"{type_icon} ")
                    type_end = self.log_text.index(tk.END + "-1c")
                    self.log_text.tag_add(f'{logger_name.lower()}_tag', type_start, type_end)
                    
                    # 插入級別圖標和文字（根據級別著色）
                    level_start = self.log_text.index(tk.END + "-1c")
                    self.log_text.insert(tk.END, f"{level_icon} {logger_name.upper():<10} | {message}")
                    level_end = self.log_text.index(tk.END + "-1c")
                    self.log_text.tag_add(level.lower(), level_start, level_end)
                    
                    # 檢查搜索高亮
                    search_text = getattr(self, 'log_search_var', None)
                    if search_text and search_text.get():
                        search_term = search_text.get().lower()
                        if search_term in message.lower():
                            # 高亮搜索結果
                            line_start = timestamp_start
                            self.log_text.tag_add('search_highlight', line_start, level_end)
                    
                    self.log_text.insert(tk.END, "\n")
                    
                    # 更新統計
                    if hasattr(self, 'log_stats'):
                        self.log_stats[level.upper()] = self.log_stats.get(level.upper(), 0) + 1
                        self.log_stats['total'] = self.log_stats.get('total', 0) + 1
                        self.update_log_stats()
                    
                    # 限制日誌顯示行數（避免過多日誌影響效能）
                    line_count = int(self.log_text.index('end-1c').split('.')[0])
                    if line_count > 1500:  # 增加限制到1500行
                        self.log_text.delete('1.0', '750.0')  # 刪除前750行
                    
                    # 自動滾動（可控制）
                    if getattr(self, 'auto_scroll_var', None) and self.auto_scroll_var.get():
                        self.log_text.see(tk.END)
                    
                    self.log_text.config(state='disabled')
                except Exception as e:
                    # 防止日誌記錄本身出錯，使用靜默失敗
                    pass
            
            # 安全地更新 GUI
            if self.gui_running:
                try:
                    self.root.after(0, update_log)
                except Exception:
                    # 如果 GUI 更新失敗，靜默忽略
                    pass
                    
        except Exception:
            # 完全靜默的錯誤處理，避免任何可能的遞歸調用
            pass
        finally:
            self._in_log_message = False
            # 減少隊列大小
            self._log_queue_size = max(0, getattr(self, '_log_queue_size', 0) - 1)
            
            # 檢查是否需要重置限流狀態
            if self._log_queue_size == 0:
                self._log_throttle_active = False
                # 當沒有活躍日誌時，檢查是否可以重置緊急限流
                if getattr(self, '_emergency_throttle', False):
                    # 延遲重置緊急限流，給系統時間冷卻
                    import time
                    if time.time() - getattr(self, '_last_log_time', 0) > 5.0:  # 5秒冷卻期
                        self._emergency_throttle = False
                        self._consecutive_errors = 0
    
    def log_info(self, message, logger_name='GUI'):
        """記錄資訊級別日誌"""
        self.log_message(message, 'INFO', logger_name)
    
    def log_warning(self, message, logger_name='GUI'):
        """記錄警告級別日誌"""
        self.log_message(message, 'WARNING', logger_name)
    
    def log_error(self, message, logger_name='GUI'):
        """記錄錯誤級別日誌"""
        self.log_message(message, 'ERROR', logger_name)
    
    def log_debug(self, message, logger_name='GUI'):
        """記錄除錯級別日誌"""
        self.log_message(message, 'DEBUG', logger_name)
    
    def log_api_request(self, url, method, payload=None):
        """記錄 API 請求"""
        msg = f"API請求: {method} {url}"
        if payload:
            msg += f" | 載荷大小: {len(str(payload))} 字元"
        self.log_debug(msg, 'API')
    
    def log_api_response(self, url, status_code, response_size=0, duration=None):
        """記錄 API 回應"""
        msg = f"API回應: {url} | 狀態碼: {status_code} | 回應大小: {response_size} 字元"
        if duration:
            msg += f" | 耗時: {duration:.2f}秒"
        
        if status_code >= 400:
            self.log_error(msg, 'API')
        else:
            self.log_info(msg, 'API')
    
    def log_validation_result(self, question_id, success, details=None):
        """記錄驗證結果"""
        status = "成功" if success else "失敗"
        msg = f"驗證 {question_id}: {status}"
        if details:
            msg += f" | {details}"
        
        if success:
            self.log_info(msg, 'Validation')
        else:
            self.log_warning(msg, 'Validation')
    
    def clear_log_display(self):
        """清空日誌顯示"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        # 重置日誌統計
        if hasattr(self, 'log_stats'):
            self.log_stats = {
                'DEBUG': 0,
                'INFO': 0,
                'WARNING': 0,
                'ERROR': 0,
                'total': 0
            }
            self.update_log_stats()
        
        self.log_info("🗑️ 日誌顯示已清空")
    
    def export_logs(self):
        """匯出當前顯示的日誌"""
        try:
            log_content = self.log_text.get(1.0, tk.END)
            timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
            filename = f"gui_logs_export_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"=== MaiAgent 驗證工具日誌匯出 ===\n")
                f.write(f"匯出時間: {pd.Timestamp.now()}\n")
                f.write(f"{'='*50}\n\n")
                f.write(log_content)
            
            self.log_info(f"日誌已匯出到: {filename}")
            messagebox.showinfo("成功", f"日誌已匯出到: {filename}")
            return filename
        except Exception as e:
            self.log_error(f"日誌匯出失敗: {str(e)}")
            messagebox.showerror("錯誤", f"日誌匯出失敗: {str(e)}")
            return None
    
    def open_log_folder(self):
        """開啟日誌資料夾"""
        try:
            log_dir = Path("logs")
            if log_dir.exists():
                self._open_file_or_folder(str(log_dir))
                self.log_info("已開啟日誌資料夾")
            else:
                self.log_warning("日誌資料夾不存在")
                messagebox.showwarning("警告", "日誌資料夾不存在")
        except Exception as e:
            self.log_error(f"開啟日誌資料夾失敗: {str(e)}")
            messagebox.showerror("錯誤", f"開啟日誌資料夾失敗: {str(e)}")
    
    def on_log_level_changed(self, event=None):
        """處理日誌級別變更"""
        level = self.log_level_var.get()
        self.log_info(f"日誌顯示級別已變更為: {level}")
        
        # 這裡可以實現過濾功能（如果需要的話）
        # 目前保持所有日誌顯示，只是改變記錄級別
        
    def get_log_stats(self):
        """獲取日誌統計資訊"""
        try:
            log_dir = Path("logs")
            if not log_dir.exists():
                return "日誌資料夾不存在"
            
            log_files = list(log_dir.glob("*.log"))
            total_size = sum(f.stat().st_size for f in log_files if f.exists())
            
            stats = f"日誌檔案數量: {len(log_files)}\n"
            stats += f"總大小: {total_size / 1024:.2f} KB\n"
            stats += f"日誌資料夾: {log_dir.absolute()}"
            
            return stats
        except Exception as e:
            return f"獲取日誌統計失敗: {str(e)}"
    
    def show_log_stats(self):
        """顯示日誌統計視窗"""
        stats_window = tk.Toplevel(self.root)
        stats_window.title("日誌統計資訊")
        stats_window.geometry("600x400")
        stats_window.resizable(True, True)
        
        # 創建文字區域
        stats_text = scrolledtext.ScrolledText(stats_window, wrap=tk.WORD)
        stats_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 獲取並顯示統計資訊
        stats_info = self.get_log_stats()
        detailed_stats = f"""=== 日誌系統統計資訊 ===

{stats_info}

=== 日誌記錄器狀態 ===
GUI Logger: {self.gui_logger.name} (Level: {self.gui_logger.level})
API Logger: {self.api_logger.name} (Level: {self.api_logger.level})
Validation Logger: {self.validation_logger.name} (Level: {self.validation_logger.level})

=== 日誌處理器資訊 ===
"""
        
        # 添加處理器資訊
        root_logger = logging.getLogger()
        for i, handler in enumerate(root_logger.handlers):
            handler_type = type(handler).__name__
            if hasattr(handler, 'baseFilename'):
                handler_info = f"檔案: {handler.baseFilename}"
            else:
                handler_info = "控制台輸出"
            detailed_stats += f"處理器 {i+1}: {handler_type} - {handler_info}\n"
        
        detailed_stats += f"\n=== 當前顯示的日誌行數 ===\n"
        try:
            line_count = int(self.log_text.index('end-1c').split('.')[0]) - 1
            detailed_stats += f"GUI 日誌顯示行數: {line_count}\n"
        except:
            detailed_stats += "無法獲取 GUI 日誌行數\n"
        
        stats_text.insert(tk.END, detailed_stats)
        stats_text.config(state='disabled')
        
        # 添加按鈕
        button_frame = ttk.Frame(stats_window)
        button_frame.pack(fill='x', padx=10, pady=(0, 10))
        
        ttk.Button(button_frame, text="重新整理", 
                  command=lambda: self.refresh_log_stats(stats_text)).pack(side='left')
        ttk.Button(button_frame, text="關閉", 
                  command=stats_window.destroy).pack(side='right')
    
    def refresh_log_stats(self, stats_text):
        """重新整理日誌統計"""
        stats_text.config(state='normal')
        stats_text.delete(1.0, tk.END)
        
        # 重新獲取統計資訊
        stats_info = self.get_log_stats()
        detailed_stats = f"""=== 日誌系統統計資訊 ===

{stats_info}

=== 日誌記錄器狀態 ===
GUI Logger: {self.gui_logger.name} (Level: {self.gui_logger.level})
API Logger: {self.api_logger.name} (Level: {self.api_logger.level})
Validation Logger: {self.validation_logger.name} (Level: {self.validation_logger.level})

=== 日誌處理器資訊 ===
"""
        
        # 添加處理器資訊
        root_logger = logging.getLogger()
        for i, handler in enumerate(root_logger.handlers):
            handler_type = type(handler).__name__
            if hasattr(handler, 'baseFilename'):
                handler_info = f"檔案: {handler.baseFilename}"
            else:
                handler_info = "控制台輸出"
            detailed_stats += f"處理器 {i+1}: {handler_type} - {handler_info}\n"
        
        detailed_stats += f"\n=== 當前顯示的日誌行數 ===\n"
        try:
            line_count = int(self.log_text.index('end-1c').split('.')[0]) - 1
            detailed_stats += f"GUI 日誌顯示行數: {line_count}\n"
        except:
            detailed_stats += "無法獲取 GUI 日誌行數\n"
            
        detailed_stats += f"\n更新時間: {pd.Timestamp.now()}"
        
        stats_text.insert(tk.END, detailed_stats)
        stats_text.config(state='disabled')
    
    def show_about(self):
        """顯示關於程式的對話框"""
        about_window = tk.Toplevel(self.root)
        about_window.title("關於程式")
        about_window.geometry("500x400")
        about_window.resizable(False, False)
        
        # 設定視窗居中
        about_window.transient(self.root)
        about_window.grab_set()
        
        main_frame = ttk.Frame(about_window, padding=20)
        main_frame.pack(fill='both', expand=True)
        
        # 應用程式標題
        title_label = ttk.Label(main_frame, text=__app_name__, 
                               font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 5))
        
        # 版本信息
        version_label = ttk.Label(main_frame, text=f"版本 {__version__}", 
                                 font=('Arial', 12))
        version_label.pack(pady=(0, 10))
        
        # 描述
        desc_label = ttk.Label(main_frame, text=__description__, 
                              font=('Arial', 10), 
                              wraplength=400, justify='center')
        desc_label.pack(pady=(0, 15))
        
        # 詳細信息框
        info_frame = ttk.LabelFrame(main_frame, text="詳細信息", padding=10)
        info_frame.pack(fill='both', expand=True, pady=(0, 15))
        
        info_text = tk.Text(info_frame, height=12, wrap=tk.WORD, 
                           font=('Consolas', 9), state='normal')
        info_text.pack(fill='both', expand=True)
        
        # 獲取系統信息
        import platform
        import sys
        
        system_info = f"""版本信息:
  應用程式名稱: {__app_name__}
  版本號: {__version__}
  建置日期: {__build_date__}
  作者: {__author__}

系統環境:
  Python 版本: {sys.version}
  作業系統: {platform.system()} {platform.release()}
  架構: {platform.machine()}
  處理器: {platform.processor()}

核心功能:
  • GUI 圖形化操作界面
  • RAG 增強統計分析
  • 多級別日誌記錄系統
  • 批次驗證處理
  • 詳細統計報告
  • API 自動重試機制
  • 多種輸出格式支援

組織管理功能:
  • 組織成員匯出功能
  • 帳號批量匯入自動化
  • 群組權限配置管理
  • Excel/CSV 格式數據處理
  • 完整的組織架構管理

知識庫管理功能:
  • 知識庫文件列表管理
  • 批量文件下載匯出
  • 文件選擇與篩選
  • 進度追蹤與日誌記錄
  • 靈活的匯出目錄配置

技術支援:
  如有問題或建議，請聯繫 MaiAgent Team
  
版權聲明:
  Copyright © 2025 MaiAgent Team
  保留所有權利
"""
        
        info_text.insert(tk.END, system_info)
        info_text.config(state='disabled')
        
        # 按鈕框
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x')
        
        # 複製信息按鈕
        def copy_info():
            try:
                about_window.clipboard_clear()
                about_window.update()  # 強制更新剪貼板
                about_window.clipboard_append(system_info)
                about_window.update()  # 再次強制更新
                self.log_info("系統信息已複製到剪貼板")
                messagebox.showinfo("成功", "系統信息已複製到剪貼板")
            except Exception as e:
                self.log_error(f"複製操作失敗: {str(e)}")
                messagebox.showerror("錯誤", f"複製失敗: {str(e)}")
        
        ttk.Button(button_frame, text="複製信息", command=copy_info).pack(side='left')
        ttk.Button(button_frame, text="關閉", command=about_window.destroy).pack(side='right')
    
    def get_selected_separators(self) -> List[str]:
        """獲取用戶選擇的分隔符"""
        selected = []
        for sep_key, var in self.separator_vars.items():
            if var.get():
                selected.append(sep_key)
        
        # 如果沒有選擇任何分隔符，使用預設
        if not selected:
            selected = ['---', '|||', '\n\n']
            self.log_warning("未選擇任何分隔符，使用預設分隔符")
        
        return selected
    
    def test_separators(self):
        """測試分隔符功能"""
        selected_separators = self.get_selected_separators()
        
        # 創建測試視窗
        test_window = tk.Toplevel(self.root)
        test_window.title("分隔符測試")
        test_window.geometry("600x500")
        test_window.resizable(True, True)
        
        main_frame = ttk.Frame(test_window, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        # 輸入區域
        input_frame = ttk.LabelFrame(main_frame, text="測試文本", padding=10)
        input_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        ttk.Label(input_frame, text="請輸入包含分隔符的測試文本：").pack(anchor='w')
        
        input_text = scrolledtext.ScrolledText(input_frame, height=8, wrap=tk.WORD)
        input_text.pack(fill='both', expand=True, pady=(5, 0))
        
        # 預設測試文本
        sample_text = """第一個段落內容---第二個段落內容|||第三個段落內容

第四個段落（雙換行分隔）

第五個段落###第六個段落===第七個段落...第八個段落"""
        input_text.insert(tk.END, sample_text)
        
        # 結果區域
        result_frame = ttk.LabelFrame(main_frame, text="分割結果", padding=10)
        result_frame.pack(fill='both', expand=True)
        
        result_text = scrolledtext.ScrolledText(result_frame, height=8, wrap=tk.WORD, state='disabled')
        result_text.pack(fill='both', expand=True, pady=(5, 0))
        
        # 控制按鈕
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', pady=(10, 0))
        
        def run_test():
            test_content = input_text.get(1.0, tk.END).strip()
            if not test_content:
                messagebox.showwarning("警告", "請輸入測試文本")
                return
            
            try:
                segments = self.text_matcher.parse_expected_segments(test_content, selected_separators)
                
                result_text.config(state='normal')
                result_text.delete(1.0, tk.END)
                
                result_content = f"使用的分隔符: {', '.join(selected_separators)}\n"
                result_content += f"分割結果 (共 {len(segments)} 個段落):\n"
                result_content += "=" * 50 + "\n\n"
                
                for i, segment in enumerate(segments, 1):
                    result_content += f"段落 {i}:\n{segment}\n\n"
                    result_content += "-" * 30 + "\n\n"
                
                result_text.insert(tk.END, result_content)
                result_text.config(state='disabled')
                
                self.log_info(f"分隔符測試完成，共分割出 {len(segments)} 個段落")
                
            except Exception as e:
                messagebox.showerror("錯誤", f"測試失敗: {str(e)}")
                self.log_error(f"分隔符測試失敗: {str(e)}")
        
        ttk.Button(button_frame, text="執行測試", command=run_test).pack(side='left')
        ttk.Button(button_frame, text="清空輸入", command=lambda: input_text.delete(1.0, tk.END)).pack(side='left', padx=(10, 0))
        ttk.Button(button_frame, text="關閉", command=test_window.destroy).pack(side='right')
        
        # 立即執行一次測試
        run_test()
    
    def reset_separators(self):
        """重設分隔符為預設值"""
        # 重設所有選項
        for sep_key, var in self.separator_vars.items():
            if sep_key in ['---', '|||', '\n\n']:
                var.set(True)
            else:
                var.set(False)
        
        self.log_info("分隔符已重設為預設值")
        messagebox.showinfo("成功", "分隔符已重設為預設值 (---, |||, \\n\\n)")
    
    def get_chinese_number(self, num: int) -> str:
        """將數字轉換為中文數字"""
        chinese_nums = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
                       '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十']
        if num < len(chinese_nums):
            return chinese_nums[num]
        else:
            return str(num)  # 超過20個段落時使用阿拉伯數字
    
    def split_segments_for_export(self, original_content: str, selected_separators: List[str]) -> List[str]:
        """為匯出功能分割段落"""
        if not original_content:
            return ['']
        
        segments = self.text_matcher.parse_expected_segments(original_content, selected_separators)
        return segments if segments else [original_content]
        
    def reset_validation_ui(self):
        """重設驗證 UI 狀態"""
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.progress_label.config(text="驗證完成")
        
    def open_results_file(self):
        """開啟結果文件"""
        if hasattr(self, 'output_file') and os.path.exists(self.output_file):
            self._open_file_or_folder(self.output_file)
        else:
            messagebox.showwarning("警告", "結果文件不存在")
            
    def open_results_folder(self):
        """開啟結果資料夾"""
        folder = os.path.dirname(os.path.abspath(self.output_file)) if hasattr(self, 'output_file') else os.getcwd()
        self._open_file_or_folder(folder)
    
    def _open_file_or_folder(self, path):
        """跨平台開啟檔案或資料夾"""
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":  # macOS
                subprocess.call(["open", path])
            elif system == "Linux":
                subprocess.call(["xdg-open", path])
            else:
                self.log_warning(f"不支援的作業系統: {system}")
                messagebox.showwarning("警告", f"無法在 {system} 系統上自動開啟檔案")
        except Exception as e:
            self.log_error(f"開啟檔案失敗: {str(e)}")
            messagebox.showerror("錯誤", f"開啟檔案失敗: {str(e)}")
        
    def load_config(self):
        """載入配置"""
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read('config.ini', encoding='utf-8')
            
            if 'api' in config:
                self.api_base_url.set(config['api'].get('base_url', 'http://localhost:8000'))
                self.api_key.set(config['api'].get('api_key', ''))
            
            if 'validation' in config:
                self.similarity_threshold.set(config['validation'].getfloat('similarity_threshold', 0.3))
                # 兼容舊的設定檔案
                max_concurrent = 5  # 預設值
                if 'max_concurrent_users' in config['validation']:
                    max_concurrent = config['validation'].getint('max_concurrent_users')
                elif 'max_concurrent_requests' in config['validation']:
                    max_concurrent = config['validation'].getint('max_concurrent_requests')
                self.max_concurrent.set(max_concurrent)
                # 載入 API 延遲設定
                self.api_delay.set(config['validation'].getfloat('api_delay', 1.0))
                # 載入重試次數設定
                self.max_retries.set(config['validation'].getint('max_retries', 3))
                # RAG 模式固定啟用，不從配置文件讀取
                # top_k 動態調整，不從配置文件讀取
            
            # 載入組織匯出設定
            if 'organization_export' in config:
                self.org_export_base_url.set(config['organization_export'].get('base_url', 'https://api.maiagent.ai/api/v1/'))
                self.org_export_api_key.set(config['organization_export'].get('api_key', ''))
            
            # 載入部署設定
            if 'deployment' in config:
                self.deploy_base_url.set(config['deployment'].get('base_url', 'http://localhost:8000/api/v1/'))
                self.deploy_api_key.set(config['deployment'].get('api_key', ''))
                self.deploy_org_name.set(config['deployment'].get('organization_name', ''))
                self.deploy_create_users.set(config['deployment'].getboolean('create_users', False))
                self.deploy_referral_code.set(config['deployment'].get('referral_code', ''))
            
            # 載入知識庫管理設定
            if 'knowledge_base' in config:
                self.kb_base_url.set(config['knowledge_base'].get('base_url', 'http://localhost:8000/api/v1/'))
                self.kb_api_key.set(config['knowledge_base'].get('api_key', ''))
                self.kb_export_dir.set(config['knowledge_base'].get('export_dir', ''))
                self.concurrent_downloads.set(config['knowledge_base'].getint('concurrent_downloads', 1))
                # 載入載入模式設置
                if hasattr(self, 'load_all_at_once'):
                    load_all = config['knowledge_base'].getboolean('load_all_at_once', True)
                    self.load_all_at_once.set(load_all)
            
            # 載入 query_metadata 設定
            if 'query_metadata' in config:
                self.enable_query_metadata.set(config['query_metadata'].getboolean('enable', False))
                self.knowledge_base_id.set(config['query_metadata'].get('knowledge_base_id', ''))
                self.label_id.set(config['query_metadata'].get('label_id', ''))
                # 更新 UI 狀態
                self.on_query_metadata_toggle()
            
            # 載入上下文組合設定
            if 'context' in config:
                self.enable_context_combination.set(config['context'].getboolean('enable_combination', True))
            
            # 載入分隔符設定
            if 'separators' in config:
                # 建立分隔符別名映射（與保存時相同）
                separator_aliases = {
                    '---': 'hyphen_triple',
                    '|||': 'pipe_triple', 
                    '\n\n': 'newline_double',
                    '###': 'hash_triple',
                    '===': 'equal_triple',
                    '...': 'dot_triple'
                }
                
                separator_section = config['separators']
                for sep_key in self.separator_vars:
                    alias = separator_aliases.get(sep_key, sep_key)
                    # 從配置文件讀取，如果不存在則使用當前值
                    saved_value = separator_section.getboolean(alias, self.separator_vars[sep_key].get())
                    self.separator_vars[sep_key].set(saved_value)
                
                self.log_info(f"分隔符設定已載入: {self.get_selected_separators()}")
            
            # 更新推薦碼輸入框狀態
            self.on_create_users_changed()
                
            messagebox.showinfo("成功", "配置載入成功")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"載入配置失敗: {str(e)}")
            
    def save_config(self):
        """儲存配置"""
        try:
            import configparser
            config = configparser.ConfigParser()
            
            config['api'] = {
                'base_url': self.api_base_url.get(),
                'api_key': self.api_key.get()
            }
            
            config['validation'] = {
                'similarity_threshold': str(self.similarity_threshold.get()),
                'max_concurrent_users': str(self.max_concurrent.get()),
                'api_delay': str(self.api_delay.get()),  # API 呼叫延遲時間
                'max_retries': str(self.max_retries.get()),  # API 請求重試次數
                'enable_rag_mode': 'True',  # 固定啟用 RAG 模式
                'top_k': 'dynamic'  # 動態調整
            }
            
            # 組織匯出設定
            config['organization_export'] = {
                'base_url': self.org_export_base_url.get(),
                'api_key': self.org_export_api_key.get()
            }
            
            # 部署設定
            config['deployment'] = {
                'base_url': self.deploy_base_url.get(),
                'api_key': self.deploy_api_key.get(),
                'organization_name': self.deploy_org_name.get(),
                'create_users': str(self.deploy_create_users.get()),
                'referral_code': self.deploy_referral_code.get()
            }
            
            # 知識庫管理設定
            config['knowledge_base'] = {
                'base_url': self.kb_base_url.get(),
                'api_key': self.kb_api_key.get(),
                'export_dir': self.kb_export_dir.get(),
                'concurrent_downloads': str(self.concurrent_downloads.get()),
                'load_all_at_once': str(getattr(self, 'load_all_at_once', tk.BooleanVar(value=True)).get())
            }
            
            # 保存 query_metadata 設定
            config['query_metadata'] = {
                'enable': str(self.enable_query_metadata.get()),
                'knowledge_base_id': self.knowledge_base_id.get(),
                'label_id': self.label_id.get()
            }
            
            # 保存上下文組合設定
            config['context'] = {
                'enable_combination': str(self.enable_context_combination.get())
            }
            
            # 保存分隔符設定
            # 建立分隔符別名映射
            separator_aliases = {
                '---': 'hyphen_triple',
                '|||': 'pipe_triple', 
                '\n\n': 'newline_double',
                '###': 'hash_triple',
                '===': 'equal_triple',
                '...': 'dot_triple'
            }
            
            config['separators'] = {}
            for sep_key, var in self.separator_vars.items():
                alias = separator_aliases.get(sep_key, sep_key)
                config['separators'][alias] = str(var.get())
            
            with open('config.ini', 'w', encoding='utf-8') as f:
                config.write(f)
                
            self.log_info(f"分隔符設定已保存: {self.get_selected_separators()}")
            messagebox.showinfo("成功", "配置儲存成功")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存配置失敗: {str(e)}")
    
    def create_organization_tab(self, notebook):
        """創建組織管理標籤頁"""
        org_frame = ttk.Frame(notebook)
        notebook.add(org_frame, text="組織管理")
        
        # 創建子筆記本
        org_notebook = ttk.Notebook(org_frame)
        org_notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # 組織匯出子頁面
        self.create_export_tab(org_notebook)
        
        # 帳號批量匯入子頁面
        self.create_deployment_tab(org_notebook)
        
        # 知識庫管理子頁面
        self.create_knowledge_base_tab(org_notebook)
    
    def create_export_tab(self, notebook):
        """創建組織匯出標籤頁"""
        export_frame = ttk.Frame(notebook)
        notebook.add(export_frame, text="組織匯出")
        
        main_frame = ttk.Frame(export_frame)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # API 設定
        api_frame = ttk.LabelFrame(main_frame, text="API 設定", padding=10)
        api_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(api_frame, text="API 基礎 URL：").pack(anchor='w')
        ttk.Entry(api_frame, textvariable=self.org_export_base_url, width=60).pack(fill='x', pady=(5, 10))
        
        ttk.Label(api_frame, text="API 金鑰：").pack(anchor='w')
        ttk.Entry(api_frame, textvariable=self.org_export_api_key, width=60, show="*").pack(fill='x', pady=(5, 0))
        
        # 組織選擇
        org_frame = ttk.LabelFrame(main_frame, text="組織選擇", padding=10)
        org_frame.pack(fill='x', pady=(0, 10))
        
        self.export_org_listbox = tk.Listbox(org_frame, height=5)
        self.export_org_listbox.pack(fill='x', pady=(0, 10))
        
        org_button_frame = ttk.Frame(org_frame)
        org_button_frame.pack(fill='x')
        
        ttk.Button(org_button_frame, text="載入組織列表", command=self.load_export_organizations).pack(side='left')
        ttk.Button(org_button_frame, text="測試連接", command=self.test_export_connection).pack(side='left', padx=(10, 0))
        
        # 匯出控制
        export_control_frame = ttk.LabelFrame(main_frame, text="匯出控制", padding=10)
        export_control_frame.pack(fill='x', pady=(0, 10))
        
        self.export_button = ttk.Button(export_control_frame, text="開始匯出", command=self.start_export)
        self.export_button.pack(side='left')
        
        # 匯出日誌
        export_log_frame = ttk.LabelFrame(main_frame, text="匯出日誌", padding=10)
        export_log_frame.pack(fill='both', expand=True)
        
        self.export_log_text = scrolledtext.ScrolledText(export_log_frame, height=10, state='disabled')
        self.export_log_text.pack(fill='both', expand=True)
    
    def create_deployment_tab(self, notebook):
        """創建帳號批量匯入標籤頁"""
        deploy_frame = ttk.Frame(notebook)
        notebook.add(deploy_frame, text="帳號批量匯入")
        
        main_frame = ttk.Frame(deploy_frame)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # CSV 文件選擇
        csv_frame = ttk.LabelFrame(main_frame, text="CSV 文件", padding=10)
        csv_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(csv_frame, text="選擇 CSV 文件：").pack(anchor='w')
        csv_path_frame = ttk.Frame(csv_frame)
        csv_path_frame.pack(fill='x', pady=(5, 0))
        
        ttk.Entry(csv_path_frame, textvariable=self.deploy_csv_file, width=60).pack(side='left', fill='x', expand=True)
        ttk.Button(csv_path_frame, text="瀏覽", command=self.browse_deploy_csv).pack(side='right', padx=(5, 0))
        
        # API 設定
        deploy_api_frame = ttk.LabelFrame(main_frame, text="目標環境 API 設定", padding=10)
        deploy_api_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(deploy_api_frame, text="API 基礎 URL：").pack(anchor='w')
        ttk.Entry(deploy_api_frame, textvariable=self.deploy_base_url, width=60).pack(fill='x', pady=(5, 10))
        
        ttk.Label(deploy_api_frame, text="API 金鑰：").pack(anchor='w')
        ttk.Entry(deploy_api_frame, textvariable=self.deploy_api_key, width=60, show="*").pack(fill='x', pady=(5, 0))
        
        # 匯入選項
        deploy_options_frame = ttk.LabelFrame(main_frame, text="匯入選項", padding=10)
        deploy_options_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(deploy_options_frame, text="組織名稱（選填）：").pack(anchor='w')
        ttk.Entry(deploy_options_frame, textvariable=self.deploy_org_name, width=60).pack(fill='x', pady=(5, 10))
        
        user_frame = ttk.Frame(deploy_options_frame)
        user_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Checkbutton(user_frame, text="創建用戶帳號", variable=self.deploy_create_users, 
                       command=self.on_create_users_changed).pack(side='left')
        
        ttk.Label(deploy_options_frame, text="推薦碼（創建用戶時需要）：").pack(anchor='w')
        self.deploy_referral_entry = ttk.Entry(deploy_options_frame, textvariable=self.deploy_referral_code, 
                                              width=60, state='disabled')
        self.deploy_referral_entry.pack(fill='x', pady=(5, 0))
        
        # 匯入控制
        deploy_control_frame = ttk.LabelFrame(main_frame, text="匯入控制", padding=10)
        deploy_control_frame.pack(fill='x', pady=(0, 10))
        
        self.deploy_button = ttk.Button(deploy_control_frame, text="開始匯入", command=self.start_deployment)
        self.deploy_button.pack(side='left')
        
        # 匯入日誌
        deploy_log_frame = ttk.LabelFrame(main_frame, text="匯入日誌", padding=10)
        deploy_log_frame.pack(fill='both', expand=True)
        
        self.deploy_log_text = scrolledtext.ScrolledText(deploy_log_frame, height=10, state='disabled')
        self.deploy_log_text.pack(fill='both', expand=True)
    
    def create_knowledge_base_tab(self, notebook):
        """創建知識庫管理標籤頁"""
        kb_frame = ttk.Frame(notebook)
        notebook.add(kb_frame, text="🗃️ 知識庫管理")
        
        # 分割為左右兩個區域
        paned_window = ttk.PanedWindow(kb_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 左側面板：配置和操作
        left_frame = ttk.Frame(paned_window)
        paned_window.add(left_frame, weight=1)
        
        # 知識庫連接配置
        config_frame = ttk.LabelFrame(left_frame, text="🔗 知識庫連接配置", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # API 配置
        ttk.Label(config_frame, text="API 基礎 URL:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        kb_base_url_entry = ttk.Entry(config_frame, textvariable=self.kb_base_url, width=40)
        kb_base_url_entry.grid(row=0, column=1, sticky=tk.W+tk.E, padx=(0, 5))
        
        # 添加URL格式說明
        url_help = ttk.Label(config_frame, text="格式: https://api.maiagent.ai/api 或 http://localhost:8000/api", 
                            font=('TkDefaultFont', 8), foreground='gray')
        url_help.grid(row=0, column=2, sticky=tk.W, padx=(5, 0))
        
        ttk.Label(config_frame, text="API 金鑰:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        kb_api_key_entry = ttk.Entry(config_frame, textvariable=self.kb_api_key, width=40, show="*")
        kb_api_key_entry.grid(row=1, column=1, sticky=tk.W+tk.E, padx=(0, 5), pady=(5, 0))
        
        config_frame.columnconfigure(1, weight=1)
        config_frame.columnconfigure(2, weight=0)  # URL說明欄位不需要擴展
        
        # 連接測試和知識庫載入
        action_frame = ttk.Frame(config_frame)
        action_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0), sticky=tk.W+tk.E)
        
        self.kb_test_button = ttk.Button(action_frame, text="🧪 測試連接", command=self.test_kb_connection)
        self.kb_test_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.kb_load_button = ttk.Button(action_frame, text="📋 載入知識庫", command=self.load_knowledge_bases)
        self.kb_load_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 知識庫選擇
        kb_select_frame = ttk.LabelFrame(left_frame, text="📚 選擇知識庫", padding=10)
        kb_select_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 創建容器來正確佈局listbox和滑動條
        kb_container = ttk.Frame(kb_select_frame)
        kb_container.pack(fill=tk.BOTH, expand=True)
        
        # 先創建滑動條（右側）
        kb_scroll = ttk.Scrollbar(kb_container, orient=tk.VERTICAL)
        kb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 再創建listbox（填滿剩餘空間）
        self.kb_listbox = tk.Listbox(kb_container, height=6, yscrollcommand=kb_scroll.set)
        self.kb_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.kb_listbox.bind('<<ListboxSelect>>', self.on_kb_selection_changed)
        
        # 配置滑動條命令
        kb_scroll.config(command=self.kb_listbox.yview)
        
        # 檔案載入進度條
        kb_progress_frame = ttk.Frame(kb_select_frame)
        kb_progress_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(kb_progress_frame, text="檔案載入進度:").pack(side=tk.LEFT, padx=(0, 5))
        self.kb_files_progress = ttk.Progressbar(kb_progress_frame, mode='determinate', maximum=100)
        self.kb_files_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 進度標籤
        self.kb_progress_label = ttk.Label(kb_progress_frame, text="0/0", width=10)
        self.kb_progress_label.pack(side=tk.RIGHT)
        
        # 檔案上傳區域
        upload_frame = ttk.LabelFrame(left_frame, text="📁 檔案上傳", padding=10)
        upload_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 檔案選擇
        file_select_frame = ttk.Frame(upload_frame)
        file_select_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(file_select_frame, text="選擇檔案:").pack(side=tk.LEFT, padx=(0, 5))
        self.upload_file_var = tk.StringVar()
        upload_file_entry = ttk.Entry(file_select_frame, textvariable=self.upload_file_var, state="readonly")
        upload_file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_file_button = ttk.Button(file_select_frame, text="瀏覽...", command=self.browse_upload_file)
        browse_file_button.pack(side=tk.RIGHT)
        
        # 上傳按鈕
        upload_button_frame = ttk.Frame(upload_frame)
        upload_button_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.upload_start_button = ttk.Button(upload_button_frame, text="📤 開始上傳", 
                                            command=self.start_file_upload, state=tk.DISABLED)
        self.upload_start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        # 上傳進度
        self.upload_progress = ttk.Progressbar(upload_button_frame, mode='indeterminate')
        self.upload_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
        
        # 檔案匯出
        export_frame = ttk.LabelFrame(left_frame, text="💾 檔案匯出", padding=10)
        export_frame.pack(fill=tk.BOTH, expand=True)
        
        # 匯出目錄
        export_dir_frame = ttk.Frame(export_frame)
        export_dir_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(export_dir_frame, text="匯出目錄:").pack(side=tk.LEFT, padx=(0, 5))
        # 如果沒有設定匯出目錄，使用預設值
        if not self.kb_export_dir.get():
            self.kb_export_dir.set(os.path.join(os.getcwd(), "exports"))
        export_dir_entry = ttk.Entry(export_dir_frame, textvariable=self.kb_export_dir, state="readonly")
        export_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        browse_dir_button = ttk.Button(export_dir_frame, text="瀏覽...", command=self.browse_export_directory)
        browse_dir_button.pack(side=tk.RIGHT)
        
        # 匯出控制
        export_control_frame = ttk.Frame(export_frame)
        export_control_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.select_all_button = ttk.Button(export_control_frame, text="✅ 全選", 
                                          command=self.select_all_files, state=tk.DISABLED)
        self.select_all_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.deselect_all_button = ttk.Button(export_control_frame, text="❌ 取消全選", 
                                            command=self.deselect_all_files, state=tk.DISABLED)
        self.deselect_all_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.kb_export_button = ttk.Button(export_control_frame, text="📂 匯出選中檔案", 
                                         command=self.start_kb_export, state=tk.DISABLED)
        self.kb_export_button.pack(side=tk.RIGHT)
        
        # 並發下載配置
        concurrent_frame = ttk.Frame(export_frame)
        concurrent_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(concurrent_frame, text="並發下載數:").pack(side=tk.LEFT, padx=(0, 5))
        self.concurrent_downloads = tk.IntVar(value=1)  # 固定為 1，完全避免並發
        concurrent_spinbox = ttk.Spinbox(concurrent_frame, from_=1, to=10, width=5, 
                                       textvariable=self.concurrent_downloads)
        concurrent_spinbox.pack(side=tk.LEFT, padx=(0, 10))
        
        # 添加說明
        ttk.Label(concurrent_frame, text="(1-10，數值越高下載越快但可能增加服務器負擔)", 
                 font=('TkDefaultFont', 8), foreground='gray').pack(side=tk.LEFT)
        
        # 載入方式選擇
        load_mode_frame = ttk.Frame(export_frame)
        load_mode_frame.pack(fill=tk.X, pady=(5, 0))
        
        self.load_all_at_once = tk.BooleanVar(value=True)
        ttk.Checkbutton(load_mode_frame, text="📦 一次性載入所有文件（減少API調用，推薦）", 
                       variable=self.load_all_at_once,
                       command=self.on_load_mode_changed).pack(side=tk.LEFT)
        
        # 檔案匯出進度條
        export_progress_frame = ttk.Frame(export_frame)
        export_progress_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Label(export_progress_frame, text="檔案匯出進度:").pack(side=tk.LEFT, padx=(0, 5))
        self.kb_export_progress = ttk.Progressbar(export_progress_frame, mode='determinate', maximum=100)
        self.kb_export_progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        # 匯出進度標籤
        self.kb_export_progress_label = ttk.Label(export_progress_frame, text="0/0", width=10)
        self.kb_export_progress_label.pack(side=tk.RIGHT)
        
        # 右側面板：檔案列表和日誌
        right_frame = ttk.Frame(paned_window)
        paned_window.add(right_frame, weight=2)
        
        # 分割為上下兩個區域
        right_paned = ttk.PanedWindow(right_frame, orient=tk.VERTICAL)
        right_paned.pack(fill=tk.BOTH, expand=True)
        
        # 檔案列表
        files_frame = ttk.LabelFrame(right_paned, text="📄 知識庫檔案", padding=5)
        right_paned.add(files_frame, weight=2)
        
        # 檔案列表容器
        files_container = ttk.Frame(files_frame)
        files_container.pack(fill=tk.BOTH, expand=True)
        
        # 創建Treeview顯示檔案
        columns = ("檔案名稱", "大小", "狀態", "創建時間")
        self.files_tree = ttk.Treeview(files_container, columns=columns, show="tree headings", height=15)
        
        # 設定欄位
        self.files_tree.heading("#0", text="☑", anchor=tk.W)
        self.files_tree.column("#0", width=30, minwidth=30)
        
        for col in columns:
            self.files_tree.heading(col, text=col, anchor=tk.W)
            if col == "檔案名稱":
                self.files_tree.column(col, width=200, minwidth=150)
            elif col == "大小":
                self.files_tree.column(col, width=80, minwidth=60)
            elif col == "狀態":
                self.files_tree.column(col, width=80, minwidth=60)
            else:  # 創建時間
                self.files_tree.column(col, width=150, minwidth=120)
        
        self.files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 檔案列表滾動條
        files_scrollbar = ttk.Scrollbar(files_container, orient=tk.VERTICAL, command=self.files_tree.yview)
        files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.files_tree.config(yscrollcommand=files_scrollbar.set)
        
        # 綁定雙擊事件
        self.files_tree.bind("<Double-1>", self.toggle_file_selection)
        
        # 日誌區域
        log_frame = ttk.LabelFrame(right_paned, text="📋 操作日誌", padding=5)
        right_paned.add(log_frame, weight=1)
        
        # 日誌文本框
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.kb_log_text = tk.Text(log_container, height=8, wrap=tk.WORD)
        self.kb_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        kb_log_scrollbar = ttk.Scrollbar(log_container, orient=tk.VERTICAL, command=self.kb_log_text.yview)
        kb_log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.kb_log_text.config(yscrollcommand=kb_log_scrollbar.set)
        
        # 初始化變量
        self.current_kb_id = None
        self.kb_files_data = []
        self.upload_thread = None
        self.selected_files = set()
        self.file_info_map = {}
        self.knowledge_bases = []
    
    # === 組織管理功能方法 ===
    
    def browse_deploy_csv(self):
        """瀏覽選擇部署用 CSV 文件"""
        file_path = filedialog.askopenfilename(
            title="選擇組織成員 CSV 文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.deploy_csv_file.set(file_path)
    
    def on_create_users_changed(self):
        """用戶創建選項變更處理"""
        if self.deploy_create_users.get():
            self.deploy_referral_entry.config(state='normal')
        else:
            self.deploy_referral_entry.config(state='disabled')
    
    def test_export_connection(self):
        """測試組織匯出 API 連接"""
        if not self.org_export_api_key.get():
            messagebox.showerror("錯誤", "請輸入 API 金鑰")
            return
            
        def test_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def test():
                    async with MaiAgentApiClient(self.org_export_base_url.get(), 
                                               self.org_export_api_key.get(), 
                                               None) as client:
                        organizations = await client.get_organizations()
                        return len(organizations)
                
                count = loop.run_until_complete(test())
                loop.close()
                
                self.root.after(0, lambda: messagebox.showinfo("成功", f"連接成功！找到 {count} 個組織"))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"連接失敗：{error_msg}"))
        
        threading.Thread(target=test_async, daemon=True).start()
    
    def load_export_organizations(self):
        """載入組織列表"""
        if not self.org_export_api_key.get():
            messagebox.showerror("錯誤", "請先輸入 API 金鑰")
            return
        
        def load_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def fetch():
                    async with MaiAgentApiClient(self.org_export_base_url.get(), 
                                               self.org_export_api_key.get(), 
                                               None) as client:
                        return await client.get_organizations()
                
                orgs = loop.run_until_complete(fetch())
                loop.close()
                
                self.root.after(0, lambda: self.update_export_organization_list(orgs))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入失敗：{error_msg}"))
        
        threading.Thread(target=load_async, daemon=True).start()
    
    def update_export_organization_list(self, organizations):
        """更新匯出組織列表"""
        self.export_org_listbox.delete(0, tk.END)
        self.export_organizations = organizations
        
        for org in organizations:
            if isinstance(org, dict):
                name = org.get('name', 'Unknown')
                org_id = org.get('id', 'Unknown')
                self.export_org_listbox.insert(tk.END, f"{name} (ID: {org_id})")
        
        self.log_info(f"載入了 {len(organizations)} 個組織")
    
    def start_export(self):
        """開始組織匯出"""
        selection = self.export_org_listbox.curselection()
        if not selection:
            messagebox.showerror("錯誤", "請選擇要匯出的組織")
            return
        
        if not self.org_export_api_key.get():
            messagebox.showerror("錯誤", "請輸入 API 金鑰")
            return
        
        selected_org = self.export_organizations[selection[0]]
        self.selected_export_org_id = selected_org['id']
        
        self.export_button.config(state='disabled')
        
        threading.Thread(target=self.run_export, daemon=True).start()
    
    def run_export(self):
        """執行組織匯出（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(self.export_organization_data())
            loop.close()
            
            if success:
                self.root.after(0, self.export_completed)
            else:
                self.root.after(0, lambda: self.export_failed("匯出過程中發生錯誤"))
                
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self.export_failed(error_msg))
    
    async def export_organization_data(self):
        """匯出組織數據"""
        try:
            async with MaiAgentApiClient(self.org_export_base_url.get(), 
                                       self.org_export_api_key.get(), 
                                       None) as client:
                
                # 獲取權限列表
                self.log_export("🔐 正在獲取權限列表...")
                permissions = await client.get_permissions()
                self.log_export(f"✅ 找到 {len(permissions)} 個權限配置")
                
                # 創建權限映射
                permission_id_to_name = {}
                for perm in permissions:
                    if isinstance(perm, dict) and 'id' in perm and 'name' in perm:
                        permission_id_to_name[str(perm['id'])] = perm['name']
                
                # 獲取組織成員
                self.log_export("👥 正在獲取組織成員...")
                members = await client.get_organization_members(self.selected_export_org_id)
                self.log_export(f"✅ 找到 {len(members)} 個成員")
                
                # 獲取組織群組
                self.log_export("🏢 正在獲取組織群組...")
                groups = await client.get_organization_groups(self.selected_export_org_id)
                self.log_export(f"✅ 找到 {len(groups)} 個群組")
                
                # 獲取群組成員信息
                group_members_map = {}
                for group in groups:
                    if isinstance(group, dict) and 'id' in group:
                        group_id = group['id']
                        if isinstance(group_id, (str, int)):
                            group_id_str = str(group_id)
                            group_name = group.get('name', 'Unknown')

                            try:
                                self.log_export(f"📋 正在獲取群組 {group_name} 的成員列表...")
                                group_members = await client.get_group_members(self.selected_export_org_id, group_id_str)
                                group_members_map[group_id_str] = group_members
                                self.log_export(f"🔍 群組 {group_name} (ID: {group_id}) 有 {len(group_members)} 個成員")
                            except Exception as e:
                                self.log_export(f"⚠️ 獲取群組 {group_name} 成員失敗: {str(e)}")
                                group_members_map[group_id_str] = []
                
                # 處理群組權限
                group_permissions_map = {}
                for group in groups:
                    if isinstance(group, dict) and 'id' in group and 'permissions' in group:
                        group_id_str = str(group['id'])
                        group_name = group.get('name', 'Unknown')
                        group_permissions = group.get('permissions', [])
                        
                        permission_names = []
                        for perm in group_permissions:
                            if isinstance(perm, dict) and 'id' in perm:
                                perm_id = str(perm['id'])
                                if perm_id in permission_id_to_name:
                                    permission_names.append(permission_id_to_name[perm_id])
                                    self.log_export(f"✅ 群組 {group_name} 權限: {permission_id_to_name[perm_id]}")
                            elif isinstance(perm, (str, int)):
                                perm_id = str(perm)
                                if perm_id in permission_id_to_name:
                                    permission_names.append(permission_id_to_name[perm_id])
                                    self.log_export(f"✅ 群組 {group_name} 權限: {permission_id_to_name[perm_id]}")
                        
                        group_permissions_map[group_id_str] = permission_names
                
                # 生成 Excel
                org_name = None
                for org in self.export_organizations:
                    if org['id'] == self.selected_export_org_id:
                        org_name = org['name']
                        break
                
                if not org_name:
                    org_name = "Unknown"
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                excel_filename = f"organization_members_{org_name}_{timestamp}.xlsx"
                
                self.log_export(f"📄 正在生成 Excel 文件: {excel_filename}")
                
                # 收集所有成員數據
                member_data_list = []
                
                for member in members:
                        if not isinstance(member, dict):
                            continue
                        
                        member_id = member.get('id')
                        member_name = member.get('name', 'Unknown')
                        member_email = member.get('email', '')
                        is_owner = member.get('is_owner', False)
                        created_at = member.get('created_at', '')
                        
                        if not isinstance(member_id, (str, int)):
                            continue
                        
                        member_id_str = str(member_id)
                        
                        # 查找成員所屬群組
                        member_groups = []
                        member_group_permissions = []
                        
                        for group_id, group_members in group_members_map.items():
                            if not isinstance(group_members, list):
                                continue
                            
                            for gm in group_members:
                                if isinstance(gm, dict):
                                    if 'member' in gm:
                                        member_data = gm['member']
                                        gm_id = member_data.get('id')
                                    elif 'id' in gm:
                                        gm_id = gm['id']
                                    else:
                                        continue
                                    
                                    if isinstance(gm_id, (str, int)) and str(gm_id) == member_id_str:
                                        # 找到對應群組
                                        for group in groups:
                                            if isinstance(group, dict) and str(group['id']) == group_id:
                                                group_name = group.get('name', 'Unknown')
                                                member_groups.append(group_name)
                                                
                                                # 添加群組權限
                                                if group_id in group_permissions_map:
                                                    permissions = group_permissions_map[group_id]
                                                    if permissions:
                                                        perm_str = f"{group_name}({', '.join(permissions)})"
                                                    else:
                                                        perm_str = f"{group_name}(無權限)"
                                                    member_group_permissions.append(perm_str)
                                                break
                                        break
                        
                        # 收集成員數據
                        member_data_list.append({
                            '成員 ID': member_id_str,
                            '姓名': member_name,
                            '電子郵件': member_email,
                            '是否為擁有者': '是' if is_owner else '否',
                            '建立時間': created_at,
                            '所屬群組': '; '.join(member_groups),
                            '群組權限配置': '; '.join(member_group_permissions)
                        })
                
                # 生成 Excel 文件
                if member_data_list:
                    df = pd.DataFrame(member_data_list)
                    df.to_excel(excel_filename, index=False, engine='openpyxl')
                    self.log_export(f"✅ Excel 文件生成完成: {excel_filename}")
                else:
                    self.log_export("⚠️ 無成員數據可匯出")
                
                return True
                
        except Exception as e:
            self.log_export(f"❌ 匯出失敗: {str(e)}")
            return False
    
    def export_completed(self):
        """匯出完成"""
        self.export_button.config(state='normal')
        messagebox.showinfo("匯出完成", "組織成員匯出已成功完成！")
        self.log_info("組織匯出完成", 'Organization')
    
    def export_failed(self, error_message):
        """匯出失敗"""
        self.export_button.config(state='normal')
        messagebox.showerror("匯出失敗", f"匯出過程發生錯誤：{error_message}")
        self.log_error(f"組織匯出失敗: {error_message}", 'Organization')
    
    def log_export(self, message):
        """記錄匯出日誌"""
        self.root.after(0, lambda: self._update_export_log(message))
    
    def _update_export_log(self, message):
        """更新匯出日誌顯示"""
        self.export_log_text.config(state='normal')
        self.export_log_text.insert(tk.END, f"{message}\n")
        self.export_log_text.see(tk.END)
        self.export_log_text.config(state='disabled')
    
    # === 帳號批量匯入功能 ===
    
    def start_deployment(self):
        """開始帳號批量匯入"""
        # 檢查設定
        if not self.deploy_csv_file.get():
            messagebox.showerror("錯誤", "請選擇部署文件 (CSV)")
            return
            
        if not self.deploy_api_key.get():
            messagebox.showerror("錯誤", "請輸入 API 金鑰")
            return
        
        self.deploy_button.config(state='disabled')
        
        threading.Thread(target=self.run_deployment, daemon=True).start()
    
    def run_deployment(self):
        """執行批量匯入（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(self.execute_batch_import())
            loop.close()
            
            if success:
                self.root.after(0, self.deployment_completed)
            else:
                self.root.after(0, lambda: self.deployment_failed("匯入過程中發生錯誤"))
                
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, lambda: self.deployment_failed(error_msg))
    
    async def execute_batch_import(self):
        """執行批量匯入邏輯"""
        try:
            async with MaiAgentApiClient(self.deploy_base_url.get(), 
                                       self.deploy_api_key.get(), 
                                       None) as client:
                
                referral_code = self.deploy_referral_code.get() if self.deploy_create_users.get() else None
                processor = BatchImportProcessor(client, self.deploy_csv_file.get(), referral_code)
                
                return await processor.execute_import(
                    organization_name=self.deploy_org_name.get() or None,
                    create_users=self.deploy_create_users.get(),
                    log_callback=self.log_deploy
                )
                
        except Exception as e:
            self.log_deploy(f"❌ 批量匯入執行失敗: {str(e)}")
            return False
    
    def deployment_completed(self):
        """匯入完成"""
        self.deploy_button.config(state='normal')
        messagebox.showinfo("匯入完成", "帳號批量匯入已成功完成！")
        self.log_info("帳號批量匯入完成", 'Deployment')
    
    def deployment_failed(self, error_message):
        """匯入失敗"""
        self.deploy_button.config(state='normal')
        messagebox.showerror("匯入失敗", f"匯入過程發生錯誤：{error_message}")
        self.log_error(f"帳號批量匯入失敗: {error_message}", 'Deployment')
    
    def log_deploy(self, message):
        """記錄匯入日誌"""
        self.root.after(0, lambda: self._update_deploy_log(message))
    
    def _update_deploy_log(self, message):
        """更新匯入日誌顯示"""
        self.deploy_log_text.config(state='normal')
        self.deploy_log_text.insert(tk.END, f"{message}\n")
        self.deploy_log_text.see(tk.END)
        self.deploy_log_text.config(state='disabled')
    
    # === 知識庫管理功能 ===
    
    def browse_export_directory(self):
        """瀏覽選擇匯出目錄"""
        directory = filedialog.askdirectory(title="選擇匯出目錄")
        if directory:
            self.kb_export_dir.set(directory)
    
    def test_kb_connection(self):
        """測試知識庫 API 連接"""
        # 獲取API配置
        base_url = self.kb_base_url.get().strip()
        api_key = self.kb_api_key.get().strip()
        
        # 詳細的調試信息
        self.log_kb(f"🔍 測試連接 - 基礎URL: {base_url}")
        self.log_kb(f"🔍 測試連接 - API金鑰長度: {len(api_key)} 字符")
        self.log_kb(f"🔍 測試連接 - API金鑰前綴: {api_key[:10]}..." if len(api_key) > 10 else f"🔍 測試連接 - API金鑰: {api_key}")
        
        if not base_url:
            messagebox.showerror("錯誤", "請輸入 API 基礎 URL")
            self.log_kb("❌ 測試失敗 - 未輸入基礎URL")
            return
            
        if not api_key:
            messagebox.showerror("錯誤", "請輸入 API 金鑰")
            self.log_kb("❌ 測試失敗 - 未輸入API金鑰")
            return
            
        def test_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                self.root.after(0, lambda: self.log_kb("🚀 開始測試API連接..."))
                
                async def test():
                    async with MaiAgentApiClient(base_url, api_key, None) as client:
                        self.root.after(0, lambda: self.log_kb("📡 正在呼叫 get_knowledge_bases API..."))
                        knowledge_bases = await client.get_knowledge_bases()
                        self.root.after(0, lambda: self.log_kb(f"📋 API回應: 找到 {len(knowledge_bases)} 個知識庫"))
                        return len(knowledge_bases)
                
                count = loop.run_until_complete(test())
                loop.close()
                
                self.root.after(0, lambda: self.log_kb(f"✅ 連接測試成功！共 {count} 個知識庫"))
                self.root.after(0, lambda: messagebox.showinfo("成功", f"連接成功！找到 {count} 個知識庫"))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.log_kb(f"❌ 連接測試失敗: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"連接失敗：{error_msg}"))
        
        threading.Thread(target=test_async, daemon=True).start()
    
    def load_knowledge_bases(self):
        """載入知識庫列表"""
        # 獲取API配置
        base_url = self.kb_base_url.get().strip()
        api_key = self.kb_api_key.get().strip()
        
        if not base_url:
            messagebox.showerror("錯誤", "請先輸入 API 基礎 URL")
            self.log_kb("❌ 載入失敗 - 未輸入基礎URL")
            return
            
        if not api_key:
            messagebox.showerror("錯誤", "請先輸入 API 金鑰")
            self.log_kb("❌ 載入失敗 - 未輸入API金鑰")
            return
        
        def load_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                self.root.after(0, lambda: self.log_kb("🔄 正在載入知識庫列表..."))
                
                async def fetch():
                    async with MaiAgentApiClient(base_url, api_key, None) as client:
                        knowledge_bases = await client.get_knowledge_bases()
                        self.root.after(0, lambda: self.log_kb(f"📋 成功獲取 {len(knowledge_bases)} 個知識庫"))
                        return knowledge_bases
                
                knowledge_bases = loop.run_until_complete(fetch())
                loop.close()
                
                self.root.after(0, lambda: self.update_knowledge_base_list(knowledge_bases))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.log_kb(f"❌ 載入知識庫失敗: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入知識庫失敗：{error_msg}"))
        
        threading.Thread(target=load_async, daemon=True).start()
    
    def update_knowledge_base_list(self, knowledge_bases):
        """更新知識庫列表"""
        self.kb_listbox.delete(0, tk.END)
        self.knowledge_bases = knowledge_bases
        
        for kb in knowledge_bases:
            if isinstance(kb, dict):
                name = kb.get('name', 'Unknown')
                kb_id = kb.get('id', 'Unknown')
                self.kb_listbox.insert(tk.END, f"{name} (ID: {kb_id})")
        
        self.log_kb(f"載入了 {len(knowledge_bases)} 個知識庫")
    
    def update_files_list(self, files):
        """更新檔案列表"""
        # 清空現有列表
        for item in self.files_tree.get_children():
            self.files_tree.delete(item)
        
        self.kb_files_data = files
        self.selected_files.clear()
        
        for i, file_info in enumerate(files):
            if isinstance(file_info, dict):
                file_id = file_info.get('id', 'Unknown')
                file_name = file_info.get('filename', file_info.get('name', 'Unknown'))
                file_size = file_info.get('file_size', file_info.get('size', 0))
                status = file_info.get('status', 'Unknown')
                created_at = file_info.get('created_at', file_info.get('updated_at', 'Unknown'))
                
                # 格式化檔案大小
                if isinstance(file_size, (int, float)) and file_size > 0:
                    if file_size > 1024 * 1024:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"
                    elif file_size > 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        size_str = f"{file_size} B"
                else:
                    size_str = "-"
                
                # 格式化狀態
                status_map = {
                    'pending': '待處理',
                    'processing': '處理中',
                    'completed': '已完成',
                    'failed': '失敗',
                    'deleting': '刪除中'
                }
                status_display = status_map.get(status, status)
                
                # 格式化創建時間
                if created_at and created_at != 'Unknown':
                    try:
                        # 嘗試解析並格式化時間
                        if 'T' in created_at:
                            date_part = created_at.split('T')[0]
                            time_part = created_at.split('T')[1].split('.')[0] if '.' in created_at else created_at.split('T')[1]
                            created_at = f"{date_part} {time_part[:8]}"
                    except:
                        pass
                
                # 添加到樹形視圖
                item_id = self.files_tree.insert('', 'end', text='☐', values=(
                    file_name,      # 檔案名稱
                    size_str,       # 大小
                    status_display, # 狀態
                    created_at      # 創建時間
                ))
                
                # 為每個item保存檔案資訊，以便後續使用
                self.file_info_map[item_id] = file_info
        
        # 更新按鈕狀態
        if len(files) > 0:
            self.select_all_button.config(state=tk.NORMAL)
            self.deselect_all_button.config(state=tk.NORMAL)
            self.kb_export_button.config(state=tk.NORMAL)
        else:
            self.select_all_button.config(state=tk.DISABLED)
            self.deselect_all_button.config(state=tk.DISABLED)
            self.kb_export_button.config(state=tk.DISABLED)
        
        self.log_kb(f"載入了 {len(files)} 個檔案")
    
    def toggle_file_selection(self, event):
        """切換檔案選擇狀態"""
        item = self.files_tree.selection()[0] if self.files_tree.selection() else None
        if item:
            current_text = self.files_tree.item(item, 'text')
            if current_text == '☐':
                # 選中
                self.files_tree.item(item, text='☑')
                self.selected_files.add(item)
            else:
                # 取消選中
                self.files_tree.item(item, text='☐') 
                self.selected_files.discard(item)
    
    def select_all_files(self):
        """選擇所有檔案"""
        for item_id in self.files_tree.get_children():
            self.files_tree.item(item_id, text='☑')
            self.selected_files.add(item_id)
        
        self.log_kb("已選擇所有檔案")
    
    def deselect_all_files(self):
        """取消選擇所有檔案"""
        for item_id in self.files_tree.get_children():
            self.files_tree.item(item_id, text='☐')
        self.selected_files.clear()
        
        self.log_kb("已取消選擇所有檔案")
    
    def start_kb_export(self):
        """開始知識庫文件匯出"""
        # 檢查設定
        if not self.selected_kb_id:
            messagebox.showerror("錯誤", "請先選擇知識庫")
            return
        
        if not self.kb_api_key.get():
            messagebox.showerror("錯誤", "請輸入 API 金鑰")
            return
        
        if not self.kb_export_dir.get():
            messagebox.showerror("錯誤", "請選擇匯出目錄")
            return
        
        # 檢查選中的文件
        selected_files = [
            self.file_info_map[item_id] for item_id in self.selected_files
            if item_id in self.file_info_map
        ]
        
        if not selected_files:
            messagebox.showerror("錯誤", "請至少選擇一個文件")
            return
        
        self.kb_export_button.config(state='disabled')
        # 重置檔案匯出進度條
        self.kb_export_progress.configure(value=0)
        self.kb_export_progress_label.config(text=f"0/{len(selected_files)}")
        
        threading.Thread(target=self.run_kb_export, args=(selected_files,), daemon=True).start()
    
    async def _download_single_file_concurrent(self, client, file_info, kb_export_path, download_stats, semaphore, file_index):
        """並行下載單個文件"""
        async with semaphore:  # 控制並發數量
            file_id = file_info.get('id')
            file_name = file_info.get('filename', file_info.get('name', f'file_{file_id}'))
            file_status = file_info.get('status', 'unknown')
            
            try:
                # 檢查文件狀態
                if file_status in ['deleting', 'failed']:
                    self.log_kb(f"⚠️ 跳過文件 {file_name}：狀態為 {file_status}")
                    async with download_stats['lock']:
                        download_stats['failed'] += 1
                        download_stats['completed'] += 1
                        self._update_concurrent_progress(download_stats)
                    return
                
                self.log_kb(f"📥 開始下載文件: {file_name}")
                
                # 下載文件（使用重試機制）
                file_data = await client.download_knowledge_base_file(self.selected_kb_id, file_id, max_retries=3)
                
                # 保存文件
                file_path = kb_export_path / file_name
                with open(file_path, 'wb') as f:
                    f.write(file_data)
                
                self.log_kb(f"✅ 文件下載成功: {file_name} ({len(file_data)} bytes)")
                
                # 更新統計
                async with download_stats['lock']:
                    download_stats['successful'] += 1
                    download_stats['completed'] += 1
                    self._update_concurrent_progress(download_stats)
                    
            except Exception as e:
                error_msg = str(e)
                self.log_kb(f"❌ 文件下載失敗: {file_name} (ID: {file_id})")
                self.log_kb(f"   錯誤詳情: {error_msg}")
                
                # 根據錯誤類型提供更具體的說明
                if "502" in error_msg or "503" in error_msg or "504" in error_msg:
                    self.log_kb(f"   可能原因: 服務器暫時不可用，已嘗試重試")
                elif "404" in error_msg:
                    self.log_kb(f"   可能原因: 文件不存在或無下載權限")
                elif "超時" in error_msg:
                    self.log_kb(f"   可能原因: 網路連接超時")
                
                # 更新統計
                async with download_stats['lock']:
                    download_stats['failed'] += 1
                    download_stats['completed'] += 1
                    self._update_concurrent_progress(download_stats)
    
    def _update_concurrent_progress(self, download_stats):
        """更新並行下載進度（線程安全）"""
        if not self.gui_running:
            return
            
        completed = download_stats['completed']
        total = download_stats['total']
        successful = download_stats['successful']
        failed = download_stats['failed']
        
        # 更新進度條（線程安全）
        progress = (completed / total) * 100 if total > 0 else 0
        try:
            self.root.after(0, lambda p=progress: self._safe_update_progress_bar(p))
            self.root.after(0, lambda c=completed, t=total, s=successful, f=failed: 
                           self._safe_update_progress_label(c, t, s, f))
        except Exception as e:
            # 如果 GUI 更新失敗，記錄但不拋出異常
            print(f"GUI 更新失敗: {e}")
    
    def _safe_update_progress_bar(self, progress_value):
        """安全更新進度條"""
        try:
            if self.gui_running and hasattr(self, 'kb_export_progress'):
                self.kb_export_progress.configure(value=progress_value)
        except Exception:
            pass
            
    def _safe_update_progress_label(self, completed, total, successful, failed):
        """安全更新進度標籤"""
        try:
            if self.gui_running and hasattr(self, 'kb_export_progress_label'):
                self.kb_export_progress_label.config(text=f"{completed}/{total} (成功:{successful}, 失敗:{failed})")
        except Exception:
            pass
    
    def _safe_update_kb_progress_bar(self, progress_value):
        """安全更新知識庫文件載入進度條"""
        try:
            if self.gui_running and hasattr(self, 'kb_files_progress'):
                self.kb_files_progress.configure(value=progress_value)
        except Exception:
            pass
            
    def _safe_update_kb_progress_label(self, current, total):
        """安全更新知識庫文件載入進度標籤"""
        try:
            if self.gui_running and hasattr(self, 'kb_progress_label'):
                self.kb_progress_label.config(text=f"{current}/{total}")
        except Exception:
            pass
    
    def _safe_update_kb_progress_label_text(self, text):
        """安全更新知識庫文件載入進度標籤（任意文本）"""
        try:
            if self.gui_running and hasattr(self, 'kb_progress_label'):
                self.kb_progress_label.config(text=text)
        except Exception:
            pass
    
    def run_kb_export(self, selected_files):
        """執行知識庫文件匯出（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            result = loop.run_until_complete(self.export_kb_files(selected_files))
            loop.close()
            
            if isinstance(result, dict):  # 成功，包含統計信息
                export_stats = result
                if self.gui_running:
                    self.root.after(0, lambda: self.kb_export_completed(export_stats))
            elif result:  # 舊版本的布爾返回值
                if self.gui_running:
                    self.root.after(0, lambda: self.kb_export_completed())
            else:
                if self.gui_running:
                    self.root.after(0, lambda: self.kb_export_failed("匯出過程中發生錯誤"))
                
        except Exception as e:
            error_msg = str(e)
            if self.gui_running:
                self.root.after(0, lambda: self.kb_export_failed(error_msg))
    
    async def export_kb_files(self, selected_files):
        """匯出知識庫文件（終極串行下載 - 完全無日誌）"""
        try:
            # 終極靜默模式 - 完全禁用所有日誌和GUI更新
            self._download_in_progress = True
            self._emergency_throttle = True  # 強制啟用緊急限流
            print(f"[SILENT] 開始串行下載 {len(selected_files)} 個文件")
            
            # 使用完全無日誌的API客戶端
            async with MaiAgentApiClient(self.kb_base_url.get(), 
                                       self.kb_api_key.get(), 
                                       None) as client:
                
                total_files = len(selected_files)
                export_dir = Path(self.kb_export_dir.get())
                
                # 創建匯出目錄
                kb_name = "unknown_kb"
                for kb in self.knowledge_bases:
                    if kb['id'] == self.selected_kb_id:
                        kb_name = kb.get('name', 'unknown_kb')
                        break
                
                kb_export_path = export_dir / f"knowledge_base_{kb_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                kb_export_path.mkdir(parents=True, exist_ok=True)
                
                print(f"[DOWNLOAD] 創建匯出目錄: {kb_export_path}")
                print(f"[DOWNLOAD] 開始串行下載 {total_files} 個文件")
                
                # 串行下載統計
                successful = 0
                failed = 0
                
                # 串行下載每個文件 - 修復文件名和進度條問題
                for i, file_info in enumerate(selected_files):
                    # 安全的文件處理流程
                    safe_filename = "unknown_file"
                    final_filename = "unknown_file"
                    
                    try:
                        # 處理文件名：長度限制和特殊字符清理
                        original_filename = file_info.get('filename', f'file_{file_info.get("id", "unknown")}')
                        safe_filename = self._sanitize_filename(original_filename)
                        print(f"[DOWNLOAD] 下載 {i+1}/{total_files}: {safe_filename}")
                        
                        # 確保文件名唯一（避免重複）
                        final_filename = self._ensure_unique_filename(kb_export_path, safe_filename)
                        
                        # 簡單下載 - 無重試，無複雜錯誤處理
                        file_content = await client.download_knowledge_base_file(
                            self.selected_kb_id, file_info['id'], max_retries=1
                        )
                        
                        # 安全保存文件
                        file_path = kb_export_path / final_filename
                        with open(file_path, 'wb') as f:
                            f.write(file_content)
                        
                        successful += 1
                        print(f"[DOWNLOAD] ✅ 成功: {final_filename}")
                        
                    except Exception as e:
                        failed += 1
                        print(f"[DOWNLOAD] ❌ 失敗: {final_filename} - {str(e)[:100]}")
                    
                    # 安全更新進度條（重新啟用，但使用簡化版本）
                    progress = ((i + 1) / total_files) * 100
                    print(f"[DOWNLOAD] 進度: {progress:.1f}% ({successful} 成功, {failed} 失敗)")
                    
                    # 安全的GUI進度更新（修復Lambda閉包問題）
                    try:
                        if self.gui_running:
                            # 創建局部變量副本，避免Lambda閉包問題
                            current_progress = progress
                            current_index = i + 1
                            current_successful = successful
                            current_failed = failed
                            self.root.after(0, 
                                lambda: self._update_export_progress_safe(
                                    current_progress, current_index, total_files, 
                                    current_successful, current_failed
                                )
                            )
                    except Exception:
                        # 忽略GUI更新錯誤，繼續下載
                        pass
                
                # 最終統計（含安全GUI更新）
                print(f"[DOWNLOAD] 📊 串行下載完成統計:")
                print(f"[DOWNLOAD]    成功: {successful} 個文件")
                print(f"[DOWNLOAD]    失敗: {failed} 個文件")
                print(f"[DOWNLOAD]    總計: {total_files} 個文件")
                print(f"[DOWNLOAD]    匯出目錄: {kb_export_path}")
                
                # 最終進度條更新（修復Lambda閉包）
                try:
                    if self.gui_running:
                        # 創建最終值的局部副本
                        final_successful = successful
                        final_failed = failed
                        final_total = total_files
                        self.root.after(0, 
                            lambda: self._update_export_progress_safe(
                                100, final_total, final_total, final_successful, final_failed
                            )
                        )
                except Exception:
                    pass
                
                # 根據成功率判定匯出結果
                success_rate = successful / total_files if total_files > 0 else 0
                
                # 準備統計信息
                export_stats = {
                    'successful': successful,
                    'failed': failed,
                    'total': total_files,
                    'success_rate': success_rate,
                    'concurrent': 1  # 串行下載
                }
                
                if successful > 0:
                    if failed == 0:
                        print(f"[DOWNLOAD] 🎉 串行下載完全成功！")
                    elif success_rate >= 0.8:  # 80% 成功率視為成功
                        print(f"[DOWNLOAD] ✅ 串行下載基本成功（成功率: {success_rate:.1%}）")
                    else:
                        print(f"[DOWNLOAD] ⚠️ 串行下載部分成功（成功率: {success_rate:.1%}）")
                    return export_stats
                else:
                    # 完全失敗
                    raise Exception(f"串行下載完全失敗：{failed} 個文件都無法下載")
                
        except Exception as e:
            print(f"[DOWNLOAD] ❌ 匯出失敗: {str(e)}")
            return False
        finally:
            # 禁用下載靜默模式
            self._download_in_progress = False
            self._emergency_throttle = False
            print("[DOWNLOAD] 下載完成，靜默模式已禁用")
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名：處理長度限制和特殊字符（增強版本）"""
        try:
            import re
            import os
            import time
            
            # 安全檢查輸入
            if not filename or not isinstance(filename, str):
                return f"safe_file_{int(time.time())}.txt"
            
            # 移除或替換不安全的字符
            # 保留中文字符，只替換文件系統不支持的字符
            unsafe_chars = r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f]'
            safe_filename = re.sub(unsafe_chars, '_', filename)
            
            # 移除連續的下劃線和前後空白
            safe_filename = re.sub(r'_+', '_', safe_filename).strip('_. ')
            
            # 處理文件名長度限制（保留副檔名）
            name_part, ext_part = os.path.splitext(safe_filename)
            max_name_length = 180  # 更保守的限制
            
            if len(name_part) > max_name_length:
                # 截斷名稱部分，保持副檔名
                name_part = name_part[:max_name_length].rstrip('._')
                safe_filename = name_part + ext_part
            
            # 確保文件名不為空和有效
            if not safe_filename or safe_filename in ['.', '..', '_']:
                safe_filename = f"safe_file_{int(time.time())}.txt"
            
            # 確保有副檔名
            if '.' not in safe_filename:
                safe_filename += '.txt'
            
            return safe_filename
            
        except Exception:
            # 如果任何步驟失敗，返回安全的預設值
            import time
            return f"fallback_file_{int(time.time())}.txt"
    
    def _ensure_unique_filename(self, directory: Path, filename: str) -> str:
        """確保文件名在目錄中唯一（增強版本）"""
        try:
            import os
            import time
            
            # 安全檢查輸入
            if not filename:
                filename = f"safe_file_{int(time.time())}.txt"
            
            base_path = directory / filename
            if not base_path.exists():
                return filename
            
            # 文件已存在，添加序號
            name_part, ext_part = os.path.splitext(filename)
            
            # 限制循環次數，防止無限循環
            for counter in range(1, 100):
                new_filename = f"{name_part}_{counter}{ext_part}"
                new_path = directory / new_filename
                if not new_path.exists():
                    return new_filename
            
            # 如果100次都不行，使用時間戳
            timestamp = int(time.time())
            return f"{name_part}_{timestamp}{ext_part}"
            
        except Exception:
            # 如果任何步驟失敗，返回帶時間戳的安全名稱
            import time
            return f"emergency_file_{int(time.time())}.txt"
    
    def _update_export_progress_safe(self, progress: float, current: int, total: int, successful: int, failed: int):
        """安全的進度條更新方法"""
        try:
            if not self.gui_running:
                return
                
            # 更新進度條
            if hasattr(self, 'kb_export_progress'):
                self.kb_export_progress.configure(value=progress)
            
            # 更新標籤
            if hasattr(self, 'kb_export_progress_label'):
                status_text = f"{current}/{total} 檔案 (成功: {successful}, 失敗: {failed})"
                self.kb_export_progress_label.config(text=status_text)
                
        except Exception:
            # 完全忽略GUI更新錯誤
            pass
    
    def kb_export_completed(self, export_stats=None):
        """知識庫匯出完成"""
        # 確保關閉靜默模式
        self._download_in_progress = False
        self._emergency_throttle = False
        print("[DOWNLOAD] 下載完成，靜默模式已禁用")
        
        self.kb_export_button.config(state='normal')
        # 重置進度條
        self.kb_export_progress.configure(value=0)
        self.kb_export_progress_label.config(text="0/0")
        
        # 顯示詳細的匯出結果
        if export_stats:
            successful = export_stats.get('successful', 0)
            failed = export_stats.get('failed', 0)
            total = successful + failed
            concurrent = export_stats.get('concurrent', 1)
            
            if failed == 0:
                message = f"知識庫文件並行下載完全成功！\n\n成功匯出 {successful} 個文件\n並發數: {concurrent}"
                title = "並行下載完成"
            else:
                success_rate = (successful / total) * 100 if total > 0 else 0
                message = f"知識庫文件並行下載已完成！\n\n成功: {successful} 個文件\n失敗: {failed} 個文件\n成功率: {success_rate:.1f}%\n並發數: {concurrent}"
                title = "並行下載完成"
        else:
            message = "知識庫文件並行下載已成功完成！"
            title = "並行下載完成"
            
        messagebox.showinfo(title, message)
        self.log_info("知識庫文件匯出完成", 'KnowledgeBase')
    
    def kb_export_failed(self, error_message):
        """知識庫匯出失敗"""
        # 確保關閉靜默模式
        self._download_in_progress = False
        self._emergency_throttle = False
        print("[DOWNLOAD] 下載失敗，靜默模式已禁用")
        
        self.kb_export_button.config(state='normal')
        # 重置進度條
        self.kb_export_progress.configure(value=0)
        self.kb_export_progress_label.config(text="匯出失敗")
        messagebox.showerror("匯出失敗", f"匯出過程發生錯誤：{error_message}")
        self.log_error(f"知識庫文件匯出失敗: {error_message}", 'KnowledgeBase')
    
    def log_kb(self, message):
        """記錄知識庫日誌"""
        self.root.after(0, lambda: self._update_kb_log(message))
    
    def _update_kb_log(self, message):
        """更新知識庫日誌顯示"""
        if self.kb_log_text:
            self.kb_log_text.insert(tk.END, f"{message}\n")
            self.kb_log_text.see(tk.END)
            self.root.update()

    def browse_upload_file(self):
        """瀏覽選擇要上傳的檔案"""
        filetypes = [
            ("文字檔案", "*.txt"),
            ("Markdown 檔案", "*.md"),
            ("PDF 檔案", "*.pdf"),
            ("Word 檔案", "*.docx"),
            ("PowerPoint 檔案", "*.pptx"),
            ("Excel 檔案", "*.xlsx"),
            ("所有檔案", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title="選擇要上傳的檔案",
            filetypes=filetypes
        )
        
        if filename:
            self.upload_file_var.set(filename)
            # 檢查是否選擇了知識庫
            if self.current_kb_id:
                self.upload_start_button.config(state=tk.NORMAL)
            self.log_kb(f"已選擇檔案: {os.path.basename(filename)}")

    def start_file_upload(self):
        """開始檔案上傳"""
        if not self.upload_file_var.get():
            messagebox.showwarning("警告", "請先選擇要上傳的檔案")
            return
        
        if not self.current_kb_id:
            messagebox.showwarning("警告", "請先選擇知識庫")
            return
        
        # 檢查檔案是否存在
        file_path = self.upload_file_var.get()
        if not os.path.exists(file_path):
            messagebox.showerror("錯誤", "選擇的檔案不存在")
            return
        
        # 檢查檔案大小（限制100MB）
        file_size = os.path.getsize(file_path)
        max_size = 100 * 1024 * 1024  # 100MB
        if file_size > max_size:
            messagebox.showerror("錯誤", f"檔案過大，最大支援 {max_size // (1024*1024)} MB")
            return
        
        # 開始上傳
        self.upload_start_button.config(state=tk.DISABLED)
        self.upload_progress.start()
        
        filename = os.path.basename(file_path)
        self.log_kb(f"開始上傳檔案: {filename}")
        
        # 在背景執行上傳
        self.upload_thread = threading.Thread(target=self.run_file_upload, daemon=True)
        self.upload_thread.start()

    def run_file_upload(self):
        """執行檔案上傳的背景處理"""
        try:
            # 取得API配置
            base_url = self.kb_base_url_var.get().strip()
            api_key = self.kb_api_key_var.get().strip()
            file_path = self.upload_file_var.get()
            
            if not base_url or not api_key:
                self.root.after(0, lambda: self.upload_failed("請先配置API基礎URL和API金鑰"))
                return
            
            def upload_async():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    async def upload():
                        async with MaiAgentApiClient(base_url, api_key, None) as client:
                            result = await client.upload_file_to_knowledge_base(
                                kb_id=self.current_kb_id,
                                file_path=file_path
                            )
                            return result
                    
                    result = loop.run_until_complete(upload())
                    
                    # 上傳成功
                    self.root.after(0, lambda: self.upload_completed(result))
                    
                except Exception as e:
                    error_msg = f"上傳失敗: {str(e)}"
                    self.root.after(0, lambda: self.upload_failed(error_msg))
                finally:
                    loop.close()
            
            upload_async()
            
        except Exception as e:
            error_msg = f"上傳準備失敗: {str(e)}"
            self.root.after(0, lambda: self.upload_failed(error_msg))

    def upload_completed(self, result):
        """檔案上傳完成回調"""
        self.upload_progress.stop()
        self.upload_start_button.config(state=tk.NORMAL)
        
        if result and len(result) > 0:
            uploaded_file = result[0]
            filename = uploaded_file.get('filename', '未知檔案')
            self.log_kb(f"✅ 檔案上傳成功: {filename}")
            
            # 清空檔案選擇
            self.upload_file_var.set("")
            self.upload_start_button.config(state=tk.DISABLED)
            
            # 重新載入檔案列表
            self.load_kb_files()
            
            messagebox.showinfo("成功", f"檔案 '{filename}' 上傳成功！")
        else:
            self.log_kb("❌ 上傳完成但未獲得檔案資訊")

    def upload_failed(self, error_message):
        """檔案上傳失敗回調"""
        self.upload_progress.stop()
        self.upload_start_button.config(state=tk.NORMAL)
        
        self.log_kb(f"❌ {error_message}")
        messagebox.showerror("上傳失敗", error_message)
            
    def run(self):
        """執行 GUI 應用程式"""
        try:
            # 設定關閉時的清理
            def on_closing():
                self.gui_running = False  # 停止所有 GUI 更新
                try:
                    self.log_info("MaiAgent 驗證工具正在關閉...")
                    self.log_info(f"最終日誌統計: {self.get_log_stats()}")
                except:
                    # 如果日誌記錄失敗，直接關閉
                    pass
                self.root.destroy()
            
            self.root.protocol("WM_DELETE_WINDOW", on_closing)
            self.root.mainloop()
        except Exception as e:
            # 完全安全的異常處理 - 避免任何可能的遞歸
            error_type = type(e).__name__
            error_msg = str(e)[:200]  # 限制錯誤訊息長度
            
            print(f"[SAFE-ERROR] 應用程式執行錯誤: {error_msg}")
            print(f"[SAFE-ERROR] 錯誤類型: {error_type}")
            
            # 如果是遞歸錯誤，立即啟用所有安全機制
            if isinstance(e, RecursionError) or "recursion" in error_msg.lower() or "maximum" in error_msg.lower():
                self._emergency_throttle = True
                self._download_in_progress = False  # 停止下載
                print("[SAFE-ERROR] 偵測到遞歸錯誤，啟用緊急保護模式")
                
                # 嘗試清理GUI狀態
                try:
                    if hasattr(self, 'root') and self.root:
                        self.root.after(100, lambda: setattr(self, 'gui_running', False))
                except:
                    pass
            
            # 不調用任何可能遞歸的方法，直接退出
            return

    def on_kb_selection_changed(self, event):
        """知識庫選擇變更處理"""
        selection = self.kb_listbox.curselection()
        if selection:
            selected_kb = self.knowledge_bases[selection[0]]
            self.current_kb_id = selected_kb['id']
            self.selected_kb_id = selected_kb['id']  # 保持相容性
            self.log_kb(f"選擇了知識庫: {selected_kb.get('name', 'Unknown')}")
            
            # 啟用上傳功能（如果已選擇檔案）
            if hasattr(self, 'upload_file_var') and self.upload_file_var.get():
                self.upload_start_button.config(state=tk.NORMAL)
            
            # 自動載入檔案列表
            self.load_kb_files()
        else:
            self.current_kb_id = None
            self.selected_kb_id = None
            if hasattr(self, 'upload_start_button'):
                self.upload_start_button.config(state=tk.DISABLED)
    
    def on_load_mode_changed(self):
        """載入模式變更處理"""
        if hasattr(self, 'load_all_at_once'):
            mode = "一次性載入" if self.load_all_at_once.get() else "分頁載入"
            self.log_kb(f"📋 載入模式已變更為: {mode}")
            # 如果已經載入了文件，提示用戶重新載入
            if hasattr(self, 'files_tree') and self.files_tree.get_children():
                self.log_kb("💡 模式變更後，請重新載入文件以套用新設置")
    
    def load_kb_files(self):
        """載入知識庫檔案列表"""
        if not self.current_kb_id and not self.selected_kb_id:
            messagebox.showerror("錯誤", "請先選擇知識庫")
            self.log_kb("❌ 載入檔案失敗 - 未選擇知識庫")
            return
        
        # 獲取API配置
        base_url = self.kb_base_url.get().strip()
        api_key = self.kb_api_key.get().strip()
        
        if not base_url:
            messagebox.showerror("錯誤", "請先輸入 API 基礎 URL")
            self.log_kb("❌ 載入失敗 - 未輸入基礎URL")
            return
            
        if not api_key:
            messagebox.showerror("錯誤", "請先輸入 API 金鑰")
            self.log_kb("❌ 載入失敗 - 未輸入API金鑰")
            return
        
        # 使用current_kb_id或selected_kb_id
        kb_id = self.current_kb_id or self.selected_kb_id
        
        def update_progress(current, total):
            """更新進度條（線程安全）"""
            if not self.gui_running:
                return
                
            if total > 0:
                progress = (current / total) * 100
                try:
                    self.root.after(0, lambda p=progress: self._safe_update_kb_progress_bar(p))
                    self.root.after(0, lambda c=current, t=total: self._safe_update_kb_progress_label(c, t))
                except Exception:
                    pass
            else:
                try:
                    self.root.after(0, lambda: self._safe_update_kb_progress_bar(0))
                    self.root.after(0, lambda: self._safe_update_kb_progress_label(0, 0))
                except Exception:
                    pass
        
        def load_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 重置進度條
                self.root.after(0, lambda: self._safe_update_kb_progress_bar(0))
                self.root.after(0, lambda: self._safe_update_kb_progress_label_text("載入中..."))
                
                self.root.after(0, lambda: self.log_kb(f"�� 正在載入知識庫檔案 (ID: {kb_id})..."))
                
                async def fetch():
                    async with MaiAgentApiClient(base_url, api_key, None) as client:
                        load_all = getattr(self, 'load_all_at_once', tk.BooleanVar(value=True)).get()
                        files = await client.get_knowledge_base_files(kb_id, progress_callback=update_progress, load_all_at_once=load_all)
                        mode_text = "一次性載入" if load_all else "分頁載入"
                        self.root.after(0, lambda: self.log_kb(f"📋 成功獲取 {len(files)} 個檔案（{mode_text}）"))
                        return files
                
                files = loop.run_until_complete(fetch())
                loop.close()
                
                # 完成進度
                self.root.after(0, lambda: self._safe_update_kb_progress_bar(100))
                self.root.after(0, lambda: self.update_files_list(files))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.log_kb(f"❌ 載入檔案失敗: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入檔案列表失敗：{error_msg}"))
                # 重置進度條
                self.root.after(0, lambda: self._safe_update_kb_progress_bar(0))
                self.root.after(0, lambda: self._safe_update_kb_progress_label_text("載入失敗"))
        
        threading.Thread(target=load_async, daemon=True).start()


def main():
    """主函數"""
    try:
        app = MaiAgentValidatorGUI()
        app.run()
    except Exception as e:
        messagebox.showerror("錯誤", f"應用程式啟動失敗: {str(e)}")


if __name__ == "__main__":
    main() 