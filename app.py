import requests
import json

ACCESS_TOKEN = "g4ldcMVGicV-mmpoQHUcJmGslx1JeMORIDl17dEtiHU"
API_BASE = "https://www.patreon.com/api/oauth2/v2"

########################################################################################################################
def get_creator_campaign_id():
    """自分のキャンペーンIDを取得"""
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    url = f"{API_BASE}/campaigns?include=creator"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    campaign_id = data["data"][0]["id"]
    print(f"✅ Campaign ID: {campaign_id}")
    return campaign_id

########################################################################################################################
def get_all_posts(campaign_id):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    params = {
        "fields[post]": "title,content,published_at,url,is_public",
        "page[size]": 20  # 一度に取得する件数（最大20）
    }
    url = f"{API_BASE}/campaigns/{campaign_id}/posts"

    all_posts = []
    while url:
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code != 200:
            print("❌ APIエラー:", resp.status_code, resp.text)
            break

        data = resp.json()
        all_posts.extend(data.get("data", []))
        print(f"📦 {len(data.get('data', []))} 件取得中... 合計: {len(all_posts)} 件")

        # 次ページURLを取得
        url = data.get("links", {}).get("next")
        params = None  # 次ページはURLにパラメータ込みで返ってくるのでクリアする

    print(f"✅ すべての投稿データを取得しました。 合計: {len(all_posts)} 件")

    # JSONに保存
    with open("patreon_posts_all.json", "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)
    print("💾 全投稿データを patreon_posts_all.json に保存しました。")

########################################################################################################################
def get_attachment_file_name(attachment_id):
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    url = f"{API_BASE}/attachments/{attachment_id}"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print("❌ エラー:", resp.status_code, resp.text)
        return None

    data = resp.json().get("data", {})
    attrs = data.get("attributes", {})
    file_name = attrs.get("file_name")
    file_url = attrs.get("url") or attrs.get("download_url")
    if not file_name and file_url:
        file_name = os.path.basename(file_url)
    return file_name

########################################################################################################################
def get_post_attachments(post):
    attachments = []
    rel = post.get("relationships", {}).get("attachments", {}).get("data", [])
    for item in rel:
        attachment_id = item.get("id")
        if attachment_id:
            name = get_attachment_file_name(attachment_id)
            if name:
                attachments.append(name)
    return attachments


if __name__ == "__main__":
    campaign_id = get_creator_campaign_id()
    # get_all_posts(campaign_id)

    # 例：全投稿JSONから1投稿目のファイル名を取得
    # with open("patreon_posts_all.json", "r", encoding="utf-8") as f:
    #     all_posts = json.load(f)

    # first_post = all_posts[0]
    # files = get_post_attachments(first_post)
    # print(files)