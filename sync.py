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
    """调用 getbiji API，支持重试 - 根据官方文档修正认证方式"""
    # 确保 path 以 / 开头
    if path and not path.startswith("/"):
        path = "/" + path
    
    url = f"{GETBIJI_BASE_URL}{path}"
    log_info(f"请求 getbiji: {method} {url}")
    
    # 根据官方文档：不需要 Bearer 前缀，直接传 API Key
    headers = {
        "X-Client-ID": GETBIJI_CLIENT_ID,
        "Authorization": GETBIJI_API_KEY,  # 直接使用 API Key，不需要 "Bearer " 前缀
        "Content-Type": "application/json"
    }
    
    for attempt in range(max_retries):
        try:
            r = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
            log_info(f"响应状态码: {r.status_code}")
            
            if r.status_code == 401:
                log_error(f"认证失败 (401)，请检查 API Key 和 Client ID")
                try:
                    error_data = r.json()
                    log_error(f"错误详情: {error_data}")
                except:
                    log_error(f"响应内容: {r.text[:200]}")
                break
            
            r.raise_for_status()
            
            ct = (r.headers.get("content-type") or "").lower()
            if "application/json" in ct:
                response_data = r.json()
                return response_data
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

def test_notion_connection():
    """测试 Notion 连接和数据库访问"""
    log_info("测试 Notion 连接...")
    
    # 测试1：验证 Token
    log_info("测试 Notion Token 有效性...")
    url = "https://api.notion.com/v1/users/me"
    try:
        response = requests.get(url, headers=notion_headers(), timeout=30)
        if response.status_code == 200:
            user_data = response.json()
            log_info(f"✅ Notion Token 有效，用户: {user_data.get('name', '未知')}")
        else:
            log_error(f"❌ Notion Token 无效 ({response.status_code}): {response.text[:200]}")
            return False
    except Exception as e:
        log_error(f"❌ Notion Token 测试失败: {str(e)}")
        return False
    
    # 测试2：验证数据库访问权限
    log_info(f"测试 Notion 数据库访问 (ID: {NOTION_DATABASE_ID[:8]}...)")
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
    try:
        response = requests.get(url, headers=notion_headers(), timeout=30)
        if response.status_code == 200:
            db_data = response.json()
            db_title = "无标题"
            if "title" in db_data and db_data["title"]:
                if isinstance(db_data["title"], list) and db_data["title"]:
                    db_title = db_data["title"][0].get("plain_text", "无标题")
            log_info(f"✅ Notion 数据库连接成功: {db_title}")
            log_info(f"数据库属性: {list(db_data.get('properties', {}).keys())}")
            return True
        elif response.status_code == 404:
            log_error("❌ Notion 数据库 404 错误: 数据库不存在或集成没有权限访问")
            log_error("请检查:")
            log_error("1. 数据库ID是否正确")
            log_error("2. 在Notion中，数据库是否已与集成共享")
            log_error("3. 在 https://www.notion.so/my-integrations 中查看集成权限")
            return False
        elif response.status_code == 403:
            log_error("❌ Notion 数据库 403 错误: 权限不足")
            log_error("请在Notion中邀请集成访问数据库:")
            log_error("1. 打开数据库页面")
            log_error("2. 点击右上角 Share")
            log_error("3. 在 'Add people, emails, or groups' 中输入您的集成名称")
            return False
        else:
            log_error(f"❌ Notion 数据库访问失败 ({response.status_code}): {response.text[:200]}")
            return False
    except Exception as e:
        log_error(f"❌ Notion 数据库连接测试失败: {str(e)}")
        return False

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
        
        response = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
        
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                log_info(f"找到已存在的页面: {results[0]['id'][:8]}...")
            return results[0]["id"] if results else None
        elif response.status_code == 404:
            log_error(f"查询 Notion 失败: 数据库不存在 (404)")
            return None
        else:
            log_error(f"查询 Notion 失败 ({response.status_code}): {response.text[:200]}")
            return None
        
    except Exception as e:
        log_error(f"查询 Notion 异常: {str(e)}")
        return None

def notion_create_page(note):
    """在 Notion 中创建新页面"""
    try:
        # 构建 Notion 页面属性
        props = {}
        
        # 标题
        title = note.get("title") or note.get("name") or "无标题"
        if not isinstance(title, str):
            title = str(title)
        props["Name"] = {"title": [{"text": {"content": title[:200]}}]}
        
        # NoteID（用于去重）
        noteid = str(note.get("id") or note.get("note_id") or note.get("noteId") or "")
        if noteid:
            props["NoteID"] = {"rich_text": [{"text": {"content": noteid[:200]}}]}
        
        # 创建时间
        created = note.get("created_at") or note.get("createdAt") or note.get("created_time")
        if created:
            props["CreatedAt"] = {"date": {"start": created}}
        
        # 更新时间
        updated = note.get("updated_at") or note.get("updatedAt") or note.get("updated_time")
        if updated:
            props["UpdatedAt"] = {"date": {"start": updated}}
        
        # 构建简单的页面内容
        content = note.get("content") or ""
        children = []
        if content:
            # 将内容分割为多个段落
            content_chunks = [content[i:i+2000] for i in range(0, min(len(content), 10000), 2000)]
            for chunk in content_chunks[:3]:  # 限制最多3个段落
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{
                            "type": "text",
                            "text": {"content": chunk}
                        }]
                    }
                })
        
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": props,
        }
        
        if children:
            payload["children"] = children
        
        log_info(f"创建 Notion 页面: {title[:50]}...")
        
        response = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
        
        if response.status_code == 200:
            page_id = response.json().get("id")
            page_url = response.json().get("url", "")
            log_info(f"✅ 成功创建 Notion 页面")
            log_info(f"   页面ID: {page_id[:8]}...")
            if page_url:
                log_info(f"   页面URL: {page_url}")
            return page_id
        elif response.status_code == 404:
            log_error(f"创建 Notion 页面失败: 数据库不存在 (404)")
            return None
        else:
            log_error(f"创建 Notion 页面失败 ({response.status_code}): {response.text[:200]}")
            return None
        
    except Exception as e:
        log_error(f"创建 Notion 页面异常: {str(e)}")
        return None

def notion_update_page(page_id, note):
    """更新 Notion 页面"""
    try:
        # 构建更新属性
        props = {}
        
        # 标题
        title = note.get("title") or note.get("name") or "无标题"
        if not isinstance(title, str):
            title = str(title)
        props["Name"] = {"title": [{"text": {"content": title[:200]}}]}
        
        # 更新时间
        updated = note.get("updated_at") or note.get("updatedAt") or note.get("updated_time")
        if updated:
            props["UpdatedAt"] = {"date": {"start": updated}}
        
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": props}
        
        log_info(f"更新 Notion 页面: {page_id[:8]}...")
        
        response = requests.patch(url, headers=notion_headers(), json=payload, timeout=30)
        
        if response.status_code == 200:
            log_info(f"✅ 成功更新 Notion 页面: {page_id[:8]}...")
            return True
        else:
            log_error(f"更新 Notion 页面失败 ({response.status_code}): {response.text[:200]}")
            return False
        
    except Exception as e:
        log_error(f"更新 Notion 页面异常: {str(e)}")
        return False

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
    
    # 测试 Notion 连接
    if not test_notion_connection():
        log_error("Notion 连接测试失败，同步终止")
        sys.exit(1)
    
    try:
        # 获取 getbiji 笔记列表
        log_info("正在从 getbiji 获取笔记...")
        
        # 根据官方文档，使用 since_id=0 获取所有笔记
        params = {"since_id": 0}
        data = getbiji_request("GET", "/resource/note/list", params=params)
        
        # 检查API响应数据结构
        if not data or not isinstance(data, dict):
            log_error(f"API响应格式异常: {type(data)}")
            sys.exit(1)
        
        # 从返回的数据结构中提取笔记
        notes = []
        if "data" in data and isinstance(data["data"], dict):
            if "notes" in data["data"]:
                notes = data["data"]["notes"]
                log_info(f"从 data['data']['notes'] 找到 {len(notes)} 条笔记")
            else:
                log_warning(f"data['data'] 中没有 notes 键，尝试其他键")
        else:
            # 尝试其他可能的键
            notes = data.get("data") or data.get("list") or data.get("notes") or []
            log_info(f"从其他键找到 {len(notes)} 条笔记")
        
        if not isinstance(notes, list):
            log_error(f"笔记数据不是列表类型: {type(notes)}")
            sys.exit(1)
        
        if not notes:
            log_warning("未获取到任何笔记")
            sys.exit(0)
        
        log_info(f"获取到 {len(notes)} 条笔记")
        
        # 只同步前3条进行测试
        synced = 0
        failed = 0
        for i, note in enumerate(notes[:3]):
            try:
                start_time = time.time()
                note_id = note.get('id', 'unknown')
                note_title = note.get('title', '无标题')[:50]
                log_info(f"【开始处理】第 {i+1} 条笔记 (ID: {note_id}, 标题: {note_title}...)")
                
                # 检查是否已存在
                existing_page_id = notion_query_by_noteid(str(note_id))
                time.sleep(0.3)  # 小延迟
                
                if existing_page_id:
                    # 更新现有页面
                    log_info(f"笔记已存在，尝试更新: {note_id}")
                    if notion_update_page(existing_page_id, note):
                        synced += 1
                        log_info(f"✓ 更新成功: {note_title}...")
                    else:
                        failed += 1
                        log_error(f"✗ 更新失败: {note_title}...")
                else:
                    # 创建新页面
                    log_info(f"创建新笔记: {note_id}")
                    if notion_create_page(note):
                        synced += 1
                        log_info(f"✓ 创建成功: {note_title}...")
                    else:
                        failed += 1
                        log_error(f"✗ 创建失败: {note_title}...")
                
                end_time = time.time()
                log_info(f"【完成处理】第 {i+1} 条笔记，耗时: {end_time - start_time:.2f}秒")
                
                # 避免速率限制
                time.sleep(0.5)
                
            except Exception as e:
                failed += 1
                log_error(f"处理第 {i+1} 条笔记失败: {str(e)}")
                log_error(f"错误详情: {traceback.format_exc()}")
                continue
        
        log_info("=" * 50)
        log_info(f"同步完成!")
        log_info(f"成功: {synced} 条，失败: {failed} 条，总计: {len(notes[:3])} 条")
        log_info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_info("=" * 50)
        
        if synced == 0:
            log_error("没有成功同步任何笔记")
            sys.exit(1)
        
    except Exception as e:
        log_error(f"同步过程失败: {str(e)}")
        log_error(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
