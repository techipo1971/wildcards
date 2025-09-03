import requests
import base64
import json
import os
from datetime import datetime
import yaml  # YAMLファイルを扱うために追加
import random  # ランダム選択のために追加


# Web UIのAPIエンドポイント
url = "http://127.0.0.1:7860/sdapi/v1/txt2img"

# プロンプトを読み込むYAMLファイル名
YAML_FILE = 'chara.yaml'

POSITIVE = "__il/quality/positive__,"
STYLE = "<lora:Realistic_Anime_-_Illustrious:0.35> illustriousanime, <lora:PHM_style_IL_v3.3:0.8>, <lora:illustriousXLv01_stabilizer_v1.185c:0.2>,"

ERO = ",1girl,__ero/*__," + POSITIVE + STYLE
R18 = ",1girl,__nude/*__, r18, nsfw," + POSITIVE + STYLE
R18_PLUS = ",1girl,__nsfw/*__, r18+, nsfw," + POSITIVE + STYLE

#############################################################################################################

BATCH_COUNT = 64        # バッチカウント
CHARACTER_NUMBER = 3   # キャラ数・繰り返し回数

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
def main():
    """
    メインの処理を実行する関数
    """

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

    # 全てのキャラクター情報を抽出
    all_characters = extract_characters_from_yaml(yaml_data)

    if not all_characters:
        print(f"[Error] No character entries with 'name' and 'prompt' found in {YAML_FILE}.")
        return

    # 抽出したキャラクターリストからランダムで1つ選択
    selected_character = random.choice(all_characters)
    char_name = selected_character['name']
    char_prompt = selected_character['prompt']

    # # 生成したい画像のプロンプトをリストで用意
    prompts_to_generate = [
        char_prompt + ERO,
        char_prompt + R18,
        char_prompt + R18_PLUS
    ]

    # 画像を保存するフォルダを作成
    output_folder = "C:\StabilityMatrix\Images\generated_images"
    os.makedirs(output_folder, exist_ok=True)

    # # 各プロンプトで画像を生成
    for i, prompt in enumerate(prompts_to_generate):
        print(f"Prompt: {prompt}")

    #     # APIに送るデータ（ペイロード）を定義
    #     # 他にも多くのパラメータが指定可能です（例: width, height, sampler_nameなど）
    #     # 詳しくは http://127.0.0.1:7860/docs を参照
        payload = {
            "prompt": prompt,
            "negative_prompt": "__il/quality/negative__",
            "steps": 28,
            "cfg_scale": 4,
            "width": 896,
            "height": 1344,
            "sampler_name": "Euler a",
            "scheduler": "Automatic",
            "n_iter": BATCH_COUNT,
            "seed": -1, 
        }

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

    print("--- All images generated! ---")

if __name__ == '__main__':
    # 最初にライブラリがインストールされているか確認
    try:
        import yaml
    except ImportError:
        print("The 'PyYAML' library is not installed.")
        print("Please install it by running: pip install pyyaml")
        exit()
    
    # 指定キャラ数分　ランダム抽出で繰り返し
    for i in range(CHARACTER_NUMBER):
        main()

    print("\nTask completed!")

