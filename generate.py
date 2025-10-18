import requests
import base64
import json
import io
import os
from datetime import datetime
import yaml  # YAMLファイルを扱うために追加
import random  # ランダム選択のために追加
import itertools
import search_yaml
import stamp2
import notion
import png_info
from typing import Dict, Any
import immich as imm

from PIL import Image, PngImagePlugin

import slack

import argparse
from InquirerPy import inquirer

# Web UIのAPIエンドポイント
url = "http://127.0.0.1:7860/sdapi/v1/txt2img"

# プロンプトを読み込むYAMLファイル名
YAML_FILE = 'chara.yaml'
SEQ_FILE = 'sequence.yaml'  # 連番管理用ファイル

POSITIVE = "__il/quality/positive__,"
# POSITIVE = "__il/quality/pos-simple__,"
STYLE = "<lora:Realistic_Anime_-_Illustrious:0.35> illustriousanime, <lora:PHM_style_IL_v3.3:0.8>, <lora:illustriousXLv01_stabilizer_v1.185c:0.2>,"

# 保存先定義
DESTINATION_FOLDER = "Z:/StabilityMatrix/Images/workspace"
RELEASE_FOLDER = "Z:/StabilityMatrix/Images/forRelease"

# ウォータマークスタンプ
STAMP_IMG = "C:/tmp/Mabo.AiArt2.png"  # 固定パス（必要なら変更）

SFW = ",1girl,__sfw/*__," + POSITIVE + STYLE
ERO = ",1girl,__ero/*__," + POSITIVE + STYLE
R18 = ",1girl,__nude/*__, r18, nsfw," + POSITIVE + STYLE
R18_PLUS = ",1girl,__nsfw/*__, r18+, nsfw," + POSITIVE + STYLE
YURI = ",2girls, __yuri__, yuri, nsfw," + POSITIVE + STYLE

# 生成リスト（あとでキャラプロンプトと結合する）
# GEN_LIST = [SFW]
# GEN_LIST = [ERO]
GEN_LIST = [ERO, R18, R18_PLUS]

#############################################################################################################

### 作品フィルター
# TITLE = 'my-hero-academia'

### ピックアップ
# PICKUP = ['rem']

### シナリオ名
SCENARIO_NAME = 'dakimakura-of'

### キーワード
KEYWORD = 'lactation'

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

    # # YAMLファイルからプロンプトを読み込む
    # try:
    #     with open(YAML_FILE, 'r', encoding='utf-8') as f:
    #         yaml_data = yaml.safe_load(f)

    # except FileNotFoundError:
    #     print(f"[Error] YAML file not found: {YAML_FILE}")
    #     return
    # except yaml.YAMLError as e:
    #     print(f"[Error] Could not parse YAML file: {e}")
    #     return

    # # 作品指定の場合, 作品の辞書を返す    
    # if isinstance(yaml_data, dict):
    #     if key == 'all':
    #         return extract_characters_from_yaml(yaml_data)
    #     elif key in yaml_data.keys():
    #         print(f"--- Title filter -> {key} ---")
    #         return extract_characters_from_yaml(yaml_data[key])

    # # 全てのキャラクター情報を抽出
    # return extract_characters_from_yaml(yaml_data)
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
def load_seq_data():
    # 連番管理用YAMLファイルからデータを読み込む
    try:
        with open(SEQ_FILE, 'r', encoding='utf-8') as f:
            seq_data = yaml.safe_load(f)
            if not isinstance(seq_data, dict):
                print(f"[Error] Invalid format in {SEQ_FILE}. Expected a dictionary.")
                return {}
            return seq_data
    except FileNotFoundError:
        print(f"[Error] Sequence YAML file not found: {SEQ_FILE}")
        return {}
    except yaml.YAMLError as e:
        print(f"[Error] Could not parse sequence YAML file: {e}")
        return {}

#############################################################################################################
def select_random_character(all_characters):
    if not all_characters:
        print(f"[Error] No character entries with 'name' and 'prompt' found in {YAML_FILE}.")
        return
    
    while True:  
        selected_character = random.choice(all_characters)
        # notionデータベースをチェック
        if not notion.check_keyword_in_character(selected_character['name']):
            print("no history data")
            break
        else:
            print('Used Character selected!! -> ' + selected_character['name'])
            print("Re-choice !!")
            continue

    return selected_character

#############################################################################################################
def generate_img(character, payload, output_folder, rating='safe'):
    try:
        # APIにPOSTリクエストを送信
        response = requests.post(url=url, json=payload)
        response.raise_for_status() # エラーがあれば例外を発生させる

        r = response.json()

        img_list = []
        # レスポンスの中から画像データ（base64エンコード）を取得
        for idx, img_data in enumerate(r['images']):
            # 画像をデコードしてファイルに保存
            # ファイル名にタイムスタンプとプロンプトの一部を使い、分かりやすくする
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
            # キャラクター名とタイムスタンプを使ってファイル名を生成
            filename = f"{character['name']}_{timestamp}_{idx+1}.png"
            output_path = os.path.join(output_folder, filename)
            img_list.append(output_path)

           # 画像をデコード
            img_bytes = base64.b64decode(img_data)
            img = Image.open(io.BytesIO(img_bytes))

            ### DB処理 ###
            # PNG用のメタ情報
            png_info = PngImagePlugin.PngInfo()

            # payload の各要素を tEXt に追加
            for key, value in payload.items():
                # 数値やブールは文字列に変換
                png_info.add_text(key, str(value))

            # キャラクター名も追加
            png_info.add_text("title", character['title'])
            png_info.add_text("character", character['name'])
            png_info.add_text("rating", rating)

            # immich用にImageDescriptionに概要記載
            png_info.add_text("ImageDescription", f"Title : {character['title']}\nCharacter : {character['name']}\nRating : {rating}")

            # 画像保存
            img.save(output_path, pnginfo=png_info)
            print(f"Image saved to: {output_path}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

    return img_list

#############################################################################################################
def set_payload(positive, negative="__il/quality/negative__", steps=25, seed=-1, batch_count=1):
    # 詳しくは http://127.0.0.1:7860/docs を参照
    payload = {
        "prompt": positive,
        "negative_prompt": negative,
        "steps": steps,
        "cfg_scale": 3,
        "width": 1024,
        "height": 1536,
        "sampler_name": "Euler a",
        "scheduler": "Automatic",
        "n_iter": batch_count,
        "seed": seed,  # -1でランダムシード
        # --- Hires. fix パラメータ ---
        "enable_hr": False,                         # Hires. fix を有効化
        "hr_scale": 2,                              # 2倍にアップスケール
        "hr_upscaler": "4x-UltraSharp",             # アップスケーラーの種類
        "hr_second_pass_steps": 0,                  # Hires steps 0に設定（元のと同じStep）
        "denoising_strength": 0.3                   # Denoising strengthを0.5に設定
    }

    return payload

#############################################################################################################
def main(char_prompt, mode, list=GEN_LIST, seed=-1, batch_count=1):
    """
    メインの処理を実行する関数
    """
    # 生成したい画像のプロンプトをリストで用意
    prompts_to_generate = [char_prompt['prompt'] + item for item in list]

    # レーティング設定
    rating = 'safe'
    root_folder = os.path.join(DESTINATION_FOLDER, char_prompt['name'])
    os.makedirs(root_folder, exist_ok=True)

    # 各プロンプトで画像を生成
    for i, prompt in enumerate(prompts_to_generate):

        if("r18, nsfw" in prompt):
            rating = "r18"
        elif("r18+, nsfw" in prompt):
            rating = "r18+"    
        elif("yuri, nsfw," in prompt):
            rating = "yuri"    

        if rating == 'safe':
            output_folder = root_folder
        else:
            # NSFWはサブフォルダへ
            output_folder = os.path.join(root_folder, rating)
            os.makedirs(output_folder, exist_ok=True)

        print(f"Character: {char_prompt['name']} \nRating: {rating} \nStart generating...")

        payload = set_payload(prompt, seed=seed, batch_count=batch_count)        
        img_list = generate_img(char_prompt, payload, output_folder, rating=rating)

        # slackへの送信処理
        message = f"\n Mode : {mode}\ncharacter : {char_prompt['name']}\nTitle : {char_prompt['title']}\nBatch cnt : {batch_count}\nRating : {rating}"
        if mode == 'scenario':
            message += f"\n Seq : {i+1}/{len(prompts_to_generate)}"

        # slackに送信
        slack.send_slack_img(random.choice(img_list) , message)

        # notion データベースに追加
        notion.add_record(
            character= char_prompt['name'],
            date=datetime.now().date().isoformat(),
            title=char_prompt['title'],
            url=output_folder,
            batch_cnt=batch_count,
            mode_list=[mode],
            rating_list=[rating]
        )
        
        # immich update
        imm.update_exif_info_to_postgres(output_folder)

        # ウォーターマーク押す
        if rating == 'safe':
            stamp2.add_stamp(output_folder, RELEASE_FOLDER, STAMP_IMG)

    print("--- All images generated! ---")


#############################################################################################################
def create_seq_prompts():
    seq_data = load_seq_data()
    if not seq_data or 'seq' not in seq_data or SCENARIO_NAME not in seq_data['seq']:
        print(f"[Error] Scenario '{SCENARIO_NAME}' not found in {SEQ_FILE}.")
        return []

    gen_seq_list = [item + POSITIVE + STYLE + ", r18+, nsfw," for item in seq_data['seq'][SCENARIO_NAME]]
    # 19桁の範囲を指定（10^18 ～ 10^19 - 1）
    seed = random.randint(10**18, 10**19 - 1)
    print(f"Seed: {seed}")

    return gen_seq_list, seed

#############################################################################################################
if __name__ == '__main__':

    # 引数パース処理
    parser = argparse.ArgumentParser(description="引数のサンプル")
    parser.add_argument("--count", type=int, help="Batch countを入力してください")
    parser.add_argument("--char_num", type=int, help="character numberを入力してください")
    parser.add_argument("--mode", help="modeを入力してください")

    args = parser.parse_args()

    if not args.count:
        args.count = input("count ? : ")

    if not args.char_num:
        args.char_num = input("character number ? : ")

    if not args.mode:
        args.mode = inquirer.select(
            message = "mode ? :",
            choices = ["random", "scenario", "keyword search", "pick up", "yuri"]
        ).execute()

    b_cnt = int(args.count)
    c_num = args.char_num
    mode = args.mode

    print(f"Batch count >>> {b_cnt}")
    print(f"Character number >>> {c_num} ")
    print(f"Mode >>> {mode}")

    # 最初にライブラリがインストールされているか確認
    try:
        import yaml
    except ImportError:
        print("The 'PyYAML' library is not installed.")
        print("Please install it by running: pip install pyyaml")
        exit()

    # 全てのキャラクター情報を抽出
    try:
        all_characters = load_all_characters(TITLE)
    except:
        all_characters = load_all_characters()

    if mode == 'keyword search':
        # キーワード検索
        try:
            if(isinstance(KEYWORD, str)):
                gen_keyword_list = [item + POSITIVE + STYLE + ", r18+, nsfw," for item in search_yaml.search_yaml_in_folder('.', KEYWORD)]
                print(f"Keyword search results: {len(gen_keyword_list)} items")
        except:
            pass
    elif mode == 'scenario':
        try:
            if(isinstance(SCENARIO_NAME, str)):
                # シナリオ指定
                mode = 'scenario'
                gen_seq_list, seed = create_seq_prompts()
        except:
            pass

    # キャラリスト初期化
    selected_list = []
    if mode == 'pick up':
        if(isinstance(PICKUP, list)):
            # ピックアップ指定キャラ数分　生成
            mode = 'pick up'
            for sel, prompt in itertools.product(PICKUP, all_characters):
                if sel in prompt['name']:
                    selected_list.append(prompt)
        else:
            print('PICKUP list definition error!!')
    elif mode == 'yuri':
        selected_list = []
        for i in range(int(c_num)):
            char_1st = select_random_character(all_characters) 
            char_2nd = select_random_character(all_characters) 
            selected_list.append({'name': f"{char_1st['name']}_and_{char_2nd['name']}", 'prompt': f"{char_1st['prompt']}, {char_2nd['prompt']}", 'title': f"{char_1st['title']}_and_{char_2nd['title']}"})  
    else:
        # 指定キャラ数分　ランダム抽出で繰り返し
        selected_list = [select_random_character(all_characters) for i in range(int(c_num))]

    for char_prompt in selected_list:
        if mode == 'keyword search':
            # キーワード指定
            main(char_prompt, mode, gen_keyword_list, batch_count=b_cnt)
        elif mode == 'scenario':
            # シナリオ指定
            main(char_prompt, mode, gen_seq_list, seed, batch_count=b_cnt)
        elif mode == 'yuri':
            # 百合モード
            main(char_prompt, mode, list=[YURI], batch_count=b_cnt)
        else:
            main(char_prompt, mode, batch_count=b_cnt)

    # Notion Generate DB update
    notion.update_Generate_DB()
# ======================