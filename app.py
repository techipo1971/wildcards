import os
import re
from PIL import Image, PngImagePlugin
from dotenv import load_dotenv

load_dotenv()

ROOT_PATH = os.getenv("ROOT_PATH")

#############################################################################################################

def rename_files(folder_path: str, character_name: str, force_replace: bool = False):
    """
    PNGファイル名を指定ルールでリネームする。

    - 通常: (キャラ名)_YYYYMMDD_(連番).png
    - unknown_ や既存キャラ名も置き換え対象
    - force_replace=True の場合、既存キャラ名を強制上書き
    """

    files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]
    if not files:
        print("❌ PNGファイルが見つかりません。")
        return

    rename_map = []
    date_groups = {}

    for file in sorted(files):
        date = None

        # パターン: 20250823_135517_177272.png
        m1 = re.match(r"(\d{8})_", file)
        # パターン: tomoe_20250823_135517.png
        m2 = re.match(r"([a-zA-Z0-9]+)_?(\d{8})_", file)
        # パターン: unknown_20250902222301_1.png
        m3 = re.match(r"unknown_(\d{8})\d{6}_\d+\.(png|PNG)", file)

        if m1:
            date = m1.group(1)
        elif m2:
            date = m2.group(2)
        elif m3:
            date = m3.group(1)

        if not date:
            print(f"⚠ スキップ: {file}（日付形式が不明）")
            continue

        date_groups.setdefault(date, []).append(file)

    # --- 日付ごとにリネーム ---
    for date, file_list in date_groups.items():
        for i, old_name in enumerate(sorted(file_list), start=1):
            ext = os.path.splitext(old_name)[1]

            # 既存キャラ名を保持 or 上書き
            if not force_replace:
                m_exist = re.match(r"([a-zA-Z0-9]+)_\d{8}_", old_name)
                if m_exist and m_exist.group(1).lower() != "unknown":
                    current_name = m_exist.group(1)
                    new_name = f"{current_name}_{date}_{i:03d}{ext}"
                else:
                    new_name = f"{character_name}_{date}_{i:03d}{ext}"
            else:
                # 常に新しいキャラ名で上書き
                new_name = f"{character_name}_{date}_{i:03d}{ext}"

            old_path = os.path.join(folder_path, old_name)
            new_path = os.path.join(folder_path, new_name)

            # 同名ファイルを避ける
            if os.path.exists(new_path):
                print(f"⚠ スキップ: {new_name}（既に存在）")
                continue

            os.rename(old_path, new_path)
            rename_map.append((old_name, new_name))
            print(f"✅ {old_name} → {new_name}")

    print(f"\n🎯 {len(rename_map)} 個のファイルをリネーム完了！")

#############################################################################################################
def clear_file_info(folder_path):
    """
    指定フォルダ内のPNG画像の 'parameters' テキストから
    title, character, rating の行を削除する。

    Args:
        folder_path (str): 画像フォルダのパス
    """

    keys_to_remove = ["title", "character", "rating"]

    def remove_keys(parameters: str) -> str:
        """指定されたキー行を削除"""
        for key in keys_to_remove:
            pattern = rf"^{key}:\s*.*$(\r?\n)?"
            parameters = re.sub(pattern, "", parameters, flags=re.MULTILINE)
        # 余分な空行を整理
        parameters = "\n".join([line for line in parameters.splitlines() if line.strip()])
        return parameters.strip()

    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            try:
                img = Image.open(img_path)
                info = img.info.copy()
                parameters = info.get("parameters", "")

                print(f"🧹 {file} parameters(before):\n{parameters}")

                new_parameters = remove_keys(parameters)

                if new_parameters == parameters:
                    print(f"ℹ {file} に削除対象なし")
                    continue

                # --- PNG情報更新 ---
                pnginfo = PngImagePlugin.PngInfo()
                for k, v in info.items():
                    if isinstance(v, str) and k != "parameters":
                        pnginfo.add_text(k, v)
                pnginfo.add_text("parameters", new_parameters)

                img.save(img_path, pnginfo=pnginfo)
                print(f"✅ {file} 更新完了")
                print(f"➡ parameters(after):\n{new_parameters}\n")

            except Exception as e:
                print(f"❌ Error processing {file}: {e}")

    print("🎯 title / character / rating の削除完了！")
#############################################################################################################

def repair_file_info(folder_path, title="", character="", rating=""):
    """
    指定フォルダ内のPNG画像のEXIF(テキストメタデータ)を読み取り、
    title / character / rating 情報を既存parametersに統合して保存する。

    Args:
        folder_path (str): 画像フォルダのパス
        title (str): タイトル情報
        character (str): キャラクター情報
        rating (str): 評価情報
    """
    clear_file_info(folder_path)  # 既存情報をクリア

    def update_or_append(parameters: str, key: str, value: str) -> str:
        """既存キーを上書き、なければ追記"""
        if not value:
            return parameters  # 空ならスキップ
        pattern = rf"^{key}:\s*.*$"
        line = f"{key}: {value}"
        if re.search(pattern, parameters, flags=re.MULTILINE):
            parameters = re.sub(pattern, line, parameters, flags=re.MULTILINE)
        else:
            if parameters.strip():
                parameters = parameters.strip() + "\n" + line
            else:
                parameters = line
        return parameters
    
    for root, _, files in os.walk(folder_path):
        for file in files:
            if not file.lower().endswith(".png"):
                continue

            img_path = os.path.join(root, file)
            try:
                img = Image.open(img_path)
                info = img.info.copy()
                parameters = info.get("parameters", "")

                print(f"📝 {file} parameters(before): {parameters}")

                # --- 上書きまたは追記 ---
                parameters = update_or_append(parameters, "title", title)
                parameters = update_or_append(parameters, "character", character)
                parameters = update_or_append(parameters, "rating", rating)

                # --- PNG情報更新 ---
                pnginfo = PngImagePlugin.PngInfo()
                for k, v in info.items():
                    if isinstance(v, str) and k != "parameters":
                        pnginfo.add_text(k, v)
                pnginfo.add_text("parameters", parameters)
    
                # immich用にImageDescriptionに概要記載
                pnginfo.add_text("ImageDescription", f"Title : {title}\nCharacter : {character}\nRating : {rating}")

                img.save(img_path, pnginfo=pnginfo)
                print(f"✅ {file} に保存完了")
                print(f"➡ parameters(after):\n{parameters}\n")

            except Exception as e:
                print(f"❌ Error processing {file}: {e}")

    print("🎯 All done!")

#############################################################################################################
if __name__ == '__main__':
    folder_path = ROOT_PATH + "/moca aoba/r18+"
    # ファイル名リネーム
    # rename_files(folder_path, character_name="ran mitake", force_replace=True)

    repair_file_info(folder_path, title="bang-dream", character="moca aoba", rating="r18+")
    
    # 消去する場合はこちら
    # clear_file_info(folder_path)