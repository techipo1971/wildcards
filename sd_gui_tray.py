import requests
import base64
import json
import os
from datetime import datetime
import yaml  # YAMLファイルを扱うために追加
import random  # ランダム選択のために追加
import itertools
import search_yaml

# Web UIのAPIエンドポイント
url = "http://127.0.0.1:7860/sdapi/v1/txt2img"

# プロンプトを読み込むYAMLファイル名
YAML_FILE = 'chara.yaml'
SEQ_FILE = 'sequence.yaml'  # 連番管理用ファイル

POSITIVE = "__il/quality/positive__,"
# POSITIVE = "__il/quality/pos-simple__,"
STYLE = "<lora:Realistic_Anime_-_Illustrious:0.35> illustriousanime, <lora:PHM_style_IL_v3.3:0.8>, <lora:illustriousXLv01_stabilizer_v1.185c:0.2>,"

SFW = ",1girl,__sfw/*__," + POSITIVE + STYLE
ERO = ",1girl,__ero/*__," + POSITIVE + STYLE
R18 = ",1girl,__nude/*__, r18, nsfw," + POSITIVE + STYLE
R18_PLUS = ",1girl,__nsfw/*__, r18+, nsfw," + POSITIVE + STYLE

# 生成リスト（あとでキャラプロンプトと結合する）
# GEN_LIST = [SFW]
GEN_LIST = [ERO, R18, R18_PLUS]

#############################################################################################################

### 作品フィルター
# TITLE = 'fire-force'

### ピックアップ
# PICKUP = ['suguha kirigaya']

### シナリオ名
# SCENARIO_NAME = 'gym-uniform'

### キーワード
# KEYWORD = 'lactation'

#############################################################################################################

BATCH_COUNT = 64        # バッチカウント
CHARACTER_NUMBER = 1   # キャラ数・繰り返し回数

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
            characters.append({'name': data['name'], 'prompt': data['prompt'][0]})
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
    # YAMLファイルからプロンプトを読み込む
    try:
        with open(YAML_FILE, 'r', encoding='utf-8') as f:
            yaml_data = yaml.safe_load(f)
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

    # 全てのキャラクター情報を抽出
    return extract_characters_from_yaml(yaml_data)

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
    
    # 履歴データの読み出し
    try:
        with open('history.txt', 'r') as f:
            while True:
                history_data = [line.strip() for line in f.readlines()]
                break
    except: 
        history_data = None
        pass

    while True:  
        # 抽出したキャラクターリストからランダムで1つ選択
        re_choice = False
        selected_character = random.choice(all_characters)
        char_name = selected_character['name']
        char_prompt = ','.join(selected_character['prompt'].splitlines()) 

        # 履歴データチェック
        if not history_data:
            print("no history data")
            break
        else:
            for prompt in history_data:
                if char_prompt in prompt:  
                    print('Used Character selected!! -> ' + char_name)
                    print("Re-choice !!")
                    re_choice = True
                    continue

            if not re_choice:
            # キャラ確定
                print("unused character selected -> " + char_name)
                break            

    # 履歴データにキャラ名とプロンプトを追記
    with open('history.txt', 'a') as f:
        f.write(char_name +','+char_prompt+'\n') 
    
    return char_prompt

#############################################################################################################
def generate_img(payload, output_folder):
    try:
        # APIにPOSTリクエストを送信
        response = requests.post(url=url, json=payload)
        response.raise_for_status() # エラーがあれば例外を発生させる

        r = response.json()

        # レスポンスの中から画像データ（base64エンコード）を取得
        for idx, img_data in enumerate(r['images']):
            # 画像をデコードしてファイルに保存
            # ファイル名にタイムスタンプとプロンプトの一部を使い、分かりやすくする
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            
            # --- ここでファイル名を変更 ---
            # キャラクター名とタイムスタンプを使ってファイル名を生成
            # filename = f"{char_name}_{timestamp}_{idx+1}.png"
            filename = f"{timestamp}_{idx+1}.png"
            output_path = os.path.join(output_folder, filename)

            with open(output_path, 'wb') as f:
                f.write(base64.b64decode(img_data))
            
            print(f"Image saved to: {output_path}")

    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

#############################################################################################################
def set_payload(positive, negative="__il/quality/negative__", steps=25, seed=-1):
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
        "n_iter": BATCH_COUNT,
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
def main(char_prompt, list=GEN_LIST, seed=-1):
    """
    メインの処理を実行する関数
    """
    # 生成したい画像のプロンプトをリストで用意
    prompts_to_generate = [char_prompt + item for item in list]

    # 画像を保存するフォルダを作成
    output_folder = "C:\StabilityMatrix\Images\generated_images"
    os.makedirs(output_folder, exist_ok=True)

    # 各プロンプトで画像を生成
    # for i, prompt in enumerate(prompts_to_generate):
    for prompt in prompts_to_generate:
        print(f"Prompt: {prompt}")

        payload = set_payload(prompt, seed=seed)
        
        # 画像生成
        generate_img(payload, output_folder)

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

    # キーワード検索
    keyword_mode = False
    try:
        if(isinstance(KEYWORD, str)):
            # キーワード指定
            print('--- Keyword search generation ---')
            gen_keyword_list = [item + POSITIVE + STYLE + ", r18+, nsfw," for item in search_yaml.search_yaml_in_folder('.', KEYWORD)]
            print(f"Keyword search results: {len(gen_keyword_list)} items")
            keyword_mode = True
    except:
        print('--- Random generation ---')
        pass

    seq_mode = False
    try:
        if(isinstance(SCENARIO_NAME, str)):
            # シナリオ指定
            print('--- Scenario generation ---')
            gen_seq_list, seed = create_seq_prompts()

            seq_mode = True
    except:
        print('--- Random generation ---')
        seq_mode = False
        pass

    try:
        if(isinstance(PICKUP, list)):
            # ピックアップ指定キャラ数分　生成
            print('--- Pick up generation ---')
            selected_list = []
            for sel, prompt in itertools.product(PICKUP, all_characters):
                if sel in prompt['name']:
                    selected_list.append(','.join(prompt['prompt'].splitlines()))

            for char_prompt in selected_list:
                if keyword_mode:
                    # キーワード指定
                    main(char_prompt, gen_keyword_list)
                elif seq_mode: 
                    # シナリオ指定
                    print('--- Scenario generation ---')
                    main(char_prompt, gen_seq_list, seed)
                else:
                    main(char_prompt)
        else:
            print('PICKUP list definition error!!')
    except:
        print('--- Random generation ---')
        # 指定キャラ数分　ランダム抽出で繰り返し
        for i in range(CHARACTER_NUMBER):
            char_prompt = select_random_character(all_characters)
            if keyword_mode:
                # キーワード指定
                main(char_prompt, gen_keyword_list)
            elif seq_mode: 
                # シナリオ指定
                print('--- Scenario generation ---')
                main(char_prompt, gen_seq_list, seed)
            else:
                main(char_prompt)

    print("\nTask completed!")

