import os
import json
import requests
import subprocess
import psycopg2
import pandas as pd
from PIL import Image

IMMICH_URL = "http://192.168.68.100:2283"  # あなたの Immich サーバの API ベース URL
TOKEN = "98BTL8i5RxQbTN2ItiJ4lD05tjayiUOlJuv8Ludihs"

headers = {
    "x-api-key": TOKEN,  # ← Authorization ではなくこちら！
    "Content-Type": "application/json"
}
#############################################################################################################
def get_all_tags():
    """すべてのタグを取得"""
    url = f"{IMMICH_URL}/api/tags"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()
#############################################################################################################
def get_all_assets():
    url = f"{IMMICH_URL}/api/assets"
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print("❌ アセット取得失敗:", resp.status_code, resp.text)
    else:
        print("✅ アセット一覧取得成功")
    resp.raise_for_status()
    return resp.json()

#############################################################################################################
def create_tag(tag_name: str, color: str = "#00FF00"):
    """Immichでタグを作成する"""
    url = f"{IMMICH_URL}/api/tags"

    payload = {
        "name": tag_name,
        "color": color  # 例: "#FF0000"（赤）
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload))

    if resp.status_code == 400:
        print("the tag is already exist")

    elif resp.status_code != 201:
        print("❌ タグ作成失敗:", resp.status_code, resp.text)
    else:
        print(f"✅ タグ作成成功: {tag_name}")    
        resp.raise_for_status()

    print(f"✅ タグ作成: {tag_name}")

    return resp.json()

#############################################################################################################
def add_tags_to_asset(asset_id: str, tag_ids: list[str]):
    """画像（アセット）にタグを付与する"""
    url = f"{IMMICH_URL}/api/asset/{asset_id}/tags"
    payload = {"tagIds": tag_ids}
    resp = requests.put(url, headers=headers, json=payload)
    resp.raise_for_status()
    print(f"🏷️ タグ付与成功: asset={asset_id}, tags={tag_ids}")
    return resp.json()

#############################################################################################################
def delete_tag(tag_id: str):
    """タグを削除する"""
    url = f"{IMMICH_URL}/api/tags/{tag_id}"
    resp = requests.delete(url, headers=headers)
    if resp.status_code == 204:
        print(f"🗑️ タグ削除成功: {tag_id}")
    else:
        print(f"⚠️ 削除失敗: {resp.status_code} {resp.text}")

#############################################################################################################
def connect_db():
    conn = psycopg2.connect(
        dbname="immich",
        user="postgres",
        password="postgres",
        host="192.168.68.100",
        port=15432
    )

    return conn

#############################################################################################################
# === Immich の PostgreSQL に接続 ===
def fetch_immich_data():
    conn = connect_db()

    # SQL クエリ
    query = """
        SELECT
            a."originalFileName" AS file_name,
            a."originalPath" AS originalPath,
            e.character,
            e.rating,
            e.title,
            a."createdAt"
        FROM asset a
        LEFT JOIN asset_exif e ON a.id = e."assetId"
        ORDER BY a."createdAt" DESC;
    """

    # pandasで結果をDataFrame化
    df = pd.read_sql_query(query, conn)
    conn.close()

    # 結果表示
    print(df.head(20))  # 先頭20件を表示
    print(f"\nTotal records: {len(df)}")

    return df

#############################################################################################################
# EXIF情報をDBに反映させる
def update_exif_info_to_postgres(folder_path):
    conn = connect_db()
    cur = conn.cursor()

    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            try:
                img = Image.open(img_path)
                info = img.info

                title = info.get("title")
                character = info.get("character")
                rating = info.get("rating")

                if not any([title, character, rating]):
                    print(f"⚠️ No EXIF data for {file}, skip")
                    continue

                cur.execute("""
                    UPDATE asset_exif
                    SET title = %s,
                        character = %s,
                        rating = %s
                    FROM asset a
                    WHERE asset_exif."assetId" = a.id
                    AND a."originalFileName" = %s
                """, (title, character, rating, file))

                conn.commit()
                print(f"✅ Updated DB for {file}")

            except Exception as e:
                print(f"❌ Error processing {file}: {e}")
                conn.rollback()  # ← これが重要！

    cur.close()
    conn.close()
    print("🎯 All done!")

#############################################################################################################
def repair_exif(folder_path):
    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            try:
                img = Image.open(img_path)
                info = img.info

                title = info.get("title")
                character = info.get("character")
                rating = info.get("rating")
                parameters = info.get("parameters")

                if not any([title, character, rating]):
                    if not parameters:
                        print(f"⚠️ No EXIF data for {file}, skip")
                        continue
                    else:
                        # parameters から title, character, rating を抽出
                        lines = parameters.split("\n")
                        if lines:
                            title = lines[0].strip()
                            for line in lines[1:]:
                                if line.startswith("character:"):
                                    character = line.replace("character:", "").strip()
                                elif line.startswith("rating:"):
                                    rating = line.replace("rating:", "").strip()

            except Exception as e:
                print(f"❌ Error processing {file}: {e}")

#############################################################################################################
if __name__ == '__main__':

    data_path = "//192.168.68.100/personal_folder/StabilityMatrix/Images/workspace"
    repair_exif(data_path)

    # update_exif_info_to_postgres(data_path)

    # # 1️⃣ タグ作成
    # new_tag = create_tag("r18+", "#FF00FF")

    # # 2️⃣ タグ一覧を確認
    # tags = get_all_tags()
    # print(tags)

    # # 3️⃣ アセット一覧を取得して最初の1枚にタグを付与
    assets = get_all_assets()
    # first_asset_id = assets[0]["id"]
    # add_tags_to_asset(first_asset_id, [new_tag["id"]])