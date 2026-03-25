#!/usr/bin/env python3
"""
列出 "G getbiji" 集成可以访问的所有数据库
"""

import os
import requests
import json

# 从环境变量获取 Token
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()

def list_all_databases():
    """列出所有可访问的数据库"""
    print("=== 列出所有可访问的数据库 ===")
    print(f"Token 长度: {len(NOTION_TOKEN)}")
    
    if not NOTION_TOKEN:
        print("❌ 错误: NOTION_TOKEN 环境变量未设置")
        return
    
    # 设置请求头
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    
    try:
        # 搜索所有数据库
        print("\n正在搜索可访问的数据库...")
        search_url = "https://api.notion.com/v1/search"
        search_payload = {
            "filter": {
                "value": "database",
                "property": "object"
            },
            "page_size": 100
        }
        
        response = requests.post(
            search_url, 
            headers=headers, 
            json=search_payload, 
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            databases = data.get("results", [])
            print(f"✅ 找到 {len(databases)} 个数据库:")
            print("-" * 60)
            
            for i, db in enumerate(databases, 1):
                # 获取数据库标题
                db_title = "无标题"
                if "title" in db and db["title"]:
                    if isinstance(db["title"], list) and db["title"]:
                        db_title = db["title"][0].get("plain_text", "无标题")
                
                # 获取数据库 ID
                db_id = db.get("id", "未知")
                
                # 获取数据库 URL
                db_url = db.get("url", "无")
                
                print(f"{i}. 数据库标题: {db_title}")
                print(f"   数据库ID: {db_id}")
                print(f"   数据库URL: {db_url}")
                
                # 显示数据库属性（如果有）
                if "properties" in db:
                    properties = list(db["properties"].keys())[:5]  # 只显示前5个属性
                    if properties:
                        print(f"   属性示例: {', '.join(properties)}...")
                
                print("-" * 60)
                
        else:
            print(f"❌ 搜索数据库失败 ({response.status_code}): {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ 搜索数据库时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    list_all_databases()
