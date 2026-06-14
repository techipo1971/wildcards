import os
import re
import yaml
from pathlib import Path
from typing import Dict, Any
from PIL import Image, PngImagePlugin
from dotenv import load_dotenv

load_dotenv()

ROOT_PATH = os.getenv("ROOT_PATH")

# プロンプトを読み込むYAMLファイル名
YAML_FILE = 'chara.yaml'


#############################################################################################################
def extract_characters_from_yaml(data):
    """
    YAMLデータから 'name' と 'prompt' のペアを再帰的に抽出し、
    辞書のリストとして返す関数。
    """
    characters = []
    if isinstance(data, dict):
        # この辞書がキャラクター情報（nameとpromptキーを持つ）かどうかをチェック
        if 'name' in data and 'prompt' in data and isinstance(data['prompt'], list) and data['prompt']:
            # キャラクター情報が見つかったのでリストに追加
            # promptリストの最初の要素を使用すると仮定
            keys = list(data.keys())
            characters.append({'name': data['name'], 'prompt': data['prompt'][0], 'title': data['title']})
        else:
            # キャラクター情報ではない場合、さらに下の階層を探索
            for key, value in data.items():
                characters.extend(extract_characters_from_yaml(value))
    elif isinstance(data, list):
        # リストの場合は、各要素に対して再帰的に探索
        for item in data:
            characters.extend(extract_characters_from_yaml(item))
    return characters

#############################################################################################################
def load_all_characters(key='all'):

    try:
        yaml_data = load_yaml_with_titles(YAML_FILE)
    except FileNotFoundError:
        print(f"[Error] YAML file not found: {YAML_FILE}")
        return
    except yaml.YAMLError as e:
        print(f"[Error] Could not parse YAML file: {e}")
        return

    # 作品指定の場合, 作品の辞書を返す    
    if isinstance(yaml_data, dict):
        if key == 'all':
            return extract_characters_from_yaml(yaml_data)
        elif key in yaml_data.keys():
            print(f"--- Title filter -> {key} ---")
            return extract_characters_from_yaml(yaml_data[key])

#############################################################################################################
def load_yaml_with_titles(yaml_path: str) -> Dict[str, Dict[str, Any]]:
    """
    YAMLを読み込み、各作品・各キャラクターに title キーを追加して辞書で返す

    返却形式:
    {
        "bang-dream": {
            "ran": { "name": ..., "prompt": ..., "title": "bang-dream" },
            ...
        },
        "love-live": {
            "chika": { "name": ..., "prompt": ..., "title": "love-live" },
            ...
        }
    }
    """
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("YAMLのトップレベルが辞書形式ではありません")

    result = {}

    # 作品ごとに処理
    for work_key, work_content in data.items():
        if not isinstance(work_content, dict):
            continue  # 作品の中身が辞書でない場合はスキップ

        # 各キャラクターに title を追加
        for char_key, char_data in work_content.items():
            if isinstance(char_data, dict):
                char_data["title"] = work_key

        # 作品名をキーにして結果に追加
        result[work_key] = work_content

    return result
#############################################################################################################

def rename_files(folder_path: str, character_name: str, force_replace: bool = False):
    """
    PNGファイル名を指定ルールでリネームする。

    - 通常: (キャラ名)_YYYYMMDD_(連番).png
    - unknown_ や既存キャラ名も置き換え対象
    - force_replace=True の場合、既存キャラ名を強制上書き
    """

    try:
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(".png")]
        if not files:
            print("❌ PNGファイルが見つかりません。")
            return
    except Exception as e:
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
        # パターン: noel_20250905090205_1.png
        m4 = re.match(r"([a-zA-Z0-9]+)_?(\d{8})\d{6}_", file)

        if m1:
            date = m1.group(1)
        elif m2:
            date = m2.group(2)
        elif m3:
            date = m3.group(1)
        elif m4:
            date = m4.group(2)

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
def clear_file_info(img_path):
    """
    指定PNG画像の 'parameters' テキストから
    title, character, rating の行を削除する。

    Args:
        img_path (str): 画像ファイルのパス
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

    try:
        img = Image.open(img_path)
        info = img.info.copy()
        parameters = info.get("parameters", "")

        new_parameters = remove_keys(parameters)

        if new_parameters == parameters:
            print(f"ℹ {img_path} に削除対象なし")
            return

        # --- PNG情報更新 ---
        pnginfo = PngImagePlugin.PngInfo()
        for k, v in info.items():
            if isinstance(v, str) and k != "parameters":
                pnginfo.add_text(k, v)
        pnginfo.add_text("parameters", new_parameters)

        img.save(img_path, pnginfo=pnginfo)
        print(f"✅ {img_path} 更新完了")

    except Exception as e:
        print(f"❌ Error processing {img_path}: {e}")


#############################################################################################################
def clear_files_info(folder_path):
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

    for file in os.listdir(folder_path):
        if not file.lower().endswith(".png"):
            continue

        img_path = os.path.join(folder_path, file)
        try:
            img = Image.open(img_path)
            info = img.info.copy()
            parameters = info.get("parameters", "")

            # print(f"🧹 {file} parameters(before):\n{parameters}")

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
            # print(f"➡ parameters(after):\n{new_parameters}\n")

        except Exception as e:
            print(f"❌ Error processing {file}: {e}")

    print("🎯 title / character / rating の削除完了！")
#############################################################################################################
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

#############################################################################################################
def save_exif_info(img_path, title="", character="", rating=""):

    img = Image.open(img_path)
    info = img.info.copy()
    parameters = info.get("parameters", "")

    # print(f"📝 {img_path} parameters(before): {parameters}")

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
    print(f"✅ {img_path} に保存完了")
    # print(f"➡ parameters(after):\n{parameters}\n")

#############################################################################################################
def repair_files_info(folder_path, title="", character="", rating=""):
    """
    指定フォルダ内のPNG画像のEXIF(テキストメタデータ)を読み取り、
    title / character / rating 情報を既存parametersに統合して保存する。

    Args:
        folder_path (str): 画像フォルダのパス
        title (str): タイトル情報
        character (str): キャラクター情報
        rating (str): 評価情報
    """
    # clear_file_info(folder_path)  # 既存情報をクリア

    for file in os.listdir(folder_path):
        if not file.lower().endswith(".png"):
            print(f'❌ No png file -> {folder_path}')

        img_path = os.path.join(folder_path, file)
        try:
            # clear_file_info(img_path)
            save_exif_info(img_path, title, character, rating)
        except Exception as e:
            print(f"❌ Error processing {file}: {e}")

    print("🎯 All done!")

#############################################################################################################
def search_title_from_character_name(target_name):
    """
    chara.yamlからキャラ名を元にタイトルをサーチ
    """
    for item in load_all_characters():
        if item['name'] == target_name:
            print(f"✅ Found title -> {item['title']}")
            return item['title']

    print(f"❌ No found title -> character name : {target_name}")
    return None
#############################################################################################################
def get_exif_info(img_path):
    """
    PNG画像のEXIF(テキストメタデータ)を読み取る。
    """
    try:
        with open(img_path, "rb") as f:
            img = PngImagePlugin.PngImageFile(f)
            exif = img.info

            # parameters があれば辞書に変換して返す
            parameters = exif.get("parameters")
            img_desc = exif.get("ImageDescription")
            if img_desc:
                try:
                    img_desc_dict = yaml.safe_load(img_desc)
                    print(img_desc_dict)
                except yaml.YAMLError:
                    print("❌ Failed to parse ImageDescription")
            if parameters:
                try:
                    parameters = "Positive prompt: " + parameters
                    param_dict = parse_sd_metadata(parameters)
                except yaml.YAMLError:
                    print("❌ Failed to parse ImageDescription")

            if img_desc_dict and param_dict:
                return {**img_desc_dict, **param_dict}
            else:
                return {}

    except Exception as e:
        print(f"❌ Error processing {img_path}: {e}")
        return {}


#############################################################################################################
def parse_sd_metadata(text: str) -> dict:

    result = {}

    # Positive Prompt
    pos_match = re.search(
        r"Positive prompt:\s*(.*?)\s*Negative prompt:",
        text,
        re.DOTALL | re.IGNORECASE
    )

    if pos_match:
        result["positive_prompt"] = (
            pos_match.group(1)
            .replace("\n", " ")
            .strip()
        )

    # Negative Prompt
    neg_match = re.search(
        r"Negative prompt:\s*(.*?)\s*Steps:",
        text,
        re.DOTALL
    )

    if neg_match:
        result["negative_prompt"] = (
            neg_match.group(1)
            .replace("\n", " ")
            .strip()
        )

    # Parameters
    param_match = re.search(
        r"Steps:\s*(.*)$",
        text,
        re.DOTALL
    )

    if not param_match:
        return result

    params_text = param_match.group(1)

    # key:value を抽出
    pairs = re.findall(
        r'([A-Za-z0-9 _]+):\s*("[^"]*"|[^,]+)',
        params_text
    )

    for key, value in pairs:

        key = (
            key.strip()
            .lower()
            .replace(" ", "_")
        )

        value = value.strip().strip('"')

        result[key] = value

    # 型変換

    int_keys = [
        "steps",
        "seed",
        "clip_skip"
    ]

    float_keys = [
        "cfg_scale"
    ]

    for k in int_keys:
        if k in result:
            try:
                result[k] = int(result[k])
            except:
                pass

    for k in float_keys:
        if k in result:
            try:
                result[k] = float(result[k])
            except:
                pass

    # Size
    if "size" in result:
        m = re.match(
            r"(\d+)x(\d+)",
            result["size"]
        )

        if m:
            result["width"] = int(m.group(1))
            result["height"] = int(m.group(2))

    return result
#############################################################################################################
if __name__ == '__main__':

    # chracter_name = "shinobu kochou"
    # try:
    #     title_name = search_title_from_character_name(chracter_name)
    # except Exception as e:
    #     print(f"❌ Error processing {chracter_name}: {e}")

    # rating = ["safe", "r18", "r18+"]
    # for r in rating:
    #     folder_path = ROOT_PATH + "/" + chracter_name
    #     if r and not r.startswith("safe"):
    #         folder_path += f"/{r}"

    #     if Path(folder_path).is_dir():
    #         # ファイル名リネーム
    #         rename_files(folder_path, character_name=chracter_name, force_replace=True)
    #         # EXIF情報修復
    #         repair_files_info(folder_path, title=title_name, character=chracter_name, rating=r)
    #     else:
    #         print(f"⚠ No directory -> {folder_path}")
    
    img_path = r"//192.168.68.100/personal_folder/StabilityMatrix/Images/workspace/aizawa ema/aizawa ema_20260516195117505749_1.png"
    info = get_exif_info(img_path)
    print(info["Title"])
    print(info["Character"])
    print(info["Rating"])
    print(info["positive_prompt"])
