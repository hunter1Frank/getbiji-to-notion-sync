#!/usr/bin/env python3
"""
同步 Getbiji 笔记到 Notion 数据库
在 GitHub Actions 中运行
"""

import os
import time
import requests
import sys
import traceback
from datetime import datetime

# 环境变量
GETBIJI_API_KEY = os.environ.get("GETBIJI_API_KEY", "").strip()
GETBIJI_CLIENT_ID = os.environ.get("GETBIJI_CLIENT_ID", "").strip()
GETBIJI_BASE_URL = os.environ.get("GETBIJI_BASE_URL", "").rstrip("/")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()

# 日志函数
def log_info(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: {message}")

def log_error(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {message}", file=sys.stderr)

def log_warning(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARNING: {message}")

def getbiji_request(method, path, params=None, json=None, max_retries=3):
    """调用 getbiji API，支持重试"""
    # 确保路径以斜杠开头
    if not path.startswith("/"):
        path = "/" + path
    
    url = f"{GETBIJI_BASE_URL}{path}"
    log_info(f"请求 getbiji: {method} {url}")
    
    # 根据官方文档，使用正确的认证头
    headers = {
        "X-Client-ID": GETBIJI_CLIENT_ID,
        "Authorization": GETBIJI_API_KEY,
        "Content-Type": "application/json"
    }
    
    for attempt in range(max_retries):
        try:
            r = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
            log_info(f"响应状态码: {r.status_code}")
            
            if r.status_code == 401:
                log_error(f"认证失败 (401)，请检查 X-Client-ID 和 Authorization 是否正确")
                try:
                    error_data = r.json()
                    log_error(f"错误详情: {error_data}")
                except:
                    log_error(f"响应内容: {r.text[:200]}")
                break
            
            r.raise_for_status()
            
            ct = (r.headers.get("content-type") or "").lower()
            if "application/json" in ct:
                return r.json()
            else:
                return {"raw": r.text}
                
        except requests.exceptions.RequestException as e:
            log_warning(f"请求失败: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    
    raise RuntimeError(f"Getbiji API 调用失败")

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

def notion_query_by_noteid(noteid):
    """查询 Notion 数据库中是否已存在该笔记"""
    if not noteid or not NOTION_DATABASE_ID:
        return None
    
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
        payload = {
            "filter": {
                "property": "NoteID",
                "rich_text": {"equals": str(noteid)},
            }
        }
        
        r = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
        r.raise_for_status()
        
        results = r.json().get("results", [])
        return results[0]["id"] if results else None
        
    except Exception as e:
        log_error(f"查询 Notion 失败: {str(e)}")
        return None

def notion_create_page(props):
    """在 Notion 中创建新页面"""
    try:
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": props,
        }
        
        r = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
        r.raise_for_status()
        
        page_id = r.json().get("id")
        log_info(f"成功创建 Notion 页面: {page_id[:8]}...")
        return page_id
        
    except Exception as e:
        log_error(f"创建 Notion 页面失败: {str(e)}")
        return None

def notion_update_page(page_id, props):
    """更新 Notion 页面"""
    try:
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": props}
        
        r = requests.patch(url, headers=notion_headers(), json=payload, timeout=30)
        r.raise_for_status()
        
        log_info(f"成功更新 Notion 页面: {page_id[:8]}...")
        return True
        
    except Exception as e:
        log_error(f"更新 Notion 页面失败: {str(e)}")
        return False

def to_notion_props(note):
    """将 getbiji 笔记转换为 Notion 属性"""
    # 确保标题是字符串
    title = note.get("title") or note.get("name") or note.get("summary") or "无标题"
    if not isinstance(title, str):
        title = str(title)
    
    # 确保noteid是字符串
    noteid = note.get("id") or note.get("note_id") or note.get("noteId") or ""
    if noteid is None:
        noteid = ""
    noteid = str(noteid)
    
    # 处理时间字段
    created = note.get("created_at") or note.get("createdAt") or note.get("created_time")
    updated = note.get("updated_at") or note.get("updatedAt") or note.get("updated_time")
    
    # 处理源 URL
    source = note.get("url") or note.get("source_url") or note.get("sourceUrl")
    
    # 处理标签
    tags = note.get("tags") or []
    if isinstance(tags, str):
        tags = [tag.strip() for tag in tags.split(",") if tag.strip()]
    
    # 构建 Notion 属性
    props = {
        "Name": {"title": [{"text": {"content": title[:200]}}]},
        "NoteID": {"rich_text": [{"text": {"content": noteid[:200]}}]},
    }
    
    # 添加创建时间
    if created:
        props["CreatedAt"] = {"date": {"start": created}}
    
    # 添加更新时间
    if updated:
        props["UpdatedAt"] = {"date": {"start": updated}}
    
    # 添加源 URL
    if source:
        props["SourceURL"] = {"url": source}
    
    # 添加标签
    if isinstance(tags, list) and tags:
        props["Tags"] = {"multi_select": [{"name": str(t)[:100]} for t in tags[:10]]}
    
    return noteid, props

def main():
    """主函数"""
    log_info("=" * 50)
    log_info("开始同步 get笔记 到 Notion")
    log_info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_info("=" * 50)
    
    # 验证所有必要的环境变量
    required_vars = {
        "GETBIJI_API_KEY": (GETBIJI_API_KEY, 10),
        "GETBIJI_CLIENT_ID": (GETBIJI_CLIENT_ID, 10),
        "GETBIJI_BASE_URL": (GETBIJI_BASE_URL, 30),
        "NOTION_TOKEN": (NOTION_TOKEN, 10),
        "NOTION_DATABASE_ID": (NOTION_DATABASE_ID, 8)
    }
    
    missing_vars = []
    for var_name, (var_value, preview_len) in required_vars.items():
        if not var_value:
            missing_vars.append(var_name)
        else:
            log_info(f"{var_name}: {var_value[:preview_len]}...")
    
    if missing_vars:
        log_error(f"缺少必要的环境变量: {', '.join(missing_vars)}")
        sys.exit(1)
    
    try:
        # 获取 getbiji 笔记列表
        log_info("正在从 getbiji 获取笔记...")
        data = getbiji_request("GET", "/resource/note/list")
        log_info(f"API 响应: {data}")
        
        # 提取笔记列表
        notes = data.get("data") or data.get("list") or data.get("notes") or []
        
        if not notes:
            log_warning("未获取到任何笔记")
            sys.exit(0)
        
        log_info(f"获取到 {len(notes)} 条笔记")
        
        # 打印第一条笔记的结构用于调试
        if notes:
            log_info(f"第一条笔记结构: {notes[0]}")
        
        # 同步前20条（避免限流）
        synced = 0
        for i, note in enumerate(notes[:20]):
            try:
                start_time = time.time()
                note_id = note.get('id', 'unknown')
                log_info(f"【开始处理】第 {i+1} 条笔记 (ID: {note_id})")
                log_info(f"笔记数据: {note}")
                
                noteid, props = to_notion_props(note)
                if not noteid:
                    log_warning(f"跳过第 {i+1} 条笔记: 缺少 NoteID")
                    continue
                
                # 检查是否已存在
                existing_page_id = notion_query_by_noteid(noteid)
                time.sleep(0.1)
                
                if existing_page_id:
                    # 更新现有页面
                    if notion_update_page(existing_page_id, props):
                        synced += 1
                        log_info(f"✓ 更新笔记: {noteid[:20]}...")
                else:
                    # 创建新页面
                    if notion_create_page(props):
                        synced += 1
                        log_info(f"✓ 创建笔记: {noteid[:20]}...")
                
                end_time = time.time()
                log_info(f"【完成处理】第 {i+1} 条笔记，耗时: {end_time - start_time:.2f}秒")
                
                # 避免速率限制
                time.sleep(0.3)
                
            except Exception as e:
                log_error(f"处理第 {i+1} 条笔记失败: {str(e)}")
                log_error(f"错误详情: {traceback.format_exc()}")
                continue
        
        log_info("=" * 50)
        log_info(f"同步完成! 成功处理 {synced} 条笔记")
        log_info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_info("=" * 50)
        
    except Exception as e:
        log_error(f"同步过程失败: {str(e)}")
        log_error(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
