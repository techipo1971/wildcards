
import requests
import os
import re
import time
import notion as nt
from dotenv import load_dotenv

# ======================
# 設定
# ======================

# .envファイルを読み込む
load_dotenv()

# Patreon API
PATREON_TOKEN = os.getenv("PATREON_TOKEN")
BASE_URL_PATREON_API = "https://www.patreon.com/api/oauth2/v2"

# Notion API
NOTION_TOKEN =  os.getenv("NOTION_TOKEN")
DATABASE_ID = "28a0b631271a80aeb46df809192739e5"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

########################################################################################################################
def get_creator_campaign_id():
    """自分のキャンペーンIDを取得"""
    headers = {"Authorization": f"Bearer {PATREON_TOKEN}"}
    url = f"{BASE_URL_PATREON_API}/campaigns?include=creator"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    campaign_id = data["data"][0]["id"]
    print(f"✅ Campaign ID: {campaign_id}")
    return campaign_id

# CAMPAIGN_ID = "ここにキャンペーンID"
CAMPAIGN_ID = get_creator_campaign_id()

# ======================
# タイトル解析関数
# ======================
def parse_title(title):
    # 日付は末尾にあると仮定
    date_match = re.search(r"'(\d{2}/\d{2}/\d{2})$", title)
    if date_match:
        yy, mm, dd = date_match.group(1).split("/")
        pub_date = f"20{yy}-{mm}-{dd}"  # ISO 8601形式
    else:
        pub_date = None

    title_without_date = title.replace(date_match.group(0), "").strip() if date_match else title

    allowed_ratings = ["R18", "R18+", "R18++"]
    parts = title_without_date.split()

    rating = "SAFE"
    char_name_parts = []

    for part in parts:
        if part in allowed_ratings:
            rating = part
        else:
            char_name_parts.append(part)

    char_name = " ".join(char_name_parts)
    return char_name, rating

# ======================
# Patreonから投稿取得
# ======================
def get_all_posts(campaign_id):
    posts = []
    url = f"{BASE_URL_PATREON_API}/campaigns/{campaign_id}/posts?fields[post]=title,url,published_at,is_public"
    
    while url:
        resp = requests.get(url, headers={"Authorization": f"Bearer {PATREON_TOKEN}"})
        if resp.status_code != 200:
            raise Exception(f"❌ Patreon APIエラー: {resp.status_code} {resp.text}")

        data = resp.json()
        posts.extend(data.get("data", []))
        url = data.get("links", {}).get("next")  # ページネーション
        time.sleep(0.3)  # API過負荷回避

    return posts

# ======================
# Notionに既存URL取得（重複防止用）
# ======================
def get_existing_urls():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    existing_urls = set()
    has_more = True
    start_cursor = None

    while has_more:
        body = {}
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = requests.post(url, headers=NOTION_HEADERS, json=body)
        data = resp.json()

        for page in data.get("results", []):
            props = page["properties"]
            url_val = props.get("URL", {}).get("url")
            if url_val:
                existing_urls.add(url_val)

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")
    
    return existing_urls

# ======================
# Notionにページ作成
# ======================
def create_notion_page(post):
    BASE_URL_PATREON = "https://www.patreon.com"
    title_text = post["attributes"].get("title", "タイトルなし")
    char_name, rating = parse_title(title_text)
    pub_date = post["attributes"].get("published_at", "").split("T")[0] if post["attributes"].get("published_at") else None  
    url = f"{BASE_URL_PATREON}{post['attributes'].get('url')}"

    data = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "タイトル": {"title": [{"text": {"content": title_text}}]},      # タイトル列名に合わせる
            "投稿日": {"date": {"start": pub_date}},                       # 日付列名に合わせる
            "キャラ名": {"rich_text": [{"text": {"content": char_name}}]}, # キャラ名列名
            # "Rating": {"multi_select": [{"name": r} for r in nt.RATING]},              # マルチセレクト対応
            "Rating": {"multi_select": [{"name": r} for r in [rating]]},              # マルチセレクト対応
            "URL": {"url": url}                                          # URL列名
        }
    }

    resp = requests.post("https://api.notion.com/v1/pages", headers=NOTION_HEADERS, json=data)
    if resp.status_code != 200:
        print("❌ エラー:", resp.status_code, resp.text)
    else:
        print("✅ Notionに追加:", title_text)

# ======================
# メイン処理
# ======================
if __name__ == "__main__":
    print("🔄 Patreonから投稿データ取得中...")
    posts = get_all_posts(CAMPAIGN_ID)
    print(f"🔹 取得件数: {len(posts)}")

    print("🔄 Notionにアップロード中...")
    existing_urls = get_existing_urls()
    for post in posts:
        post_url = f"https://www.patreon.com{post['attributes'].get('url')}"
        if post_url in existing_urls:
            print("⚠️ 既に登録済み:", post_url)
            continue
        create_notion_page(post)
        time.sleep(0.3)  # Notion API制限対策

    print("🎉 全投稿のNotionアップロード完了！")