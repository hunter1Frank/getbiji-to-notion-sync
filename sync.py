#!/usr/bin/env python3
"""
同步 Getbiji 笔记到 Notion 数据库 - 修复原文链接同步问题
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
GETBIJI_BASE_URL = os.environ.get("GETBIJI_BASE_URL", "").strip()
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
    
    # 清理 Base URL
    base_url = GETBIJI_BASE_URL.rstrip("/")
    url = f"{base_url}{path}"
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
    """获取所有笔记（支持分页）"""
    all_notes = []
    next_cursor = 0
    page_count = 0
    
    while True:
        page_count += 1
        log_info(f"正在获取第 {page_count} 页笔记，游标: {next_cursor}")
        
        try:
            params = {"since_id": next_cursor}
            data = getbiji_request("GET", "/resource/note/list", params=params)
            
            if not data or not isinstance(data, dict):
                log_error(f"API响应格式异常: {type(data)}")
                break
            
            # 调试：查看API返回的数据结构
            if page_count == 1:
                log_info(f"API响应keys: {list(data.keys())}")
                if "data" in data and isinstance(data["data"], dict):
                    log_info(f"data['data'] keys: {list(data['data'].keys())}")
                    if "notes" in data["data"] and data["data"]["notes"]:
                        first_note = data["data"]["notes"][0]
                        log_info(f"第一条笔记结构 keys: {list(first_note.keys())[:20]}")
            
            notes = []
            if "data" in data and isinstance(data["data"], dict):
                if "notes" in data["data"]:
                    notes = data["data"]["notes"]
                    log_info(f"第 {page_count} 页获取到 {len(notes)} 条笔记")
                else:
                    log_warning(f"data['data'] 中没有 notes 键，尝试其他键")
            else:
                notes = data.get("data") or data.get("list") or data.get("notes") or []
                log_info(f"从其他键找到 {len(notes)} 条笔记")
            
            if not isinstance(notes, list):
                log_error(f"笔记数据不是列表类型: {type(notes)}")
                break
            
            all_notes.extend(notes)
            
            has_more = False
            next_cursor_value = None
            
            if "data" in data and isinstance(data["data"], dict):
                has_more = data["data"].get("has_more", False)
                next_cursor_value = data["data"].get("next_cursor")
            else:
                has_more = data.get("has_more", False)
                next_cursor_value = data.get("next_cursor")
            
            log_info(f"分页信息 - has_more: {has_more}, next_cursor: {next_cursor_value}")
            
            if not has_more or not next_cursor_value:
                log_info(f"已获取所有笔记，共 {len(all_notes)} 条")
                break
            
            try:
                next_cursor = int(next_cursor_value)
                if next_cursor <= 0:
                    log_warning(f"无效的游标值: {next_cursor_value}")
                    break
            except (ValueError, TypeError):
                log_warning(f"无法解析游标值: {next_cursor_value}")
                break
            
            time.sleep(0.5)
            
        except Exception as e:
            log_error(f"获取第 {page_count} 页笔记失败: {str(e)}")
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

def notion_create_page(note, db_info):
    """在 Notion 中创建新页面"""
    try:
        properties = db_info.get("properties", {})
        title_property = db_info.get("title_property", "名称")
        
        props = {}
        
        title = note.get("title") or note.get("name") or "无标题"
        if not isinstance(title, str):
            title = str(title)
        
        if title_property and title_property in properties:
            props[title_property] = {"title": [{"text": {"content": title[:200]}}]}
        else:
            log_error(f"标题属性 '{title_property}' 不存在于数据库中")
            return None
        
        noteid = str(note.get("id") or note.get("note_id") or note.get("noteId") or "")
        if noteid and "NoteID" in properties:
            props["NoteID"] = {"rich_text": [{"text": {"content": noteid[:200]}}]}
        
        created = note.get("created_at") or note.get("createdAt") or note.get("created_time")
        if created and "CreatedAt" in properties:
            props["CreatedAt"] = {"date": {"start": created}}
        
        updated = note.get("updated_at") or note.get("updatedAt") or note.get("updated_time")
        if updated and "UpdatedAt" in properties:
            props["UpdatedAt"] = {"date": {"start": updated}}
        
        # 标签处理
        tags = note.get("tags") or []
        tag_property_name = None
        for prop_name in ["Tags", "标签", "Tag", "categories"]:
            if prop_name in properties:
                tag_property_name = prop_name
                break
        
        if tags and tag_property_name:
            tag_names = []
            for tag in tags:
                if isinstance(tag, dict) and "name" in tag:
                    tag_name = tag["name"]
                    if tag_name and tag_name not in tag_names:
                        tag_names.append(tag_name)
                elif isinstance(tag, str) and tag not in tag_names:
                    tag_names.append(tag)
            
            if tag_names:
                max_tags = 10
                if len(tag_names) > max_tags:
                    log_warning(f"笔记有 {len(tag_names)} 个标签，只取前 {max_tags} 个")
                    tag_names = tag_names[:max_tags]
                
                prop_type = properties[tag_property_name].get("type")
                if prop_type == "multi_select":
                    props[tag_property_name] = {"multi_select": [{"name": tag} for tag in tag_names]}
                elif prop_type == "select":
                    props[tag_property_name] = {"select": {"name": tag_names[0]}}
                else:
                    props[tag_property_name] = {"rich_text": [{"text": {"content": ", ".join(tag_names[:3])}}]}
                
                log_info(f"提取到 {len(tag_names)} 个标签: {', '.join(tag_names[:5])}{'...' if len(tag_names) > 5 else ''}")
        
        # 原文链接处理 - 增强调试
        log_info(f"调试: 检查笔记中的链接字段")
        
        # 尝试多种可能的字段名
        url_fields_to_check = ["url", "source_url", "link_url", "source", "link", "original_url", "web_url"]
        
        source_url = None
        for field_name in url_fields_to_check:
            if field_name in note:
                source_url = note.get(field_name)
                log_info(f"  找到字段 '{field_name}': {source_url[:80] if source_url and len(source_url) > 80 else source_url}")
                break
        
        if source_url:
            url_property_name = None
            for prop_name in ["SourceURL", "原文链接", "URL", "Link", "Source", "原文"]:
                if prop_name in properties:
                    url_property_name = prop_name
                    break
            
            if url_property_name:
                props[url_property_name] = {"url": source_url}
                log_info(f"✅ 原文链接已设置: {source_url[:50]}...")
            else:
                log_warning("数据库中没有找到合适的URL属性")
        else:
            log_warning("笔记中没有找到原文链接字段")
            # 调试：显示笔记的所有键
            log_info(f"笔记可用字段: {list(note.keys())}")
        
        # 构建页面内容
        content = note.get("content") or ""
        children = []
        if content:
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
    log_info("开始同步 get笔记 到 Notion（修复原文链接问题）")
    log_info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_info("=" * 50)
    
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
    
    db_info = get_notion_database_properties()
    if not db_info:
        log_error("无法获取数据库结构，同步终止")
        sys.exit(1)
    
    try:
        log_info("正在从 getbiji 获取所有笔记（分页获取）...")
        all_notes = get_all_notes()
        
        if not all_notes:
            log_warning("未获取到任何笔记")
            sys.exit(0)
        
        log_info(f"总共获取到 {len(all_notes)} 条笔记")
        
        # 只测试前3条笔记
        test_notes = all_notes[:3]
        synced = 0
        failed = 0
        skipped = 0
        
        for i, note in enumerate(test_notes):
            try:
                start_time = time.time()
                note_id = note.get('id', 'unknown')
                note_title = note.get('title', '无标题')[:50]
                log_info(f"【开始处理】第 {i+1}/{len(test_notes)} 条笔记 (ID: {note_id}, 标题: {note_title}...)")
                
                existing_page_id = notion_query_by_noteid(str(note_id), db_info)
                time.sleep(0.3)
                
                if existing_page_id:
                    log_info(f"笔记已存在，跳过: {note_id}")
                    skipped += 1
                else:
                    log_info(f"创建新笔记: {note_id}")
                    if notion_create_page(note, db_info):
                        synced += 1
                        log_info(f"✓ 创建成功: {note_title}...")
                    else:
                        failed += 1
                        log_error(f"✗ 创建失败: {note_title}...")
                
                end_time = time.time()
                log_info(f"【完成处理】第 {i+1} 条笔记，耗时: {end_time - start_time:.2f}秒")
                
                time.sleep(0.5)
                
            except Exception as e:
                failed += 1
                log_error(f"处理第 {i+1} 条笔记失败: {str(e)}")
                log_error(f"错误详情: {traceback.format_exc()}")
                continue
        
        log_info("=" * 50)
        log_info(f"同步完成!")
        log_info(f"获取到: {len(all_notes)} 条笔记（总共）")
        log_info(f"测试同步: {len(test_notes)} 条笔记")
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
