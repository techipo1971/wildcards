import requests
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from notion_client import Client
import immich
import traceback
import nas_env as nas   #環境情報

#import psycopg2
from PIL import Image

# NOTION_TOKEN >>> 環境変数に登録
# 環境変数からNOTION_TOKEN呼び出し
ROOT_PATH = nas.img_dirs['root']
notion_token = nas.notion_params["notion_token"]
PAGE_ID = nas.notion_params["notion_page_id"]
NOTION_DATABASE_ID = nas.notion_params["notion_database_id"]
GEN_DB_ID = nas.notion_params["notion_gen_db_id"]

RATING = [{'name':'safe'}, {'name':'r18'}, {'name':'r18+'}, {'name':'yuri'},{'name':'R18++'}]
MODE = [{'name':'random'}, {'name':'scenario'}, {'name':'pickup'}, {'name':'keyword search'}]

headers = {
    "Authorization": f"Bearer {notion_token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# Notionクライアントを初期化
client = Client(auth=notion_token)

#############################################################################################################
# === description（EXIF）から Character と rating を抽出 ===
def parse_exif_description(desc):
    character = None
    rating = "safe"

    if not desc:
        return character, rating

    # Character を抽出（"Character: xxx" の形式を想定）
    match_char = re.search(r"character\s*[:=]\s*([^\n,]+)", desc)
    if match_char:
        character = match_char.group(1).strip()

    # rating 判定（文中のキーワードから推定）
    if re.search(r"r18\+|nsfw", desc, re.IGNORECASE):
        rating = "r18+"
    elif re.search(r"r18", desc, re.IGNORECASE):
        rating = "r18"

    return character, rating

#############################################################################################################
def ensure_properties_exist(client, db_id, required_props):
    """
    required_props: { "プロパティ名": "type" }  typeは 'number'|'date'|'title'|'rich_text' 等
    存在しないプロパティは databases.update で追加する
    """
    db = client.databases.retrieve(database_id=db_id)
    existing = db.get("properties", {}).keys()

    to_add = {}
    for name, ptype in required_props.items():
        if name not in existing:
            if ptype == "number":
                to_add[name] = {"number": {}}
            elif ptype == "date":
                to_add[name] = {"date": {}}
            elif ptype == "title":
                to_add[name] = {"title": {}}
            elif ptype == "rich_text":
                to_add[name] = {"rich_text": {}}
            elif ptype == "multi_select":
                to_add[name] = {"multi_select": {}}
            else:
                # その他はそのまま突っ込む（必要なら拡張）
                to_add[name] = {ptype: {}}

    if to_add:
        # databases.update は既存プロパティに追加する形で使えます
        client.databases.update(database_id=db_id, properties=to_add)
        print("✅ Added missing properties:", ", ".join(to_add.keys()))
    else:
        print("✅ All required properties already exist.")

#############################################################################################################
def upsert_character_record(client, db_id, char_name, safe_count, r18_count, r18p_count, yuri_count, last_created_dt, folder_path):
    # properties 構築
    props = {
        "character": {"title": [{"text": {"content": char_name}}]},
        "safe count": {"number": safe_count},
        "r18 count": {"number": r18_count},
        "r18+ count": {"number": r18p_count},
        "yuri count": {"number": yuri_count},
        "image folder": {"rich_text": [{"text": {"content": folder_path}}]}
    }

    if last_created_dt is not None:
        # last_created_dt が datetime なら isoformat、それ以外（文字列）はそのまま
        if isinstance(last_created_dt, datetime):
            props["last created"] = {"date": {"start": last_created_dt.isoformat()}}
        else:
            props["last created"] = {"date": {"start": str(last_created_dt)}}

    # 既存ページを検索（character タイトルと一致するもの）
    try:
        q = client.databases.query(
            database_id=db_id,
            filter={
                "property": "character",
                "title": {"equals": char_name}
            }
        )
    except Exception as e:
        print("❌ データベースクエリでエラー:", e)
        traceback.print_exc()
        return

    try:
        if q.get("results"):
            page_id = q["results"][0]["id"]
            client.pages.update(page_id=page_id, properties=props)
            print(f"🔁 Updated {char_name}: safe={safe_count}, r18={r18_count}, r18+={r18p_count}, yuri={yuri_count}, folder={folder_path}, last_created_dt={last_created_dt}")
        else:
            client.pages.create(parent={"database_id": db_id}, properties=props)
            print(f"➕ Created {char_name}: safe={safe_count}, r18={r18_count}, r18+={r18p_count}, yuri={yuri_count}, folder={folder_path}, last_created_dt={last_created_dt}")
    except Exception as e:
        print(f"❌ Notion update/create error ({char_name}):", e)
        traceback.print_exc()

#############################################################################################################
# === Notion へアップロード ===
def update_Generate_DB():
    print("📦 Fetching data from Immich DB...")
    df = immich.fetch_immich_data()  # あなたの既存関数

    if df is None or df.empty:
        print("データがありません。")
        return

    # DataFrameにキャラクターのルートフォルダ列を追加
    def extract_root_folder(path, character):
        if not path or not character:
            return ""
        parts = path.split(os.sep)
        for i, part in enumerate(parts):
            if part.lower() == character.lower():
                return os.sep.join(parts[:i + 1])  # キャラ名までのパス
        return os.path.dirname(path)  # fallback

    # DataFrameにフォルダ列を追加
    df["folder"] = df.apply(lambda row: extract_root_folder(row.get("originalpath"), row.get("character")), axis=1)

    print("📊 DataFrame columns:", df.columns.tolist())
    print(df.head(5))

    # 集計: character x rating ごとに count と最終作成日時を取得
    summary = (
        df.groupby(["character", "rating"])
        .agg(
            count=("file_name", "count"),
            last_created=("createdAt", "max"),
            file_path=("originalpath", "first")  # 代表的なファイルパスを取得
        )
        .reset_index()
    )

    # pivot で rating 列を横展開
    pivot = summary.pivot_table(index="character", columns="rating", values="count", fill_value=0).reset_index()

    # 各キャラの最新作成日時を取得
    last_created_map = summary.groupby("character")["last_created"].max().to_dict()

    # 各キャラの代表的なフォルダを取得（最初のレコードの folder を使用）
    folder_map = df.groupby("character")["folder"].first().to_dict()

    # 必要なプロパティを保険で作る（存在しなければ追加）
    required = {
        "character": "title",
        "safe count": "number",
        "r18 count": "number",
        "r18+ count": "number",
        "yuri count": "number",
        "last created": "date",
        "image folder": "rich_text"  # ← 追加！
    }
    ensure_properties_exist(client, GEN_DB_ID, required)

    # 各行を upsert
    for _, row in pivot.iterrows():
        char_name = str(row["character"])
        safe_count = int(row.get("safe", 0))
        r18_count = int(row.get("r18", 0))
        r18p_count = int(row.get("r18+", 0))
        yuri_count = int(row.get("yuri", 0))
        last_dt = last_created_map.get(char_name)  # pandas.Timestamp などが入る
        folder_path = folder_map.get(char_name, "")

        # pandas.Timestamp を Python datetime に変換する場合
        if hasattr(last_dt, "to_pydatetime"):
            last_dt = last_dt.to_pydatetime()

        upsert_character_record(
            client, 
            GEN_DB_ID, 
            char_name, 
            safe_count, 
            r18_count, 
            r18p_count, 
            yuri_count, 
            last_dt,
            folder_path,  # ← 追加
        )

    print("✅ Notion Generate DB update completed.")

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
def add_record(character, date, title, url, batch_cnt, mode_list=MODE, rating_list=RATING):
    # multi_selectはリスト形式で渡す
    mode_list = mode_list or []
    rating_list = rating_list or []

    try:

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
                },
                "work": {
                    "rich_text": [{"text": {"content": title}}]
                }
            }
        )

        print(f"✅ レコード追加成功: {new_page['id']}")

    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")


#############################################################################################################
def check_keyword_in_character(keyword: str):
    # データベースをクエリ（全件取得）
    pages = get_all_notion_pages(NOTION_DATABASE_ID)
    print(f"🔍 Generate Log -> {len(pages)}  records")

    found = False
    for page in pages:
        # character プロパティを取得
        character_property = page["properties"].get("character", {})
        title_items = character_property.get("title", [])

        if not title_items:
            continue

        # plain_text を結合して文字列化
        character_name = "".join([t["plain_text"] for t in title_items])

        #完全一致で比較
        if keyword.lower() == character_name.lower():
            print(f"❌ キーワード '{keyword}' と一致するデータが見つかりました: {character_name}")
            found = True

    if not found:
        print(f"✅ キーワード '{keyword}' と一致するデータは見つかりませんでした")

    return found


#############################################################################################################
def get_all_notion_pages(database_id: str):
    """Notionデータベースの全ページを再帰的に取得する"""
    all_results = []
    has_more = True
    next_cursor = None

    while has_more:
        # クエリパラメータを組み立て
        query_params = {"database_id": database_id}
        if next_cursor:
            query_params["start_cursor"] = next_cursor

        # データ取得
        response = client.databases.query(**query_params)

        all_results.extend(response["results"])
        has_more = response.get("has_more", False)
        next_cursor = response.get("next_cursor")

        # print(f"📦 {len(all_results)} 件 取得完了...")

    return all_results

#############################################################################################################
if __name__ == '__main__':
   
    immich.update_exif_info_to_postgres(ROOT_PATH)

    print("🚀 Uploading to Notion...")
    update_Generate_DB()
    print("✅ Done!")