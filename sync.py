import os

import time

import requests

GETBIJI_API_KEY = os.environ["GETBIJI_API_KEY"]

GETBIJI_BASE_URL = os.environ["GETBIJI_BASE_URL"].rstrip("/")

NOTION_TOKEN = os.environ["NOTION_TOKEN"]

NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

def getbiji_request(method, path, params=None, json=None):

url = f"{GETBIJI_BASE_URL}{path}"

header_candidates = [

{"Authorization": f"Bearer {GETBIJI_API_KEY}"},

{"Authorization": GETBIJI_API_KEY},

{"X-API-Key": GETBIJI_API_KEY},

{"x-api-key": GETBIJI_API_KEY},

]

last = None

for headers in header_candidates:

r = requests.request(method, url, headers=headers, params=params, json=json, timeout=30)

# 401/403 继续试下一个 header

if r.status_code in (401, 403):

last = (r.status_code, r.text[:300])

continue

r.raise_for_status()

return r.json()

raise RuntimeError(f"Getbiji auth failed. Last response: {last}")

def notion_headers():

return {

"Authorization": f"Bearer {NOTION_TOKEN}",

"Content-Type": "application/json",

"Notion-Version": "2022-06-28",

}

def notion_query_by_noteid(noteid):

url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"

payload = {

"filter": {

"property": "NoteID",

"rich_text": {"equals": noteid},

}

}

r = [requests.post](http://requests.post)(url, headers=notion_headers(), json=payload, timeout=30)

r.raise_for_status()

results = r.json().get("results", [])

return results[0]["id"] if results else None

def notion_create_page(props):

url = "https://api.notion.com/v1/pages"

payload = {

"parent": {"database_id": NOTION_DATABASE_ID},

"properties": props,

}

r = [requests.post](http://requests.post)(url, headers=notion_headers(), json=payload, timeout=30)

r.raise_for_status()

return r.json()["id"]

def notion_update_page(page_id, props):

url = f"https://api.notion.com/v1/pages/{page_id}"

payload = {"properties": props}

r = requests.patch(url, headers=notion_headers(), json=payload, timeout=30)

r.raise_for_status()

def to_notion_props(note):

title = note.get("title") or note.get("name") or note.get("summary") or "Untitled"

noteid = str(note.get("id") or note.get("note_id") or note.get("noteId") or "")

created = note.get("created_at") or note.get("createdAt") or note.get("created_time")

updated = note.get("updated_at") or note.get("updatedAt") or note.get("updated_time")

source = note.get("url") or note.get("source_url") or note.get("sourceUrl")

tags = note.get("tags") or []

props = {

"Name": {"title": [{"text": {"content": title[:200]}}]},

"NoteID": {"rich_text": [{"text": {"content": noteid[:200]}}]},

}

if created:

props["CreatedAt"] = {"date": {"start": created}}

if updated:

props["UpdatedAt"] = {"date": {"start": updated}}

if source:

props["SourceURL"] = {"url": source}

if isinstance(tags, list) and tags:

props["Tags"] = {"multi_select": [{"name": str(t)[:100]} for t in tags[:50]]}

return noteid, props

def main():

data = getbiji_request("GET", "/resource/note/list")

notes = data.get("data") or data.get("list") or data.get("notes") or []

print("notes:", len(notes))

synced = 0

for n in notes[:50]:  # 先跑通链路：只同步前 50 条

noteid, props = to_notion_props(n)

if not noteid:

continue

existing_page_id = notion_query_by_noteid(noteid)

if existing_page_id:

notion_update_page(existing_page_id, props)

else:

notion_create_page(props)

synced += 1

time.sleep(0.4)

print("synced:", synced)

if **name** == "**main**":

main()
