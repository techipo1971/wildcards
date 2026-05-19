import os
import json
import requests
import subprocess
import psycopg2
import pandas as pd
from PIL import Image
import nas_env   #環境情報
import time
from datetime import datetime

#############################################################################################################
# Immich の認証情報を環境変数から取得
immich_params = nas_env.get_immich_params()
IMMICH_URL = immich_params["immich_url"]
LIBRARY_ID = immich_params["immich_library_id"]
IMMICH_TOKEN = immich_params["immich_token"]
immich_access_token = immich_params["immich_access_token"]

headers = {
    "x-api-key": IMMICH_TOKEN,  # ← Authorization ではなくこちら！
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
    url = f"{IMMICH_URL}/api/search/metadata"

    params = {
        "page": 1,
        "limit": 1000
    }

    all_assets = []
    resp = requests.post(url, headers=headers, json=params)
    if resp.status_code != 200:
        print("❌ アセット取得失敗:", resp.status_code, resp.text)
    data = resp.json()
    assets = data.get("assets", [])

    return all_assets

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
    db_params = nas_env.get_db_params()
    conn = psycopg2.connect(**db_params)
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
def normalize_rating_to_int(rating) -> int | None:
    if rating is None:
        return None
    r = str(rating).strip().lower()
    mapping = {
        "safe": 0,
        "r18": 1,
        "r18+": 2,
        "yuri": 2,
    }
    return mapping.get(r)  # 未知の文字列は None

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
                rating_raw = info.get("rating")
                rating_int = normalize_rating_to_int(rating_raw)

                # title/character/rating が全部無いならスキップ（必要なら条件は調整）
                if not any([title, character, rating_raw]):
                    print(f"⚠️ No EXIF data for {file}, skip")
                    continue

                if rating_int is None:
                    # rating は更新しない（title/character だけ更新）
                    cur.execute(
                        """
                        UPDATE asset_exif
                        SET title = %s,
                            character = %s
                        FROM asset a
                        WHERE asset_exif."assetId" = a.id
                          AND a."originalFileName" = %s
                        """,
                        (title, character, file),
                    )
                else:
                    # rating も更新する（int）
                    cur.execute(
                        """
                        UPDATE asset_exif
                        SET title = %s,
                            character = %s,
                            rating = %s
                        FROM asset a
                        WHERE asset_exif."assetId" = a.id
                          AND a."originalFileName" = %s
                        """,
                        (title, character, rating_int, file),
                    )

                conn.commit()
                print(f"✅ Updated DB for {file}")
            except Exception as e:
                print(f"❌ Error processing {file}: {e}")
                conn.rollback()  # 重要：失敗時にロールバック

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
def get_library_info(library_id):
    """ライブラリ情報を取得"""
    url = f"{IMMICH_URL}/api/libraries/{library_id}"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

#############################################################################################################
# --- ライブラリスキャン ---
# https://api.immich.app/endpoints/libraries/scanLibrary
# curl -X POST -H "x-api-key: {IMMICH_TOKEN}" http://192.168.68.100:2283/api/libraries/6e75703c-aead-4497-b9e7-119d54496473/scan
def scan_library(library_id, timeout=60):
    """ライブラリをスキャンし完了を待つ"""
    library = get_library_info(library_id)
    refreshed_at_before = library["refreshedAt"]
    print("スキャン前 refreshedAt:", datetime.fromisoformat(refreshed_at_before.replace("Z", "+00:00")).strftime("%H:%M:%S"))
    
    # スキャン開始
    scan_url = f"{IMMICH_URL}/api/libraries/{library_id}/scan"
    resp = requests.post(scan_url, headers=headers)
    if resp.status_code == 204:
        print("✅ スキャン開始成功")
    else:
        print(f"❌ スキャン開始失敗: {resp.status_code}, {resp.text}")
        return

    # 完了監視（refreshedAtの更新を確認）
    start_time = time.time()
    while True:
        library = get_library_info(library_id)
        refreshed_at_after = library["refreshedAt"]
        if refreshed_at_after != refreshed_at_before:
            print("スキャン完了: refreshedAt 更新", datetime.fromisoformat(refreshed_at_after.replace("Z", "+00:00")).strftime("%H:%M:%S"))
            break
        if time.time() - start_time > timeout:
            print("❌ タイムアウト: スキャン完了を確認できませんでした")
            break
        time.sleep(2)  # 2秒ごとにチェック

#############################################################################################################
if __name__ == '__main__':

    scan_library(LIBRARY_ID, timeout=300)

    # data_path = "//192.168.68.100/personal_folder/StabilityMatrix/Images/workspace"
    # update_exif_info_to_postgres(data_path)

    # # 1️⃣ タグ作成
    # new_tag = create_tag("r18+", "#FF00FF")

    # # 2️⃣ タグ一覧を確認
    # tags = get_all_tags()
    # print(tags)

    # # 3️⃣ アセット一覧を取得して最初の1枚にタグを付与
    # assets = get_all_assets()
    # print(f"Total assets: {len(assets)}")
    # first_asset_id = assets[0]["id"]
    # add_tags_to_asset(first_asset_id, [new_tag["id"]])