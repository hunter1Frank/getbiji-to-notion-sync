name: Sync Getbiji to Notion

on:

workflow_dispatch:

schedule:

- cron: "0 */6*   **"

jobs:

sync:

runs-on: ubuntu-latest

steps:

- name: Checkout
    
    uses: actions/checkout@v4
    
- name: Set up Python
    
    uses: actions/setup-python@v5
    
    with:
    
    python-version: "3.11"
    
- name: Install dependencies
    
    run: pip install requests
    
- name: Run sync
    
    env:
    
    GETBIJI_API_KEY: $ secrets.GETBIJI_API_KEY 
    
    GETBIJI_BASE_URL: $ secrets.GETBIJI_BASE_URL 
    
    NOTION_TOKEN: $ secrets.NOTION_TOKEN 
    
    NOTION_DATABASE_ID: $ secrets.NOTION_DATABASE_ID 
    
    run: python [sync.py](http://sync.py)
