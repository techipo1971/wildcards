from dotenv import load_dotenv
import platform
import os
from pathlib import Path

# ========= 環境変数から読み出し =========
load_dotenv()

def get_img_path() -> dict:
    system = platform.system()

    suffix = "WIN" if system == "Windows" else "LINUX"

    release = Path(os.getenv(f"RELEASE_PATH_{suffix}"))
    workspace = Path(os.getenv(f"WORKSPACE_PATH_{suffix}"))
    posted = Path.joinpath(release, 'posted')
    root = Path(os.getenv(f"ROOT_PATH_{suffix}"))

    # posted フォルダが無ければ作る
    os.makedirs(posted, exist_ok=True)

    return {"release": release, "workspace": workspace, "posted": posted, "root": root}

# 画像パスを取得
img_dirs = get_img_path()

# Xの認証情報
x_params = {
    "api_key": os.getenv("X_API_KEY"),
    "api_secret": os.getenv("X_API_SECRET"),
    "access_token": os.getenv("X_ACCESS_TOKEN"),
    "access_token_secret": os.getenv("X_ACCESS_TOKEN_SECRET"),  
}

# Notionの認証情報
notion_params = { 
    "notion_token": os.getenv("NOTION_TOKEN"),
    "notion_page_id": os.getenv("NOTION_PAGE_ID"), 
    "notion_database_id": os.getenv("NOTION_DATABASE_ID"),
    "notion_gen_db_id": os.getenv("NOTION_GEN_DB_ID"),
    "notion_char_db_id": os.getenv("NOTION_CHAR_DB_ID"),
}

# Immichの認証情報
immich_params = {
    "immich_url": os.getenv("IMMICH_URL"),
    "immich_library_id": os.getenv("IMMICH_LIBRARY_ID"),
    "immich_token": os.getenv("IMMICH_TOKEN"),
    "immich_access_token": os.getenv("IMMICH_ACCESS_TOKEN"),
}