import platform
import os
from pathlib import Path

# ========= 環境変数から読み出し =========
# load_dotenv()  # generate.py で読んでいるので不要

def _must_env(key: str) -> str:
	v = os.getenv(key)
	if not v:
		raise RuntimeError(f"Missing env var: {key}")
	return v


def get_img_dirs() -> dict:
    system = platform.system()

    suffix = "WIN" if system == "Windows" else "LINUX"

    release = Path(_must_env(f"RELEASE_PATH_{suffix}"))
    if not release.is_absolute(): 
        raise RuntimeError(f"release path must be absolute: {release}")  
    
    workspace = Path(_must_env(f"WORKSPACE_PATH_{suffix}"))
    if not workspace.is_absolute(): 
        raise RuntimeError(f"workspace path must be absolute: {workspace}") 

    root = Path(_must_env(f"ROOT_PATH_{suffix}"))
    if not root.is_absolute(): 
        raise RuntimeError(f"root path must be absolute: {root}") 
    
    posted = release / "posted"
    posted.mkdir(parents=True, exist_ok=True) 

    return {"release": release, "workspace": workspace, "posted": posted, "root": root}

# Xの認証情報を環境変数から取得
def get_x_params() -> dict:
    return {
        "api_key": os.getenv("X_API_KEY"),
        "api_secret": os.getenv("X_API_SECRET"),
        "access_token": os.getenv("X_ACCESS_TOKEN"),
        "access_token_secret": os.getenv("X_ACCESS_TOKEN_SECRET"),  
    }

# Notionの認証情報を環境変数から取得
def get_notion_params() -> dict:
    return {
        "notion_token": os.getenv("NOTION_TOKEN"),
        "notion_page_id": os.getenv("NOTION_PAGE_ID"), 
        "notion_database_id": os.getenv("NOTION_DATABASE_ID"),
        "notion_gen_db_id": os.getenv("NOTION_GEN_DB_ID"),
        "notion_char_db_id": os.getenv("NOTION_CHAR_DB_ID"),
    }

# Immichの認証情報を環境変数から取得
def get_immich_params() -> dict:
    return {
        "immich_url": os.getenv("IMMICH_URL"),
        "immich_library_id": os.getenv("IMMICH_LIBRARY_ID"),
        "immich_token": os.getenv("IMMICH_TOKEN"),
        "immich_access_token": os.getenv("IMMICH_ACCESS_TOKEN"),
    }

# Immich PostgreSQL接続情報を環境変数から取得
def get_db_params() -> dict:
    return {
        "dbname": os.getenv("IMMICH_DB_NAME", "immich"),
        "user": os.getenv("IMMICH_DB_USER", "postgres"),
        "password": _must_env("IMMICH_DB_PASSWORD"),
        "host": os.getenv("IMMICH_DB_HOST", "192.168.68.100"),
        "port": int(os.getenv("IMMICH_DB_PORT", "15432")),
    }