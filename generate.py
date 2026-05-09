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
import immich as imm
import exif_util as exif
import character
from PIL import Image, PngImagePlugin
import slack
import argparse
from InquirerPy import inquirer
import nas_env as nas   #環境情報
import logging
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import censor

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ======================
# 設定
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yaml")
try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
except Exception as e:
    logger.error(f"Could not load config.yaml: {e}")
    exit(1)

# Web UIのAPIエンドポイント
url = config_data.get('api', {}).get('url', "http://127.0.0.1:7860/sdapi/v1/txt2img")
API_RETRIES = config_data.get('api', {}).get('retries', 3)
API_BACKOFF = config_data.get('api', {}).get('backoff_factor', 0.5)

# APIリトライ設定
api_session = requests.Session()
retry = Retry(total=API_RETRIES, connect=API_RETRIES, read=API_RETRIES, backoff_factor=API_BACKOFF)
adapter = HTTPAdapter(max_retries=retry)
api_session.mount('http://', adapter)
api_session.mount('https://', adapter)

# プロンプトを読み込むYAMLファイル名
SEQ_FILE = 'sequence.yaml'  # 連番管理用ファイル

POSITIVE = config_data.get('prompt', {}).get('positive', "__il/quality/positive__,")
STYLE = config_data.get('prompt', {}).get('style', "<lora:RealisticAnimeIXL:0.5>")
NEGATIVE_DEFAULT = config_data.get('prompt', {}).get('negative', "__il/quality/negative__")

# 保存先定義
ROOT_FOLDER = nas.img_dirs['root']
RELEASE_FOLDER = nas.img_dirs['release']
DESTINATION_FOLDER = nas.img_dirs['workspace']   

# ウォータマークスタンプ（環境変数 STAMP_IMG_PATH が未設定の場合はデフォルトパスを使用）
STAMP_IMG = config_data.get('generation', {}).get('stamp_img', os.getenv("STAMP_IMG_PATH", "C:/tmp/Mabo.AiArt2.png"))

# 生成リスト（あとでキャラプロンプトと結合する）
GEN_LIST_RAW = config_data.get('generation', {}).get('lists', [])
GEN_LIST = [item + POSITIVE + STYLE for item in GEN_LIST_RAW]
YURI_RAW = config_data.get('generation', {}).get('yuri', "")
YURI = YURI_RAW + POSITIVE + STYLE if YURI_RAW else ""

#############################################################################################################

### シナリオ名
SCENARIO_NAME = config_data.get('generation', {}).get('scenario_name', '')

### キーワード
KEYWORD = config_data.get('generation', {}).get('keyword', '')

#############################################################################################################
def load_seq_data():
    # 連番管理用YAMLファイルからデータを読み込む
    try:
        with open(SEQ_FILE, 'r', encoding='utf-8') as f:
            seq_data = yaml.safe_load(f)
            if not isinstance(seq_data, dict):
                logger.error(f"Invalid format in {SEQ_FILE}. Expected a dictionary.")
                return {}
            return seq_data
    except FileNotFoundError:
        logger.error(f"Sequence YAML file not found: {SEQ_FILE}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Could not parse sequence YAML file: {e}")
        return {}

#############################################################################################################
def generate_img(character, payload, output_folder, rating='safe'):
    img_list = []
    try:
        # APIにPOSTリクエストを送信
        response = api_session.post(url=url, json=payload)
        response.raise_for_status() # エラーがあれば例外を発生させる

        r = response.json()

        # レスポンスの中から画像データ（base64エンコード）を取得
        for idx, img_data in enumerate(r['images']):
            # ファイル名にタイムスタンプとプロンプトの一部を使い、分かりやすくする
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")  # ミリ秒まで含める
        
            # キャラクター名とタイムスタンプを使ってファイル名を生成
            filename = f"{character['name']}_{timestamp}_{idx+1}.png"
            output_path = os.path.join(output_folder, filename)
            img_list.append(output_path)

            # 画像をデコード
            img_bytes = base64.b64decode(img_data)
            img = Image.open(io.BytesIO(img_bytes))
            info = img.info.copy()
            parameters = info.get("parameters", "")

            ### DB処理 ###
            # PNG用のメタ情報
            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("parameters", parameters)

            # immich用にImageDescriptionに概要記載
            png_info.add_text("ImageDescription", f"Title : {character['title']}\nCharacter : {character['name']}\nRating : {rating}")

            # 画像保存
            img.save(output_path, pnginfo=png_info)

            logger.info(f"Image saved to: {output_path}")

    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")

    if rating != "safe":
        censor.batch_censor(output_folder)

    return img_list

#############################################################################################################
def set_payload(positive, negative=NEGATIVE_DEFAULT, steps=25, seed=-1, batch_count=1):
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
def main(char_prompt, mode, gen_list=GEN_LIST, seed=-1, batch_count=1, current_char_idx=1, total_char_count=1):
    """
    メインの処理を実行する関数
    """
    # 生成したい画像のプロンプトをリストで用意
    prompts_to_generate = [char_prompt['prompt'] + item for item in gen_list]

    # レーティング設定
    rating = 'safe'
    root_folder = os.path.join(DESTINATION_FOLDER, char_prompt['name'])
    os.makedirs(root_folder, exist_ok=True)

    # 各プロンプトで画像を生成
    for i, prompt in enumerate(tqdm(prompts_to_generate, desc=f"Gen: {char_prompt['name']}")):

        # r18+ を先に判定（r18 より厳しい条件を先にチェック）
        if "r18+, nsfw" in prompt:
            rating = "r18+"
        elif "r18, nsfw" in prompt:
            rating = "r18"
        elif "yuri, nsfw," in prompt:
            rating = "yuri"
        else:
            rating = "safe"

        if rating == 'safe':
            output_folder = root_folder
        else:
            # NSFWはサブフォルダへ
            output_folder = os.path.join(root_folder, rating)
            os.makedirs(output_folder, exist_ok=True)

        logger.info(f"Character: {char_prompt['name']} | Rating: {rating} | Start generating...")

        payload = set_payload(prompt, seed=seed, batch_count=batch_count)        
        img_list = generate_img(char_prompt, payload, output_folder, rating=rating)

        # slackへの送信処理
        message = f"\n Mode : {mode}\ncharacter : {char_prompt['name']} ({current_char_idx}/{total_char_count})\nTitle : {char_prompt['title']}\nBatch cnt : {batch_count}\nRating : {rating}"
        if mode == 'scenario':
            message += f"\n Seq : {i+1}/{len(prompts_to_generate)}"

        # slackに送信
        slack.send_slack_img(random.choice(img_list) , message)

        # immich メタ情報追加
        try:
            imm.update_exif_info_to_postgres(output_folder)
        except Exception as e:
            logger.error(f"Immich update failed: {e}")

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
        
        # ウォーターマーク押す
        if rating == 'safe':
            stamp2.add_stamp(output_folder, RELEASE_FOLDER, STAMP_IMG)

    logger.info("--- All images generated! ---")


#############################################################################################################
def create_seq_prompts():
    seq_data = load_seq_data()
    if not seq_data or 'seq' not in seq_data or SCENARIO_NAME not in seq_data['seq']:
        logger.error(f"Scenario '{SCENARIO_NAME}' not found in {SEQ_FILE}.")
        return []

    gen_seq_list = [item + POSITIVE + STYLE + ", r18+, nsfw," for item in seq_data['seq'][SCENARIO_NAME]]
    # 19桁の範囲を指定（10^18 ～ 10^19 - 1）
    seed = random.randint(10**18, 10**19 - 1)
    logger.info(f"Seed: {seed}")

    return gen_seq_list, seed

#############################################################################################################
def create_prompt_from_keyword():
    # キーワード検索
    keyword_prompt = []
    try:
        if isinstance(KEYWORD, str):
            keyword_prompt = [item + POSITIVE + STYLE + ", r18+, nsfw," for item in search_yaml.search_yaml_in_folder('.', KEYWORD)]
            logger.info(f"Keyword search results: {len(keyword_prompt)} items")
    except Exception as e:
        logger.error(f"Keyword search failed: {e}")

    return keyword_prompt

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

    logger.info(f"Batch count >>> {b_cnt}")
    logger.info(f"Character number >>> {c_num} ")
    logger.info(f"Mode >>> {mode}")

    # キャラリスト初期化
    selected_list = character.generate_list(mode, c_num)

    # プロンプト設定
    if mode == 'keyword search':
        gen_keyword_list = create_prompt_from_keyword()
    elif mode == 'scenario':
        try:
            if isinstance(SCENARIO_NAME, str):
                # シナリオ指定
                gen_seq_list, seed = create_seq_prompts()
        except Exception as e:
            logger.error(f"Scenario prompt creation failed: {e}")

    total_chars = len(selected_list)
    for idx, char_prompt in enumerate(selected_list):
        current_idx = idx + 1
        if mode == 'keyword search':
            # キーワード指定
            main(char_prompt, mode, gen_list=gen_keyword_list, batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)
        elif mode == 'scenario':
            # シナリオ指定
            main(char_prompt, mode, gen_list=gen_seq_list, seed=seed, batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)
        elif mode == 'yuri':
            # 百合モード
            main(char_prompt, mode, gen_list=[YURI], batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)
        else:
            main(char_prompt, mode, batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)

    # immich ライブラリをスキャン
    try:
        imm.scan_library(imm.LIBRARY_ID)
    except Exception as e:
        logger.error(f"Immich library scan failed: {e}")
# ======================