

import tweepy
import os
import random
import shutil
from PIL import Image
import datetime
import nas_env   #環境情報

# ========= 設定 =========
DEFAULT_HASHTAGS = ["#AIart", "#AIイラスト", "#StableDiffusion"]  # 追加したいハッシュタグ

now = datetime.datetime.now()
hour = now.hour

messages = {
    range(5, 11):  "おはようございます～🌅",
    range(11, 17): "こんにちは～☀️",
    range(17, 23): "こんばんは～🌙",
}

TWEET_TEXT = next((msg for r, msg in messages.items() if hour in r), "おやすみなさい～💤")

# ========= 環境変数から読み出し =========
x_params = nas_env.get_x_params()
API_KEY = x_params["api_key"]
API_SECRET = x_params["api_secret"]
ACCESS_TOKEN = x_params["access_token"]
ACCESS_TOKEN_SECRET = x_params["access_token_secret"]

img_dirs = nas_env.get_img_dirs()
ROOT_DIR = img_dirs['root']
IMAGE_DIR = img_dirs['release']
WORKSPACE_DIR = img_dirs['workspace']   
POSTED_DIR = img_dirs['posted']

# =======================

# v2 Client（投稿用）
client = tweepy.Client(
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_TOKEN_SECRET
)

# v1.1 API（画像アップロード用）
auth = tweepy.OAuth1UserHandler(
    API_KEY, API_SECRET,
    ACCESS_TOKEN, ACCESS_TOKEN_SECRET
)
api_v1 = tweepy.API(auth)

def get_exif_hashtags(image_path: str) -> list:
    img = Image.open(image_path)
    info = img.info

    desc = info.get("description") or info.get("ImageDescription") or ""
    if not desc:
        return []

    tags = []
    for line in desc.split("\n"):
        line = line.strip()
        if line.lower().startswith("title"):
            title = line.split(":", 1)[1].strip()
            if title:
                # スペースをアンダースコアに置換
                title_tag = title.replace(" ", "_")
                tags.append(f"#{title_tag}")
        elif line.lower().startswith("character"):
            character = line.split(":", 1)[1].strip()
            if character:
                character_tag = character.replace(" ", "_")
                tags.append(f"#{character_tag}")

    return tags

def get_rating_from_exif(image_path: str) -> str:
    img = Image.open(image_path)
    info = img.info

    desc = info.get("description") or info.get("ImageDescription") or ""
    if not desc:
        return "unknown"

    for line in desc.split("\n"):
        line = line.strip()
        if line.lower().startswith("rating"):
            rating = line.split(":", 1)[1].strip().lower()
            return rating

    return "unknown"


def choose_random_image(image_dir: str) -> str:
    """
    指定フォルダから画像をランダム選択（Linux/Windows 対応版）
    """
    # パスを正規化（\ を / に変換）
    image_dir = os.path.normpath(image_dir)

    if not os.path.isdir(image_dir):
        raise NotADirectoryError(f"ディレクトリが存在しません: {image_dir}")
    
    files = [
        f for f in os.listdir(image_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if not files:
        raise FileNotFoundError(f"画像ファイルが見つかりません: {image_dir}")

    return os.path.join(image_dir, random.choice(files))

def choose_random_nsfw_image(image_dir: str) -> str:
    """
    指定したフォルダと、サブフォルダのうち名前が "R18" または "R18+" のフォルダ内から
    ランダムに画像ファイル(.jpg, .jpeg, .png)を選択して、そのフルパスを返す関数。
    """
    all_files = []

    for root, dirs, files in os.walk(image_dir):
        # 現在のフォルダ名を取得
        folder_name = os.path.basename(root)
        # サブフォルダが "r18" または "r18+" の場合のみ処理
        if root == image_dir or folder_name in ("r18", "r18+"):
            for f in files:
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    all_files.append(os.path.join(root, f))

    if not all_files:
        raise FileNotFoundError("対象の画像ファイルが見つかりませんでした。")

    return random.choice(all_files)

def main():
    image_path = choose_random_image(IMAGE_DIR)
    print("選択された画像:", image_path)

    exif_tags = get_exif_hashtags(image_path)
    rating = get_rating_from_exif(image_path)

    # Trueなら #NSFW タグを追加
    if rating == ("r18" or "r18+"):
        exif_tags.append("#NSFW")

    print("EXIF Rating:", rating)

    media = api_v1.media_upload(image_path)
    media_id = media.media_id_string

    full_text = f"{TWEET_TEXT}\n" + " ".join(DEFAULT_HASHTAGS + exif_tags)

    client.create_tweet(
        text=full_text,
        media_ids=[media_id],
    )

    print("投稿完了")

    # ❗重複投稿を防止するため posted/ フォルダへ移動
    shutil.move(image_path, os.path.join(POSTED_DIR, os.path.basename(image_path)))
    print("画像を posted/ に移動しました:", image_path)

if __name__ == "__main__":
    main()