#!/usr/bin/env python3
"""
测试 Notion 连接和数据库访问
"""

import os
import requests
import sys

# 从环境变量获取 Token 和 Database ID
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "").strip()
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "").strip()

def test_notion_connection():
    """测试 Notion 连接"""
    print("=== Notion 连接测试 ===")
    print(f"Token 长度: {len(NOTION_TOKEN)}")
    print(f"Database ID 长度: {len(NOTION_DATABASE_ID)}")
    print(f"Database ID: {NOTION_DATABASE_ID}")
    
    if not NOTION_TOKEN:
        print("❌ 错误: NOTION_TOKEN 环境变量未设置")
        return False
    
    if not NOTION_DATABASE_ID:
        print("❌ 错误: NOTION_DATABASE_ID 环境变量未设置")
        return False
    
    # 设置请求头
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    
    # 测试1：验证 Token
    print("\n1. 测试 Token 有效性...")
    try:
        response = requests.get(
            "https://api.notion.com/v1/users/me", 
            headers=headers, 
            timeout=10
        )
        
        if response.status_code == 200:
            user_data = response.json()
            user_name = user_data.get("name", "未知用户")
            print(f"✅ Token 有效")
            print(f"   用户: {user_name}")
            print(f"   用户ID: {user_data.get('id', '未知')[:8]}...")
        else:
            print(f"❌ Token 无效 - 状态码: {response.status_code}")
            print(f"   错误信息: {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    
    # 测试2：验证数据库访问
    print("\n2. 测试数据库访问...")
    try:
        url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            db_data = response.json()
            
            # 获取数据库标题
            db_title = "无标题"
            if "title" in db_data and db_data["title"]:
                if isinstance(db_data["title"], list) and db_data["title"]:
                    db_title = db_data["title"][0].get("plain_text", "无标题")
            
            print(f"✅ 数据库访问成功")
            print(f"   数据库标题: {db_title}")
            print(f"   数据库ID: {db_data.get('id', '未知')[:8]}...")
            
            # 显示数据库属性
            properties = db_data.get("properties", {})
            if properties:
                print(f"   数据库属性 ({len(properties)} 个):")
                for prop_name, prop_data in list(properties.items())[:10]:  # 只显示前10个
                    prop_type = prop_data.get("type", "未知")
                    print(f"     - {prop_name} ({prop_type})")
                if len(properties) > 10:
                    print(f"     ... 还有 {len(properties) - 10} 个属性")
            else:
                print(f"   警告: 数据库没有属性")
            
            return True
            
        elif response.status_code == 404:
            print("❌ 数据库不存在或集成没有权限 (404)")
            print("可能的原因:")
            print("1. 数据库ID错误 - 请检查 Database ID 是否正确")
            print("2. 数据库没有与集成共享 - 请在 Notion 中邀请集成访问数据库")
            print("3. 数据库在不同工作区 - 请确保数据库在与集成相同的工作区")
            print(f"   请求的URL: {url}")
            
        elif response.status_code == 403:
            print("❌ 权限不足 (403)")
            print("请在 Notion 中完成以下操作:")
            print("1. 打开数据库页面")
            print("2. 点击右上角 '...' 菜单")
            print("3. 选择 'Connections'")
            print("4. 找到 'G getbiji' 集成并连接")
            
        else:
            print(f"❌ 数据库访问失败 - 状态码: {response.status_code}")
            print(f"   错误信息: {response.text[:200]}")
            
        return False
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False

if __name__ == "__main__":
    print("开始测试 Notion 连接...")
    print("-" * 50)
    
    success = test_notion_connection()
    
    print("-" * 50)
    if success:
        print("✅ 所有测试通过！Notion 连接正常")
        sys.exit(0)
    else:
        print("❌ 测试失败，请检查以上错误信息")
        sys.exit(1)
