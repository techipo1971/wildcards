import os
import yaml
import time
import shutil
from tkinter import filedialog, Tk
from PIL import Image
import stamp2

CHARA_YAML_PATH = "C:/StabilityMatrix/Packages/Stable Diffusion WebUI/extensions/sd-dynamic-prompts/wildcards/chara.yaml"
DESTINATION_FOLDER = "Z:/StabilityMatrix/Images/workspace"
RELEASE_FOLDER = "Z:/StabilityMatrix/Images/forRelease"

# 画像からメタデータを取得
def get_metadata(filepath):
    try:
        with Image.open(filepath) as img:
            return img.info.get("parameters", "")   
    except Exception as e:
        print(f"メタデータ取得エラー: {filepath}, {e}")
        return {}

# YAML からキャラ名とキーを読み込み
def load_chara_yaml():
    with open(CHARA_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    chara_list = []
    chara_names = set()
    for work, chars in data.items():
        if not isinstance(chars, dict):
            continue
        for char, info in chars.items():
            if not isinstance(info, dict):
                continue
            name = info.get("name")
            if not name:
                continue
            chara_names.add(name)
            prompts = info.get("prompt", [])
            if isinstance(prompts, list):
                for p in prompts:
                    if isinstance(p, str) and p.strip().startswith("${trg:"):
                        key = p.strip()[6:].split("}")[0]
                        chara_list.append((name, key))
    return chara_list, chara_names

# 安全にリネーム（PermissionError 対策）
def safe_rename(src, dst, retries=3, delay=0.5):
    for i in range(retries):
        try:
            os.rename(src, dst)
            return True
        except PermissionError:
            print(f"リネーム失敗（リトライ {i+1}/{retries}）: {src}")
            time.sleep(delay)
    print(f"リネーム最終失敗: {src}")
    return False

# 安全にファイルを移動（PermissionError 対策）
def safe_move(src, dst, retries=3, delay=0.5):
    for i in range(retries):
        try:
            shutil.move(src, dst)
            return True
        except PermissionError:
            print(f"ファイル移動失敗（リトライ {i+1}/{retries}）: {src}")
            time.sleep(delay)
        except Exception as e:
            print(f"ファイル移動エラー: {src} -> {dst}, {e}")
            return False
    print(f"ファイル移動最終失敗: {src}")
    return False

def main():


    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="テスト画像フォルダを選択")
    if not folder:
        print("フォルダが選択されませんでした")
        return

    # 保存先親フォルダが存在しない場合は作成
    if not os.path.exists(DESTINATION_FOLDER):
        os.makedirs(DESTINATION_FOLDER)
        print(f"保存先親フォルダを作成しました: {DESTINATION_FOLDER}")

    chara_list, chara_names = load_chara_yaml()

    for filename in os.listdir(folder):
        if not filename.lower().endswith((".png", ".jpg")):
            continue

        if filename.startswith("unknown_") or any(
            name and filename.startswith(name + "_") for name in chara_names
        ):
            continue

        filepath = os.path.join(folder, filename)
        metadata = get_metadata(filepath)
        prompt_text = str(metadata)

        matches = sorted(set(name for name, key in chara_list if key in prompt_text))


        if matches:
            prefix = "+".join(matches)
        else:
            prefix = "unknown"

        # フォルダとファイル名を構築
        dest_folder = os.path.join(DESTINATION_FOLDER, prefix)
        new_filename = f"{prefix}_{filename}"
        # スタンプ用フォルダを保持（R18、R18+以外）
        stamp_folder = dest_folder  

        # ratingをチェック(safe/r18/r18+)してサブフォルダへ
        rating = "safe"

        if("r18, nsfw" in prompt_text):
            rating = "r18"
            dest_folder = os.path.join(dest_folder, rating)
        elif("r18+, nsfw" in prompt_text):
            rating = "r18+"
            dest_folder = os.path.join(dest_folder, rating)
            
        dest_filepath = os.path.join(dest_folder, new_filename)

        print(f"ファイル: {filename}")
        print(f"検出されたキャラクター: {matches}")
        print(f"rating: {rating}")
        print(f"移動先フォルダ: {dest_folder}")
        print(f"新ファイル名: {new_filename}")

        # キャラクターごとのフォルダが存在しない場合は作成
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)
            print(f"キャラクターごとのフォルダを作成しました: {dest_folder}")

        # ファイルを新しい場所に移動
        if safe_move(filepath, dest_filepath):
            print(f"ファイルを移動しました: {filename} -> {dest_filepath}")
        else:
            print(f"ファイル移動に失敗しました: {filename}")

    # スタンプ画像を選択
    stamp_image_path = r"C:\tmp\Mabo.AiArt2.png"  # 固定パス（必要なら変更）
    if not stamp_image_path:
        print("スタンプ画像が選択されていません。終了します。")
        return

    # 画像にスタンプを追加する処理を実行
    stamp2.add_stamp(stamp_folder, RELEASE_FOLDER, stamp_image_path)

    print("処理が完了しました。")


        # if matches:
        #     prefix = matches
        #     print(f"リネーム候補: {filename} → {prefix}")
        #     prefix = "+".join(matches)
        # else:
        #     print(f"リネーム候補なし: {filename} → {prefix}")
        #     if unknown_added:
        #         continue
        #     prefix = "unknown"
        #     unknown_added = True

        # new_filename = f"{prefix}_{filename}"
        # new_filepath = os.path.join(folder, new_filename)

        # if safe_rename(filepath, new_filepath):
        #     print(f"リネーム: {filename} → {new_filename}")

if __name__ == "__main__":
    main()
