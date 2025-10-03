import requests
import json
import os
from datetime import datetime
from notion_client import Client

# NOTION_TOKEN >>> 環境変数に登録

PAGE_ID = "27f0b631271a80ef8657e6081d7c435b"  # ページID
NOTION_DATABASE_ID = "27f0b631271a80e2bd54ed729caadfdd"

RATING = [{'name':'safe'}, {'name':'r18'}, {'name':'r18+'} ]
MODE = [{'name':'random'}, {'name':'scenario'}, {'name':'pickup'}, {'name':'keyword search'}]

# 環境変数からNOTION_TOKEN呼び出し
notion_token = os.environ["NOTION_TOKEN"]

headers = {
    "Authorization": f"Bearer {notion_token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Notionクライアントを初期化
client = Client(auth=notion_token)

#############################################################################################################
# 全てのユーザー情報取得
def get_all_notion_users():
    response = client.users.list()
    return response

#############################################################################################################
# データベースの全ての情報を取得
def read_notion_database(database_id):
    response = client.databases.query(
        **{
            "database_id": database_id,
        }
    )

    print(response)
    return response

#############################################################################################################
# データベースにレコード追加
def add_record(character, date, url, batch_cnt, mode_list=MODE, rating_list=RATING):
    # multi_selectはリスト形式で渡す
    mode_list = mode_list or []
    rating_list = rating_list or []

    # image_path = "//192.168.68.100/personal_folder/StabilityMatrix/Images/workspace/raana/raana_20251002101034_1.png"

    try:
        # upload_response = client.file_uploads.create(
        #     filename="raana_20251002101034_1.png",# ← Notion上での表示名
        #     content_type="image/png"
        # )

        # with open(image_path, "rb") as file:
        #     client.file_uploads.send(
        #         file_upload_id=upload_response["id"],
        #         file=file
        #     )

        new_page = client.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "character": {
                    "title": [{"text": {"content": character}}]
                },
                "日付": {
                    "date": {"start": date}
                },
                "URL": {
                    "url": url
                },
                "mode": {
                    "multi_select": [{"name": m} for m in mode_list]
                },
                "rating": {
                    "multi_select": [{"name": r} for r in rating_list]
                },
                "Batch count": {
                    "number": batch_cnt
                }
            }
        )

        # file_block = client.blocks.children.append(
        #     new_page["id"],
        #     children=[
        #         {
        #             "object": "block",
        #             "type": "file",
        #             "file": {
        #                 "caption": [],
        #                 "type": "file_upload",
        #                 "file_upload": {
        #                     "id": upload_response["id"]
        #                 },
        #                 "name": "raana_20251002101034_1.png"
        #             } 
        #         }
        #     ]
        # )

        print(f"✅ レコード追加成功: {new_page['id']}")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")


#############################################################################################################
def check_keyword_in_character(keyword: str):
    # データベースをクエリ（全件取得）
    response = client.databases.query(database_id=NOTION_DATABASE_ID)

    found = False
    for page in response["results"]:
        # character プロパティを取得
        character_property = page["properties"].get("character", {})
        title_items = character_property.get("title", [])

        if not title_items:
            continue

        # plain_text を結合して文字列化
        character_name = "".join([t["plain_text"] for t in title_items])

        if keyword.lower() in character_name.lower():
            print(f"✅ キーワード '{keyword}' を含むデータが見つかりました: {character_name}")
            found = True

    if not found:
        print(f"❌ キーワード '{keyword}' を含むデータは見つかりませんでした")

# url = f"https://api.notion.com/v1/blocks/{PAGE_ID}/children"

# data_to_add = "こんにちは、NotionにPythonからアップロードしました！"

# payload = {
#     "children": [
#         {
#             "object": "block",
#             "type": "paragraph",
#             "paragraph": {
#                 "rich_text": [
#                     {
#                         "type": "text",
#                         "text": {
#                             "content": data_to_add
#                         }
#                     }
#                 ]
#             }
#         }
#     ]
# }

# response = requests.patch(url, headers=headers, data=json.dumps(payload))

# if response.status_code == 200:
#     print("データをNotionページに追加しました！")
# else:
#     print("エラー:", response.status_code, response.text)

#############################################################################################################
if __name__ == '__main__':
    add_record(
        character="himeko",
        date=datetime.now().date().isoformat(),
        url="\\100.78.203.111\personal_folder\StabilityMatrix\Images\workspace\himeko",
        batch_cnt=64,
        mode_list=["random"],
        rating_list=["safe"]
    )
    # check_keyword_in_character("raana")
