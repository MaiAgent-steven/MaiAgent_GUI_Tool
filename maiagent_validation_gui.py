#!/usr/bin/env python3
"""
MaiAgent Django 自動化驗證工具 - GUI 版本

具有圖形化使用者界面的 AI 助理回覆品質驗證工具
支援 RAG 增強統計分析功能
"""

# 版本信息
__version__ = "4.0.1"
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
    
    # API 回覆結果（自動填入）
    AI助理回覆: str = ""
    引用節點: str = ""
    參考文件: str = ""
    
    # 驗證結果（自動填入）
    引用節點是否命中: str = ""
    參考文件是否正確: str = ""
    回覆是否滿意: str = ""
    
    # RAG 增強指標（自動填入）
    precision: float = 0.0
    recall: float = 0.0
    f1_score: float = 0.0
    hit_rate: float = 0.0


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
                        # 限制載荷長度以避免日誌過長
                        if len(payload_str) > 500:
                            payload_str = payload_str[:500] + "...(內容已截斷)"
                        details.append(f"     {payload_str}")
                    except:
                        details.append(f"     {str(payload)[:500]}...")
                else:
                    details.append(f"     {str(payload)[:500]}...")
            
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
                        # 限制回應長度以避免日誌過長
                        if len(response_str) > 1000:
                            response_str = response_str[:1000] + "...(內容已截斷)"
                        details.append(f"     {response_str}")
                    except:
                        details.append(f"     {str(response_data)[:1000]}...")
                elif isinstance(response_data, str):
                    if len(response_data) > 1000:
                        details.append(f"     {response_data[:1000]}...(內容已截斷)")
                    else:
                        details.append(f"     {response_data}")
                else:
                    details.append(f"     {str(response_data)[:1000]}...")
            
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
        self.session = aiohttp.ClientSession(headers=headers)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_chatbots(self) -> List[Dict]:
        """獲取可用的聊天機器人列表"""
        if not self.session:
            raise Exception("API Client session not initialized")
            
        url = self._build_api_url("chatbots/")
        start_time = pd.Timestamp.now()
        
        self._log_api_request(url, 'GET')
        
        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status == 200:
                data = await response.json()
                return data.get('results', [])
            else:
                raise Exception(f"獲取聊天機器人列表失敗: {response.status} - {response_text}")
    
    async def send_message(self, chatbot_id: str, message: str, conversation_id: Optional[str] = None) -> ApiResponse:
        """發送訊息到指定的聊天機器人"""
        if not self.session:
            raise Exception("API Client session not initialized")
            
        url = self._build_api_url(f"chatbots/{chatbot_id}/completions/")
        
        payload = {
            "conversation": conversation_id,
            "message": {
                "content": message,
                "attachments": []
            },
            "isStreaming": False
        }
        
        start_time = pd.Timestamp.now()
        self._log_api_request(url, 'POST', payload)
        
        async with self.session.post(url, json=payload) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            response_text = await response.text()
            
            self._log_api_response(url, response.status, len(response_text), duration)
            
            if response.status == 200:
                data = await response.json()
                return ApiResponse(
                    conversation_id=data.get('conversationId'),
                    content=data.get('content', ''),
                    citations=data.get('citations', []),
                    citation_nodes=data.get('citationNodes', [])
                )
            else:
                raise Exception(f"發送訊息失敗: {response.status} - {response_text}")
    
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
        """獲取知識庫列表"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url("knowledge-bases/")
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
                    return data
                elif isinstance(data, dict):
                    return data.get('results', [])
                else:
                    return []
            else:
                raise Exception(f"獲取知識庫列表失敗: {response.status} - {response_text}")
    
    async def get_knowledge_base_files(self, kb_id: str) -> List[Dict]:
        """獲取知識庫文件列表"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url(f"knowledge-bases/{kb_id}/files/")
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
                raise Exception(f"獲取知識庫文件列表失敗: {response.status} - {response_text}")
    
    async def download_knowledge_base_file(self, kb_id: str, file_id: str) -> bytes:
        """下載知識庫文件"""
        if not self.session:
            raise Exception("API Client session not initialized")

        url = self._build_api_url(f"knowledge-bases/{kb_id}/files/{file_id}/download/")
        start_time = pd.Timestamp.now()

        self._log_api_request(url, 'GET')

        async with self.session.get(url) as response:
            duration = (pd.Timestamp.now() - start_time).total_seconds()
            
            self._log_api_response(url, response.status, 0, duration)

            if response.status == 200:
                return await response.read()
            else:
                response_text = await response.text()
                raise Exception(f"下載文件失敗: {response.status} - {response_text}")
    
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
    
    def get_conversation_id(self, questioner: str) -> Optional[str]:
        return self.conversations.get(questioner)
    
    def set_conversation_id(self, questioner: str, conversation_id: str):
        self.conversations[questioner] = conversation_id


class CSVParser:
    """CSV 文件解析器 - 整合自 deploy_from_csv.py"""
    
    def __init__(self, csv_file: str):
        self.csv_file = csv_file
        self.members = []
        self.groups_info = {}
        
    def parse(self) -> Tuple[List[Dict], Dict[str, List[str]]]:
        """解析 CSV 文件，返回成員列表和群組信息"""
        print(f"📄 正在解析 CSV 文件: {self.csv_file}")
        
        with open(self.csv_file, 'r', encoding='utf-8-sig') as file:
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
    def calculate_similarity(text1: str, text2: str) -> float:
        """計算兩個文字的相似度（0-1之間）"""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()
    
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
            if 'chatbotTextNode' in node and 'content' in node['chatbotTextNode']:
                node_content = node['chatbotTextNode']['content']
                similarity = cls.calculate_similarity(node_content, expected_content)
                
                if similarity > best_match_score:
                    best_match_score = similarity
                    best_match_content = node_content
        
        is_hit = best_match_score >= similarity_threshold
        result_detail = f"最佳匹配分數: {best_match_score:.2f}"
        
        return is_hit, result_detail
    
    @classmethod
    def check_rag_enhanced_hit(cls, citation_nodes: List[Dict], expected_content: str, 
                             similarity_threshold: float = 0.3, top_k: Optional[int] = None,
                             custom_separators: List[str] = None) -> Tuple[bool, Dict]:
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
            if 'chatbotTextNode' in node and 'content' in node['chatbotTextNode']:
                chunk_content = node['chatbotTextNode']['content']
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
                similarity = cls.calculate_similarity(chunk['content'], expected_seg)
                
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
    def check_citation_file_match(cls, citations: List[Dict], expected_files: str) -> Tuple[bool, str]:
        """檢查參考文件是否正確"""
        if not citations or not expected_files:
            return False, "無引用文件或預期文件為空"
        
        expected_file_list = [f.strip() for f in expected_files.split(',') if f.strip()]
        cited_files = []
        
        for citation in citations:
            if 'name' in citation:
                cited_files.append(citation['name'])
        
        matches = []
        for expected_file in expected_file_list:
            for cited_file in cited_files:
                if cls.contains_keywords(cited_file, expected_file) or cls.calculate_similarity(cited_file, expected_file) > 0.7:
                    matches.append(f"{expected_file} -> {cited_file}")
        
        is_correct = len(matches) > 0
        result_detail = f"匹配文件: {len(matches)} 個"
        
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
            self.canvas.bind_all("<MouseWheel>", _on_mousewheel)
            # macOS 滾輪事件
            self.canvas.bind_all("<Button-4>", _on_mousewheel)
            self.canvas.bind_all("<Button-5>", _on_mousewheel)
        
        def _unbind_from_mousewheel(event):
            self.canvas.unbind_all("<MouseWheel>")
            # macOS 滾輪事件
            self.canvas.unbind_all("<Button-4>")
            self.canvas.unbind_all("<Button-5>")
        
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
        # 固定使用 RAG 模式，不再提供開關
        self.top_k = None  # 動態：根據 API 回傳的引用節點數量決定
        self.selected_chatbot_id = None
        self.validation_data = []
        self.conversation_manager = ConversationManager()
        self.text_matcher = EnhancedTextMatcher()
        
        # 段落分隔符設定
        self.separator_vars = {
            '---': tk.BooleanVar(value=True),      # 三個連字符
            '|||': tk.BooleanVar(value=True),      # 三個豎線
            '\n\n': tk.BooleanVar(value=True),     # 雙換行
            '###': tk.BooleanVar(value=False),     # 三個井號
            '===': tk.BooleanVar(value=False),     # 三個等號
            '...': tk.BooleanVar(value=False),     # 三個點
        }
        
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
        
        self.create_widgets()
        
        # 記錄啟動日誌
        self.log_info(f"{__app_name__} v{__version__} 已啟動")
        self.log_info(f"日誌系統已初始化，日誌目錄: {Path('logs').absolute()}")
    
    def api_logger_callback(self, method_name, *args, **kwargs):
        """API日誌回調函數 - 增強版本"""
        if method_name == 'log_api_request' and len(args) >= 2:
            url, method = args[0], args[1]
            payload = args[2] if len(args) > 2 else None
            self.log_api_request(url, method, payload)
        elif method_name == 'log_api_response' and len(args) >= 2:
            url, status_code = args[0], args[1]
            response_size = args[2] if len(args) > 2 else 0
            duration = args[3] if len(args) > 3 else None
            self.log_api_response(url, status_code, response_size, duration)
        elif method_name == 'log_info' and len(args) >= 1:
            message = args[0]
            logger_name = args[1] if len(args) > 1 else 'API'
            self.log_info(message, logger_name)
        elif method_name == 'log_error' and len(args) >= 1:
            message = args[0]
            logger_name = args[1] if len(args) > 1 else 'API'
            self.log_error(message, logger_name)
        
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
        
        ttk.Label(file_frame, text="CSV 文件路徑：").pack(anchor='w')
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
        
        # 驗證參數
        param_frame = ttk.LabelFrame(padding_frame, text="驗證參數", padding=10)
        param_frame.pack(fill='x', pady=(0, 10))
        
        # 系統固定使用 RAG 增強模式，檢索片段數量動態調整
        
        ttk.Label(param_frame, text="相似度閾值 (0.0-1.0)：").pack(anchor='w')
        ttk.Scale(param_frame, from_=0.0, to=1.0, variable=self.similarity_threshold, orient='horizontal').pack(fill='x', pady=(5, 5))
        threshold_label = ttk.Label(param_frame, text="")
        threshold_label.pack(anchor='w')
        self.similarity_threshold.trace_add('write', lambda *args: threshold_label.config(text=f"當前值: {self.similarity_threshold.get():.2f}"))
        
        ttk.Label(param_frame, text="最大並發請求數：").pack(anchor='w')
        ttk.Scale(param_frame, from_=1, to=20, variable=self.max_concurrent, orient='horizontal').pack(fill='x', pady=(5, 5))
        concurrent_label = ttk.Label(param_frame, text="")
        concurrent_label.pack(anchor='w')
        self.max_concurrent.trace_add('write', lambda *args: concurrent_label.config(text=f"當前值: {self.max_concurrent.get()}"))
        
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
        
        # 進度顯示
        progress_frame = ttk.LabelFrame(padding_frame, text="進度", padding=10)
        progress_frame.pack(fill='x', pady=(0, 10))
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill='x', pady=(0, 5))
        
        self.progress_label = ttk.Label(progress_frame, text="準備中...")
        self.progress_label.pack(anchor='w')
        
        # 日誌顯示
        log_frame = ttk.LabelFrame(padding_frame, text="執行日誌", padding=10)
        log_frame.pack(fill='both', expand=True)
        
        # 日誌控制按鈕
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill='x', pady=(0, 5))
        
        ttk.Button(log_control_frame, text="清空日誌", command=self.clear_log_display).pack(side='left')
        ttk.Button(log_control_frame, text="匯出日誌", command=self.export_logs).pack(side='left', padx=(5, 0))
        ttk.Button(log_control_frame, text="開啟日誌資料夾", command=self.open_log_folder).pack(side='left', padx=(5, 0))
        
        # 日誌級別過濾
        ttk.Label(log_control_frame, text="顯示級別:").pack(side='left', padx=(20, 5))
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_combo = ttk.Combobox(log_control_frame, textvariable=self.log_level_var, 
                                      values=["DEBUG", "INFO", "WARNING", "ERROR"], 
                                      width=10, state="readonly")
        log_level_combo.pack(side='left')
        log_level_combo.bind('<<ComboboxSelected>>', self.on_log_level_changed)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, state='disabled')
        self.log_text.pack(fill='both', expand=True)
        
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
        """瀏覽選擇 CSV 文件"""
        filename = filedialog.askopenfilename(
            title="選擇 CSV 測試文件",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
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
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"連接失敗：{str(e)}"))
        
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
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入失敗：{str(e)}"))
        
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
            messagebox.showerror("錯誤", "請選擇 CSV 文件")
            return
            
        if not self.api_key.get():
            messagebox.showerror("錯誤", "請設定 API 金鑰")
            return
            
        selection = self.bot_listbox.curselection()
        if not selection:
            messagebox.showerror("錯誤", "請選擇聊天機器人")
            return
            
        self.selected_chatbot_id = self.chatbots[selection[0]]['id']
        
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
        # 這裡可以實現停止邏輯
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.log_warning("驗證已停止")
        
    def run_validation(self):
        """執行驗證（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 載入數據
            self.log_info("正在載入 CSV 數據...")
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
            
            # 輸出結果
            output_file = f"validation_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
            self.log_info(f"匯出結果到: {output_file}")
            self.export_results(results, output_file, stats)
            
            # 更新 UI
            self.log_info("驗證完成，更新結果顯示")
            self.root.after(0, lambda: self.show_results(results, stats, output_file))
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"驗證過程發生錯誤：{str(e)}"))
        finally:
            # 重設 UI 狀態
            self.root.after(0, lambda: self.reset_validation_ui())
            
    def load_csv_data(self):
        """載入 CSV 數據"""
        df = pd.read_csv(self.csv_file_path.get(), encoding='utf-8')
        
        validation_rows = []
        for _, row in df.iterrows():
            validation_row = ValidationRow(
                編號=str(row['編號']),
                提問者=str(row['提問者']),
                問題描述=str(row['問題描述']),
                建議_or_正確答案=str(row.get('建議 or 正確答案 (if have)', '')),
                應參考的文件=str(row.get('應參考的文件', '')),
                應參考的文件段落=str(row.get('應參考的文件段落', ''))
            )
            validation_rows.append(validation_row)
            
        return validation_rows
        
    async def process_validation(self, validation_data):
        """處理驗證"""
        results = []
        
        async with MaiAgentApiClient(self.api_base_url.get(), self.api_key.get(), self.api_logger_callback) as client:
            for i, row in enumerate(validation_data):
                try:
                    # 更新進度
                    self.root.after(0, lambda: self.update_progress(i, len(validation_data), f"處理問題 {row.編號}"))
                    
                    # 處理單個問題
                    result = await self.process_single_question(client, row)
                    results.append(result)
                    
                    self.log_validation_result(row.編號, True, f"回覆長度: {len(result.AI助理回覆)} 字元")
                    
                except Exception as e:
                    self.log_error(f"處理問題 {row.編號} 時發生錯誤: {str(e)}", 'Validation')
                    row.AI助理回覆 = f"錯誤: {str(e)}"
                    results.append(row)
                    
        return results
        
    async def process_single_question(self, client, validation_row):
        """處理單個問題"""
        # 獲取或創建對話
        conversation_id = self.conversation_manager.get_conversation_id(validation_row.提問者)
        
        # 發送問題
        response = await client.send_message(self.selected_chatbot_id, validation_row.問題描述, conversation_id)
        
        # 更新對話 ID
        self.conversation_manager.set_conversation_id(validation_row.提問者, response.conversation_id)
        
        # 填入回覆結果
        validation_row.AI助理回覆 = response.content
        validation_row.引用節點 = json.dumps(response.citation_nodes, ensure_ascii=False)
        validation_row.參考文件 = json.dumps(response.citations, ensure_ascii=False)
        
        # 進行文字比對驗證（固定使用 RAG 增強模式）
        # 動態根據實際回傳的引用節點數量決定片段數
        actual_chunks_count = len(response.citation_nodes) if response.citation_nodes else 0
        
        citation_hit, rag_result = self.text_matcher.check_rag_enhanced_hit(
            response.citation_nodes, 
            validation_row.應參考的文件段落,
            self.similarity_threshold.get(),
            actual_chunks_count,  # 使用實際回傳的節點數量
            self.get_selected_separators()  # 使用用戶選擇的分隔符
        )
        
        # 儲存詳細指標
        validation_row.precision = rag_result.get('precision', 0.0)
        validation_row.recall = rag_result.get('recall', 0.0)
        validation_row.f1_score = rag_result.get('f1_score', 0.0)
        validation_row.hit_rate = rag_result.get('hit_rate', 0.0)
        
        validation_row.引用節點是否命中 = "是" if citation_hit else "否"
        
        file_match, _ = self.text_matcher.check_citation_file_match(
            response.citations,
            validation_row.應參考的文件
        )
        validation_row.參考文件是否正確 = "是" if file_match else "否"
        
        # 評估滿意度
        if citation_hit and file_match:
            validation_row.回覆是否滿意 = "是"
        elif citation_hit or file_match:
            validation_row.回覆是否滿意 = "部分滿意"
        else:
            validation_row.回覆是否滿意 = "否"
            
        return validation_row
        
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
            'total_relevant_chunks': 0
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
            'total_relevant_chunks': total_relevant_chunks,
            'rag_mode_enabled': True  # 固定啟用 RAG 模式
        }
        
    def export_results(self, results, output_file, stats):
        """輸出結果到 CSV（包含分割的段落欄位）"""
        selected_separators = self.get_selected_separators()
        output_data = []
        
        # 先分析所有行，找出最大段落數量
        max_segments = 1
        for row in results:
            segments = self.split_segments_for_export(row.應參考的文件段落, selected_separators)
            max_segments = max(max_segments, len(segments))
        
        self.log_info(f"檢測到最大段落數量: {max_segments}，將創建對應的欄位")
        
        for row in results:
            # 基本欄位
            row_data = {
                '編號': row.編號,
                '提問者': row.提問者,
                '問題描述': row.問題描述,
                'AI 助理回覆': row.AI助理回覆,
                '引用節點': row.引用節點,
                '參考文件': row.參考文件,
                '建議 or 正確答案 (if have)': row.建議_or_正確答案,
                '應參考的文件': row.應參考的文件,
                '應參考的文件段落(原始)': row.應參考的文件段落,  # 保留原始完整內容
                '引用節點是否命中': row.引用節點是否命中,
                '參考文件是否正確': row.參考文件是否正確,
                '回覆是否滿意': row.回覆是否滿意
            }
            
            # 分割段落並添加到獨立欄位
            segments = self.split_segments_for_export(row.應參考的文件段落, selected_separators)
            
            for i in range(max_segments):
                chinese_num = self.get_chinese_number(i + 1)
                column_name = f'應參考的文件段落({chinese_num})'
                
                if i < len(segments):
                    row_data[column_name] = segments[i]
                else:
                    row_data[column_name] = ''  # 空欄位用於沒有那麼多段落的行
            
            output_data.append(row_data)
        
        df = pd.DataFrame(output_data)
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        self.output_file = output_file
        
        # 記錄分割統計
        self.log_info(f"已匯出 {len(results)} 筆記錄，最多 {max_segments} 個段落")
        self.log_info(f"使用的分隔符: {', '.join(selected_separators)}")
        
    def show_results(self, results, stats, output_file):
        """顯示增強結果"""
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
平均段落命中率: {stats['avg_hit_rate']:.2f}%

=== 段落級統計 ===
總預期段落數: {stats['total_expected_segments']}
命中段落數: {stats['total_hit_segments']}
總檢索塊數: {stats['total_retrieved_chunks']}
相關塊數: {stats['total_relevant_chunks']}

=== 文件匹配 ===
參考文件正確率: {stats['file_match_rate']:.2f}%

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
        """增強版日誌記錄方法"""
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
        
        # 更新 GUI 顯示
        def update_log():
            try:
                self.log_text.config(state='normal')
                
                # 根據日誌級別設定顏色標籤
                color_tag = level.lower()
                
                # 安全地檢查標籤是否存在並配置顏色
                try:
                    # 嘗試獲取標籤配置，如果不存在會拋出異常
                    existing_color = self.log_text.tag_cget(color_tag, 'foreground')
                    if not existing_color:
                        raise Exception("標籤未配置顏色")
                except:
                    # 標籤不存在或未配置，創建新標籤
                    if level.upper() == 'ERROR' or level.upper() == 'CRITICAL':
                        self.log_text.tag_config(color_tag, foreground='red')
                    elif level.upper() == 'WARNING':
                        self.log_text.tag_config(color_tag, foreground='orange')
                    elif level.upper() == 'DEBUG':
                        self.log_text.tag_config(color_tag, foreground='gray')
                    else:
                        self.log_text.tag_config(color_tag, foreground='black')
                
                # 插入帶顏色的文字
                start_pos = self.log_text.index(tk.END + "-1c")
                self.log_text.insert(tk.END, f"{formatted_message}\n")
                end_pos = self.log_text.index(tk.END + "-1c")
                self.log_text.tag_add(color_tag, start_pos, end_pos)
                
                # 限制日誌顯示行數（避免過多日誌影響效能）
                line_count = int(self.log_text.index('end-1c').split('.')[0])
                if line_count > 1000:
                    self.log_text.delete('1.0', '500.0')
                
                self.log_text.see(tk.END)
                self.log_text.config(state='disabled')
            except Exception as e:
                # 防止日誌記錄本身出錯
                print(f"日誌更新失敗: {e}")
                
        self.root.after(0, update_log)
    
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
        self.log_info("日誌顯示已清空")
    
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
                import subprocess
                import sys
                
                if sys.platform == "win32":
                    os.startfile(log_dir)
                elif sys.platform == "darwin":  # macOS
                    subprocess.run(["open", str(log_dir)])
                else:  # Linux
                    subprocess.run(["xdg-open", str(log_dir)])
                    
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
  • CSV 格式數據處理
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
            about_window.clipboard_clear()
            about_window.clipboard_append(system_info)
            self.log_info("系統信息已複製到剪貼板")
            messagebox.showinfo("成功", "系統信息已複製到剪貼板")
        
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
            os.startfile(self.output_file)
        else:
            messagebox.showwarning("警告", "結果文件不存在")
            
    def open_results_folder(self):
        """開啟結果資料夾"""
        folder = os.path.dirname(os.path.abspath(self.output_file)) if hasattr(self, 'output_file') else os.getcwd()
        os.startfile(folder)
        
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
                self.max_concurrent.set(config['validation'].getint('max_concurrent_requests', 5))
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
            
            # 載入分隔符設定
            if 'separators' in config:
                separator_section = config['separators']
                for sep_key in self.separator_vars:
                    # 從配置文件讀取，如果不存在則使用當前值
                    saved_value = separator_section.getboolean(sep_key, self.separator_vars[sep_key].get())
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
                'max_concurrent_requests': str(self.max_concurrent.get()),
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
                'export_dir': self.kb_export_dir.get()
            }
            
            # 保存分隔符設定
            config['separators'] = {}
            for sep_key, var in self.separator_vars.items():
                config['separators'][sep_key] = str(var.get())
            
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
        self.kb_base_url_var = tk.StringVar(value="https://api.maiagent.ai/api")
        kb_base_url_entry = ttk.Entry(config_frame, textvariable=self.kb_base_url_var, width=40)
        kb_base_url_entry.grid(row=0, column=1, sticky=tk.W+tk.E, padx=(0, 5))
        
        # 添加URL格式說明
        url_help = ttk.Label(config_frame, text="格式: https://api.maiagent.ai/api 或 http://localhost:8000/api", 
                            font=('TkDefaultFont', 8), foreground='gray')
        url_help.grid(row=0, column=2, sticky=tk.W, padx=(5, 0))
        
        ttk.Label(config_frame, text="API 金鑰:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.kb_api_key_var = tk.StringVar()
        kb_api_key_entry = ttk.Entry(config_frame, textvariable=self.kb_api_key_var, width=40, show="*")
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
        self.kb_export_dir_var = tk.StringVar(value=os.path.join(os.getcwd(), "exports"))
        export_dir_entry = ttk.Entry(export_dir_frame, textvariable=self.kb_export_dir_var, state="readonly")
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
                                               self.api_logger_callback) as client:
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
                                               self.api_logger_callback) as client:
                        return await client.get_organizations()
                
                orgs = loop.run_until_complete(fetch())
                loop.close()
                
                self.root.after(0, lambda: self.update_export_organization_list(orgs))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入失敗：{str(e)}"))
        
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
            self.root.after(0, lambda: self.export_failed(str(e)))
    
    async def export_organization_data(self):
        """匯出組織數據"""
        try:
            async with MaiAgentApiClient(self.org_export_base_url.get(), 
                                       self.org_export_api_key.get(), 
                                       self.api_logger_callback) as client:
                
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
                
                # 生成 CSV
                org_name = None
                for org in self.export_organizations:
                    if org['id'] == self.selected_export_org_id:
                        org_name = org['name']
                        break
                
                if not org_name:
                    org_name = "Unknown"
                
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                csv_filename = f"organization_members_{org_name}_{timestamp}.csv"
                
                self.log_export(f"📄 正在生成 CSV 文件: {csv_filename}")
                
                with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                    fieldnames = ['成員 ID', '姓名', '電子郵件', '是否為擁有者', '建立時間', '所屬群組', '群組權限配置']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    
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
                        
                        # 寫入 CSV
                        writer.writerow({
                            '成員 ID': member_id_str,
                            '姓名': member_name,
                            '電子郵件': member_email,
                            '是否為擁有者': '是' if is_owner else '否',
                            '建立時間': created_at,
                            '所屬群組': '; '.join(member_groups),
                            '群組權限配置': '; '.join(member_group_permissions)
                        })
                
                self.log_export(f"✅ CSV 文件生成完成: {csv_filename}")
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
            messagebox.showerror("錯誤", "請選擇 CSV 文件")
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
            self.root.after(0, lambda: self.deployment_failed(str(e)))
    
    async def execute_batch_import(self):
        """執行批量匯入邏輯"""
        try:
            async with MaiAgentApiClient(self.deploy_base_url.get(), 
                                       self.deploy_api_key.get(), 
                                       self.api_logger_callback) as client:
                
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
        base_url = self.kb_base_url_var.get().strip()
        api_key = self.kb_api_key_var.get().strip()
        
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
                    async with MaiAgentApiClient(base_url, api_key, self.api_logger_callback) as client:
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
        base_url = self.kb_base_url_var.get().strip()
        api_key = self.kb_api_key_var.get().strip()
        
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
                    async with MaiAgentApiClient(base_url, api_key, self.api_logger_callback) as client:
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
            info['file_info'] for info in self.selected_files.values() 
            if info['selected']
        ]
        
        if not selected_files:
            messagebox.showerror("錯誤", "請至少選擇一個文件")
            return
        
        self.kb_export_button.config(state='disabled')
        self.kb_progress_bar['value'] = 0
        
        threading.Thread(target=self.run_kb_export, args=(selected_files,), daemon=True).start()
    
    def run_kb_export(self, selected_files):
        """執行知識庫文件匯出（在背景執行緒中）"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(self.export_kb_files(selected_files))
            loop.close()
            
            if success:
                self.root.after(0, self.kb_export_completed)
            else:
                self.root.after(0, lambda: self.kb_export_failed("匯出過程中發生錯誤"))
                
        except Exception as e:
            self.root.after(0, lambda: self.kb_export_failed(str(e)))
    
    async def export_kb_files(self, selected_files):
        """匯出知識庫文件"""
        try:
            async with MaiAgentApiClient(self.kb_base_url.get(), 
                                       self.kb_api_key.get(), 
                                       self.api_logger_callback) as client:
                
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
                
                self.log_kb(f"📁 創建匯出目錄: {kb_export_path}")
                
                successful_exports = 0
                failed_exports = 0
                
                for i, file_info in enumerate(selected_files):
                    try:
                        file_id = file_info.get('id')
                        file_name = file_info.get('name', f'file_{file_id}')
                        
                        self.log_kb(f"📥 正在下載文件: {file_name}")
                        
                        # 更新進度
                        progress = (i / total_files) * 100
                        self.root.after(0, lambda p=progress: setattr(self.kb_progress_bar, 'value', p))
                        
                        # 下載文件
                        file_data = await client.download_knowledge_base_file(self.selected_kb_id, file_id)
                        
                        # 保存文件
                        file_path = kb_export_path / file_name
                        with open(file_path, 'wb') as f:
                            f.write(file_data)
                        
                        self.log_kb(f"✅ 文件下載成功: {file_name} ({len(file_data)} bytes)")
                        successful_exports += 1
                        
                    except Exception as e:
                        self.log_kb(f"❌ 文件下載失敗: {file_name} - {str(e)}")
                        failed_exports += 1
                
                # 完成進度
                self.root.after(0, lambda: setattr(self.kb_progress_bar, 'value', 100))
                
                self.log_kb(f"📊 匯出完成統計:")
                self.log_kb(f"   成功: {successful_exports} 個文件")
                self.log_kb(f"   失敗: {failed_exports} 個文件")
                self.log_kb(f"   匯出目錄: {kb_export_path}")
                
                return successful_exports > 0
                
        except Exception as e:
            self.log_kb(f"❌ 匯出失敗: {str(e)}")
            return False
    
    def kb_export_completed(self):
        """知識庫匯出完成"""
        self.kb_export_button.config(state='normal')
        messagebox.showinfo("匯出完成", "知識庫文件匯出已成功完成！")
        self.log_info("知識庫文件匯出完成", 'KnowledgeBase')
    
    def kb_export_failed(self, error_message):
        """知識庫匯出失敗"""
        self.kb_export_button.config(state='normal')
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
                        async with MaiAgentApiClient(base_url, api_key, self.api_logger_callback) as client:
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
                self.log_info("MaiAgent 驗證工具正在關閉...")
                self.log_info(f"最終日誌統計: {self.get_log_stats()}")
                self.root.destroy()
            
            self.root.protocol("WM_DELETE_WINDOW", on_closing)
            self.root.mainloop()
        except Exception as e:
            self.log_error(f"應用程式執行錯誤: {str(e)}")
            raise

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
    
    def load_kb_files(self):
        """載入知識庫檔案列表"""
        if not self.current_kb_id and not self.selected_kb_id:
            messagebox.showerror("錯誤", "請先選擇知識庫")
            self.log_kb("❌ 載入檔案失敗 - 未選擇知識庫")
            return
        
        # 獲取API配置
        base_url = self.kb_base_url_var.get().strip()
        api_key = self.kb_api_key_var.get().strip()
        
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
        
        def load_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                self.root.after(0, lambda: self.log_kb(f"🔄 正在載入知識庫檔案 (ID: {kb_id})..."))
                
                async def fetch():
                    async with MaiAgentApiClient(base_url, api_key, self.api_logger_callback) as client:
                        files = await client.get_knowledge_base_files(kb_id)
                        self.root.after(0, lambda: self.log_kb(f"📋 成功獲取 {len(files)} 個檔案"))
                        return files
                
                files = loop.run_until_complete(fetch())
                loop.close()
                
                self.root.after(0, lambda: self.update_files_list(files))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda: self.log_kb(f"❌ 載入檔案失敗: {error_msg}"))
                self.root.after(0, lambda: messagebox.showerror("錯誤", f"載入檔案列表失敗：{error_msg}"))
        
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