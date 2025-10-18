import os
import io
import re
import yaml
from PIL import Image, PngImagePlugin

YAML_FILE = 'chara.yaml'

# --- YAML 定義を読み込む ---
with open(YAML_FILE, "r", encoding="utf-8") as f:
    yaml_data = yaml.safe_load(f)

#############################################################################################################
# --- ${trg: ... } の中身を抽出する関数 ---
def extract_trg_prompts(prompt_text):
    """
    YAML内のプロンプト文字列から ${trg: ... } の中身だけを抽出し、
    カンマ区切りの文字列で返す。
    """
    matches = re.findall(r"\$\{trg:([^}]+)\}", prompt_text)
    parts = []
    for m in matches:
        sub = [p.strip() for p in m.split(",") if p.strip()]
        parts.extend(sub)
    # まとめてカンマ区切り文字列にする
    return ", ".join(parts)

#############################################################################################################
def force_write_rating(folder_path, rating="r18"):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            img = Image.open(img_path)
            info = img.info  # EXIF / tEXt情報

            png_info = PngImagePlugin.PngInfo()
            # 既存の EXIF をすべてコピー
            for k, v in info.items():
                png_info.add_text(k, str(v))
            png_info.add_text("rating", rating)

            img.save(img_path, pnginfo=png_info)
            print(f"[UPDATED] {file}: rating={rating}")

#############################################################################################################
def copy_parameters_to_description(folder_path):
    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            try:
                img = Image.open(img_path)
                info = img.info  # PNGのメタデータ取得

                # Parametersを取得
                parameters = info.get("parameters")
                if not parameters:
                    print(f"⚠️ No Parameters found in {file}")
                    continue

                # すでにImageDescriptionがある場合はスキップ
                if info.get("ImageDescription"):
                    print(f"ℹ️ Already has ImageDescription: {file}")
                    continue

                # 新しいメタ情報作成
                png_info = PngImagePlugin.PngInfo()
                for k, v in info.items():
                    png_info.add_text(k, str(v))

                # Parameters → ImageDescription にコピー
                png_info.add_text("ImageDescription", parameters)

                # 保存
                img.save(img_path, pnginfo=png_info)
                print(f"✅ Copied Parameters → ImageDescription in {file}")

            except Exception as e:
                print(f"❌ Error processing {file}: {e}")

#############################################################################################################
def add_character_info(folder_path, title, chara_name, rating):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            img = Image.open(img_path)
            info = img.info  # EXIF / tEXt情報

            png_info = PngImagePlugin.PngInfo()
            # 既存の EXIF をすべてコピー
            for k, v in info.items():
                png_info.add_text(k, str(v))

            png_info.add_text("title", title)
            png_info.add_text("character", chara_name)
            png_info.add_text("rating", rating)

            # immich用にImageDescriptionに概要記載
            png_info.add_text("ImageDescription", f"Title : {title}\nCharacter : {chara_name}\nRating : {rating}")

            img.save(img_path, pnginfo=png_info)
            print(f"[UPDATED] {file}: title={title}, character name={chara_name}, rating={rating}")


#############################################################################################################
# os.walkを使って再帰的にフォルダ探索
def add_title_from_yaml(folder_path):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            img = Image.open(img_path)
            info = img.info  # EXIF / tEXt情報

            # EXIFのpromptを取得
            prompt = info.get("parameters", "")  
            title = info.get("title", "")
            rating = info.get("rating", "")

            # if title and rating:
            #     print(f"[SKIP] {file}: title={title}, rating={rating}")
            #     continue

            matched_title = None
            matched_character = None
            matched_rating = "safe"

            # YAML を走査して Parameters に含まれるプロンプトを探す
            for work, chars in yaml_data.items():
                for key, char_info in chars.items():
                    yaml_char_name = char_info.get("name", "")
                    yaml_prompts = char_info.get("prompt", [])

                    # 各prompt文字列から ${trg:...} 内の文字列を抽出
                    for p in yaml_prompts:
                        trg_text = extract_trg_prompts(p)
                        if trg_text and trg_text in prompt:
                            matched_title = work
                            matched_character = yaml_char_name
                            if "r18, nsfw" in prompt:
                                matched_rating = "r18"
                            elif "r18+, nsfw" in prompt:
                                matched_rating = "r18+"
                            break
                    if matched_title:
                        break
                if matched_title:
                    break

            print(f"[CHECK] {file}: title={matched_title}, character={matched_character}, rating={matched_rating}")

            # タイトルを EXIF に追加
            if matched_title:
                png_info = PngImagePlugin.PngInfo()
                # 既存の EXIF をすべてコピー
                for k, v in info.items():
                    png_info.add_text(k, str(v))
                # title と rating を追加
                png_info.add_text("title", matched_title)
                png_info.add_text("rating", matched_rating)
                if matched_character:
                    png_info.add_text("character", matched_character)

                img.save(img_path, pnginfo=png_info)
                print(f"[UPDATED] {file}: title={matched_title}, rating={matched_rating}")
            else:
                print(f"[NO MATCH] {file}")
#############################################################################################################
import os
from PIL import Image
from pathlib import Path
import time

def rename_pngs_by_character(folder_path: str):
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"フォルダが見つかりません: {folder_path}")

    for png_path in folder.glob("*.png"):
        try:
            with Image.open(png_path) as img:
                meta = img.info
                character = meta.get("character")
            if not character:
                continue

            old_name = png_path.name
            parts = old_name.split("_", 1)
            new_name = f"{character}_{parts[1]}" if len(parts) > 1 else f"{character}_{old_name}"
            new_path = png_path.with_name(new_name)

            counter = 1
            while new_path.exists():
                stem, ext = os.path.splitext(new_name)
                new_name = f"{stem}_{counter}{ext}"
                new_path = png_path.with_name(new_name)
                counter += 1

            # リトライ付き rename
            for attempt in range(3):
                try:
                    png_path.rename(new_path)
                    print(f"✅ {old_name} → {new_name}")
                    break
                except PermissionError:
                    print(f"⚠️ {png_path.name} が使用中。1秒後に再試行します")
                    time.sleep(1)
            else:
                print(f"❌ {png_path.name} の名前変更に失敗しました")

        except Exception as e:
            print(f"⚠️ {png_path.name} の処理中にエラー: {e}")


#############################################################################################################
if __name__ == '__main__':
    path = "//192.168.68.100/personal_folder/StabilityMatrix/Images/workspace/da_vinci/R18+"
    rename_pngs_by_character(path)


    # add_title_from_yaml(path)
    # force_write_rating(path, 'r18+')

    # copy_parameters_to_description("//192.168.68.100/personal_folder/StabilityMatrix/Images/workspace/ako")



# --- フォルダ内の PNG 画像を処理 ---
# def add_title_from_yaml(folder_path):
#     for file in os.listdir(folder_path):
#         if not file.lower().endswith(".png"):
#             continue

#         img_path = os.path.join(folder_path, file)
#         img = Image.open(img_path)
#         info = img.info  # EXIF / tEXt情報

#         # EXIFのpromptを取得
#         prompt = info.get("prompt", "")
#         title = info.get("title","")
#         rating = info.get("rating","")

#         if title and rating:
#             print(f"title: {title}")
#             print(f"rating: {rating}")
#             print(f"already exist, skip...")
#             break

#         matched_title = None
#         matched_character = None
#         matched_rating = "safe"

#         # YAML を走査して Parameters に含まれるプロンプトを探す
#         for work, chars in yaml_data.items():
#             for key, char_info in chars.items():
#                 yaml_char_name = char_info.get("name", "")
#                 yaml_prompts = char_info.get("prompt", [])
#                 # YAML 内の任意のプロンプト文字列が Parameters に含まれる場合
#                 if any(p.strip() in prompt for p in yaml_prompts):
#                     matched_title = work
#                     matched_character = yaml_char_name
#                     if "r18, nsfw" in prompt:
#                         matched_rating = "r18"
#                     elif "r18+, nsfw" in prompt:
#                         matched_rating = "r18+"
#                     break
#             if matched_title:
#                 break

#         print(matched_title)
#         print(matched_character)
#         print(matched_rating)

#         # # タイトルを EXIF に追加
#         if matched_title:
#             png_info = PngImagePlugin.PngInfo()
#             # 既存の EXIF をすべてコピー
#             for k, v in info.items():
#                 png_info.add_text(k, str(v))
#             # titleとrating を追加
#             png_info.add_text("title", matched_title)
#             png_info.add_text("rating", matched_rating)
#             img.save(img_path, pnginfo=png_info)
#             print(f"Updated title for {file}: {matched_title}")
#         else:
#             print(f"No match found for {file}")

# --- 使用例 ---
