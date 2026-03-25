import os
import time
import requests
import sys
from datetime import datetime

# 环境变量
GETBIJI_API_KEY = os.environ.get("GETBIJI_API_KEY", "").strip()
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
    url = f"{GETBIJI_BASE_URL}{path}"
    
    # 尝试不同的认证头
    header_candidates = [
        {"Authorization": f"Bearer {GETBIJI_API_KEY}"},
        {"Authorization": GETBIJI_API_KEY},
        {"X-API-Key": GETBIJI_API_KEY},
        {"x-api-key": GETBIJI_API_KEY},
    ]
    
    for attempt in range(max_retries):
        for headers in header_candidates:
            try:
                log_info(f"尝试 getbiji 请求: {method} {url} (尝试 {attempt + 1}/{max_retries})")
                r = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)
                
                if r.status_code in (401, 403):
                    log_warning(f"认证失败，状态码: {r.status_code}, 头: {list(headers.keys())[0]}")
                    continue
                
                r.raise_for_status()
                
                ct = (r.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    return r.json()
                else:
                    return {"raw": r.text}
                    
            except requests.exceptions.RequestException as e:
                log_warning(f"请求失败: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    raise
    
    raise RuntimeError(f"Getbiji 认证失败，已尝试所有认证方式")

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
        log_info(f"成功创建 Notion 页面: {page_id}")
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
        
        log_info(f"成功更新 Notion 页面: {page_id}")
        return True
        
    except Exception as e:
        log_error(f"更新 Notion 页面失败: {str(e)}")
        return False

def to_notion_props(note):
    """将 getbiji 笔记转换为 Notion 属性"""
    title = note.get("title") or note.get("name") or note.get("summary") or "无标题"
    noteid = str(note.get("id") or note.get("note_id") or note.get("noteId") or "")
    
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
        props["Tags"] = {"multi_select": [{"name": str(t)[:100]} for t in tags[:10]]}  # 限制最多10个标签
    
    return noteid, props

def main():
    """主函数"""
    log_info("开始同步 get笔记 到 Notion")
    
    # 验证环境变量
    if not all([GETBIJI_API_KEY, GETBIJI_BASE_URL, NOTION_TOKEN, NOTION_DATABASE_ID]):
        log_error("缺少必要的环境变量")
        sys.exit(1)
    
    try:
        # 获取 getbiji 笔记列表
        log_info("正在从 getbiji 获取笔记...")
        data = getbiji_request("GET", "/resource/note/list")
        
        # 提取笔记列表
        notes = data.get("data") or data.get("list") or data.get("notes") or []
        
        if not notes:
            log_warning("未获取到任何笔记")
            sys.exit(0)
        
        log_info(f"获取到 {len(notes)} 条笔记")
        
        # 同步前20条（避免限流）
        synced = 0
        for i, note in enumerate(notes[:20]):
            try:
                log_info(f"处理第 {i+1} 条笔记...")
                
                noteid, props = to_notion_props(note)
                if not noteid:
                    log_warning(f"跳过第 {i+1} 条笔记: 缺少 NoteID")
                    continue
                
                # 检查是否已存在
                existing_page_id = notion_query_by_noteid(noteid)
                time.sleep(0.1)  # 小延迟
                
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
                
                # 避免速率限制
                time.sleep(0.4)
                
            except Exception as e:
                log_error(f"处理第 {i+1} 条笔记失败: {str(e)}")
                continue
        
        log_info(f"同步完成! 成功处理 {synced} 条笔记")
        
    except Exception as e:
        log_error(f"同步过程失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
