#!/usr/bin/env python3
"""
同步 Getbiji 笔记到 Notion 数据库 - 支持完整分页和标签同步
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
    if path and not path.startswith("/"):
        path = "/" + path
    
    url = f"{GETBIJI_BASE_URL}{path}"
    log_info(f"请求 getbiji: {method} {url}")
    
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

def get_all_notes():
    """获取所有笔记，支持分页"""
    all_notes = []
    page = 1
    page_size = 50  # 每页获取50条，减少请求次数
    
    while True:
        try:
            log_info(f"正在获取第 {page} 页笔记，每页 {page_size} 条...")
            
            # 尝试不同的分页参数组合
            params = {
                "page": page,
                "page_size": page_size,
                "since_id": 0
            }
            
            data = getbiji_request("GET", "/resource/note/list", params=params)
            
            # 解析响应数据
            notes_batch = []
            
            # 尝试多种可能的响应结构
            if isinstance(data, dict):
                # 结构1: data.data.notes
                if "data" in data and isinstance(data["data"], dict):
                    if "notes" in data["data"]:
                        notes_batch = data["data"]["notes"]
                    elif "list" in data["data"]:
                        notes_batch = data["data"]["list"]
                    elif "items" in data["data"]:
                        notes_batch = data["data"]["items"]
                # 结构2: data.notes
                elif "notes" in data:
                    notes_batch = data["notes"]
                elif "list" in data:
                    notes_batch = data["list"]
                elif "items" in data:
                    notes_batch = data["items"]
                # 结构3: 直接是数组
                elif isinstance(data.get("data"), list):
                    notes_batch = data["data"]
            
            # 如果没有找到笔记，尝试直接使用响应
            if not notes_batch and isinstance(data, list):
                notes_batch = data
            
            if not notes_batch:
                log_warning(f"第 {page} 页没有找到笔记数据")
                break
            
            log_info(f"第 {page} 页获取到 {len(notes_batch)} 条笔记")
            all_notes.extend(notes_batch)
            
            # 检查是否还有更多数据
            # 如果获取的数量小于请求的page_size，说明是最后一页
            if len(notes_batch) < page_size:
                log_info(f"获取到 {len(notes_batch)} 条笔记，小于请求的 {page_size} 条，可能是最后一页")
                break
            
            # 检查响应中是否有分页指示器
            if isinstance(data, dict):
                if "has_more" in data and not data["has_more"]:
                    log_info("API 返回 has_more: false，没有更多数据")
                    break
                if "next_cursor" in data and not data["next_cursor"]:
                    log_info("API 返回 next_cursor 为空，没有更多数据")
                    break
                if "total" in data and len(all_notes) >= data["total"]:
                    log_info(f"已获取 {len(all_notes)} 条笔记，达到总数 {data['total']}")
                    break
            
            # 增加页码，继续获取下一页
            page += 1
            
            # 避免请求过于频繁
            time.sleep(0.5)
            
        except Exception as e:
            log_error(f"获取第 {page} 页笔记失败: {str(e)}")
            break
    
    return all_notes

def notion_headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

def get_notion_database_properties():
    """获取数据库的属性和结构"""
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
        response = requests.get(url, headers=notion_headers(), timeout=30)
        
        if response.status_code == 200:
            db_data = response.json()
            properties = db_data.get("properties", {})
            
            # 查找标题属性
            title_property = None
            for prop_name, prop_data in properties.items():
                if prop_data.get("type") == "title":
                    title_property = prop_name
                    break
            
            log_info(f"数据库标题属性: {title_property or '未找到'}")
            log_info(f"数据库所有属性: {list(properties.keys())}")
            
            return {
                "properties": properties,
                "title_property": title_property
            }
        else:
            log_error(f"获取数据库结构失败 ({response.status_code}): {response.text[:200]}")
            return None
    except Exception as e:
        log_error(f"获取数据库结构异常: {str(e)}")
        return None

def notion_query_by_noteid(noteid, db_info):
    """查询 Notion 数据库中是否已存在该笔记"""
    if not noteid or not NOTION_DATABASE_ID:
        return None
    
    # 检查数据库中是否有 NoteID 属性
    properties = db_info.get("properties", {})
    if "NoteID" not in properties:
        log_warning("数据库中没有 NoteID 属性，跳过去重检查")
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
        else:
            log_error(f"查询 Notion 失败 ({response.status_code}): {response.text[:200]}")
            return None
        
    except Exception as e:
        log_error(f"查询 Notion 异常: {str(e)}")
        return None

def extract_tags(note):
    """从笔记数据中提取标签"""
    tags = []
    
    # 尝试多种可能的标签数据结构
    if isinstance(note, dict):
        # 结构1: 直接有tags字段
        if "tags" in note and isinstance(note["tags"], list):
            for tag in note["tags"]:
                if isinstance(tag, dict) and "name" in tag:
                    tag_name = tag["name"]
                    if tag_name and tag_name not in tags:
                        tags.append(tag_name)
                elif isinstance(tag, str) and tag not in tags:
                    tags.append(tag)
        
        # 结构2: 在metadata中
        elif "metadata" in note and isinstance(note["metadata"], dict):
            if "tags" in note["metadata"] and isinstance(note["metadata"]["tags"], list):
                for tag in note["metadata"]["tags"]:
                    if isinstance(tag, dict) and "name" in tag:
                        tag_name = tag["name"]
                        if tag_name and tag_name not in tags:
                            tags.append(tag_name)
                    elif isinstance(tag, str) and tag not in tags:
                        tags.append(tag)
        
        # 结构3: 在properties中
        elif "properties" in note and isinstance(note["properties"], dict):
            if "tags" in note["properties"]:
                tags_data = note["properties"]["tags"]
                if isinstance(tags_data, list):
                    for tag in tags_data:
                        if isinstance(tag, dict) and "name" in tag:
                            tag_name = tag["name"]
                            if tag_name and tag_name not in tags:
                                tags.append(tag_name)
                        elif isinstance(tag, str) and tag not in tags:
                            tags.append(tag)
    
    return tags

def notion_create_page(note, db_info):
    """在 Notion 中创建新页面"""
    try:
        properties = db_info.get("properties", {})
        title_property = db_info.get("title_property", "名称")
        
        # 准备属性
        props = {}
        
        # 1. 标题属性
        title = note.get("title") or note.get("name") or "无标题"
        if not isinstance(title, str):
            title = str(title)
        
        if title_property and title_property in properties:
            props[title_property] = {"title": [{"text": {"content": title[:200]}}]}
        else:
            log_error(f"标题属性 '{title_property}' 不存在于数据库中")
            return None
        
        # 2. NoteID 属性
        noteid = str(note.get("id") or note.get("note_id") or note.get("noteId") or "")
        if noteid and "NoteID" in properties:
            props["NoteID"] = {"rich_text": [{"text": {"content": noteid[:200]}}]}
        
        # 3. 创建时间属性
        created = note.get("created_at") or note.get("createdAt") or note.get("created_time")
        if created and "CreatedAt" in properties:
            props["CreatedAt"] = {"date": {"start": created}}
        
        # 4. 更新时间属性
        updated = note.get("updated_at") or note.get("updatedAt") or note.get("updated_time")
        if updated and "UpdatedAt" in properties:
            props["UpdatedAt"] = {"date": {"start": updated}}
        
        # 5. 标签属性 - 使用提取函数
        tags = extract_tags(note)
        if tags:
            # 尝试多种可能的标签属性名
            tag_property_names = ["Tags", "标签", "Tag", "分类", "Categories"]
            tag_property_found = None
            
            for prop_name in tag_property_names:
                if prop_name in properties:
                    tag_property_found = prop_name
                    break
            
            if tag_property_found:
                # 限制标签数量，避免Notion API限制
                max_tags = 10
                if len(tags) > max_tags:
                    log_warning(f"笔记有 {len(tags)} 个标签，只取前 {max_tags} 个")
                    tags = tags[:max_tags]
                
                props[tag_property_found] = {"multi_select": [{"name": tag} for tag in tags]}
                log_info(f"提取到 {len(tags)} 个标签: {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
            else:
                log_warning(f"未找到标签属性，可用属性名: {list(properties.keys())}")
        
        # 构建页面内容
        content = note.get("content") or note.get("body") or ""
        children = []
        if content:
            # 将内容分割为多个段落，确保每个段落不超过1990字符
            content_chunks = []
            chunk_size = 1990
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i+chunk_size]
                content_chunks.append(chunk)
            
            for chunk in content_chunks[:3]:
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
        log_info(f"使用的属性: {list(props.keys())}")
        
        response = requests.post(url, headers=notion_headers(), json=payload, timeout=30)
        
        if response.status_code == 200:
            page_data = response.json()
            page_id = page_data.get("id")
            page_url = page_data.get("url", "")
            log_info(f"✅ 成功创建 Notion 页面")
            log_info(f"   页面ID: {page_id[:8]}...")
            if page_url:
                log_info(f"   页面URL: {page_url}")
            return page_id
        else:
            log_error(f"创建 Notion 页面失败 ({response.status_code}): {response.text[:200]}")
            return None
        
    except Exception as e:
        log_error(f"创建 Notion 页面异常: {str(e)}")
        return None

def main():
    """主函数"""
    log_info("=" * 50)
    log_info("开始同步 get笔记 到 Notion（支持完整分页和标签同步）")
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
    
    # 获取数据库结构
    db_info = get_notion_database_properties()
    if not db_info:
        log_error("无法获取数据库结构，同步终止")
        sys.exit(1)
    
    try:
        # 获取所有笔记（支持分页）
        log_info("正在从 getbiji 获取所有笔记（支持分页）...")
        notes = get_all_notes()
        
        if not isinstance(notes, list):
            log_error(f"笔记数据不是列表类型: {type(notes)}")
            sys.exit(1)
        
        log_info(f"总共获取到 {len(notes)} 条笔记")
        
        if not notes:
            log_warning("未获取到任何笔记")
            sys.exit(0)
        
        # 同步所有笔记
        synced = 0
        failed = 0
        skipped = 0
        
        for i, note in enumerate(notes):
            try:
                start_time = time.time()
                note_id = note.get('id', 'unknown')
                note_title = note.get('title', '无标题')[:50]
                log_info(f"【开始处理】第 {i+1}/{len(notes)} 条笔记 (ID: {note_id}, 标题: {note_title}...)")
                
                # 检查是否已存在
                existing_page_id = notion_query_by_noteid(str(note_id), db_info)
                time.sleep(0.3)
                
                if existing_page_id:
                    log_info(f"笔记已存在，跳过: {note_id}")
                    skipped += 1
                else:
                    # 创建新页面
                    log_info(f"创建新笔记: {note_id}")
                    if notion_create_page(note, db_info):
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
        log_info(f"总计: {len(notes)} 条笔记")
        log_info(f"成功创建: {synced} 条")
        log_info(f"已存在跳过: {skipped} 条")
        log_info(f"失败: {failed} 条")
        log_info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_info("=" * 50)
        
        if synced == 0 and failed > 0:
            log_error("没有成功同步任何新笔记")
            sys.exit(1)
        
    except Exception as e:
        log_error(f"同步过程失败: {str(e)}")
        log_error(f"错误详情: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
