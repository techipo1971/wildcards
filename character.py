import yaml
import random  # ランダム選択のために追加
import notion
import itertools
from typing import Dict, Any

# プロンプトを読み込むYAMLファイル名
YAML_FILE = 'chara.yaml'

### ピックアップ
PICKUP = ['rem', 'ram', 'emilia']

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
def select_random_character(all_characters):
    if not all_characters:
        print(f"[Error] No character entries with 'name' and 'prompt' found in {YAML_FILE}.")
        return
    
    while True:  
        selected_character = random.choice(all_characters)
        # notionデータベースをチェック
        is_found = notion.check_keyword_in_character(selected_character['name'])
        if not is_found:
            print("no history data")
            break
        else:
            print('Used Character selected!! -> ' + selected_character['name'])
            print("Re-choice !!")
            continue

    return selected_character

#############################################################################################################
def generate_list(mode, c_num):
    selected_list = []
    if mode == 'pick up':
        if(isinstance(PICKUP, list)):
            # ピックアップ指定キャラ数分　生成
            mode = 'pick up'
            for sel, prompt in itertools.product(PICKUP, ALL_CHARACTERS):
                if sel == prompt['name']:
                    selected_list.append(prompt)
        else:
            print('PICKUP list definition error!!')
    elif mode == 'yuri':
        selected_list = []
        for i in range(int(c_num)):
            char_1st = select_random_character(ALL_CHARACTERS) 
            char_2nd = select_random_character(ALL_CHARACTERS) 
            selected_list.append({'name': f"{char_1st['name']}_and_{char_2nd['name']}", 'prompt': f"{char_1st['prompt']}, {char_2nd['prompt']}", 'title': f"{char_1st['title']}_and_{char_2nd['title']}"})  
    else:
        # 指定キャラ数分　ランダム抽出で繰り返し
        selected_list = [select_random_character(ALL_CHARACTERS) for i in range(int(c_num))]
        
    return selected_list
#############################################################################################################

# 全てのキャラクター情報を抽出
ALL_CHARACTERS = load_all_characters()

#############################################################################################################
if __name__ == '__main__':

    selected_characters = select_random_character(ALL_CHARACTERS)

    print(ALL_CHARACTERS)