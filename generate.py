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
import exif_util as exif
import character as char_gen
from PIL import Image, PngImagePlugin
import argparse
from InquirerPy import inquirer
import logging
from tqdm import tqdm
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import censor
from enum import Enum
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # ここで1回だけ読み込む（CWD依存を排除）

import nas_env   # dotenv 読込後に import
import notion
import slack
import stamp2
import immich as imm

CONFIG_PATH = BASE_DIR / "config.yaml"                      # 設定を読み込むYAMLファイル名
SEQUENCE_PATH = BASE_DIR / "sequence.yaml"                  # プロンプトを読み込むYAMLファイル名
STAMP_IMG_PATH = BASE_DIR / "assets" / "Mabo.AiArt2.png"    # ウォータマークスタンプ

def resolve_from_base(p: str | Path) -> Path:
    pp = Path(p)
    return (BASE_DIR / pp).resolve() if not pp.is_absolute() else pp

# mode 列挙型
class RunMode(str, Enum):
    RANDOM = "random"
    KEYWORD = "keyword"
    SCENARIO = "scenario"
    PICKUP = "pickup"
    YURI = "yuri"

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ======================
# 設定

try:
    with CONFIG_PATH.open('r', encoding='utf-8') as f:
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
retry = Retry(
    total=API_RETRIES,
    connect=API_RETRIES,
    read=0,  # read timeout は自動リトライしない
    backoff_factor=API_BACKOFF,
    allowed_methods=frozenset(["GET", "HEAD", "OPTIONS"]),
    status_forcelist=[502, 503, 504],
    raise_on_status=False,
)
adapter = HTTPAdapter(max_retries=retry)
api_session.mount('http://', adapter)
api_session.mount('https://', adapter)


POSITIVE = config_data.get('prompt', {}).get('positive', "__il/quality/positive__,")
STYLE = config_data.get('prompt', {}).get('style', "<lora:RealisticAnimeIXL:0.5>")
NEGATIVE_DEFAULT = config_data.get('prompt', {}).get('negative', "__il/quality/negative__")

# 保存先定義
img_dirs = nas_env.get_img_dirs()
RELEASE_FOLDER = img_dirs['release']
DESTINATION_FOLDER = img_dirs['workspace']   

# 生成リスト（あとでキャラプロンプトと結合する）
GEN_LIST_RAW = config_data.get('generation', {}).get('lists', [])
GEN_LIST = [item + POSITIVE + STYLE for item in GEN_LIST_RAW]
YURI_RAW = config_data.get('generation', {}).get('yuri', "")
YURI = YURI_RAW + POSITIVE + STYLE if YURI_RAW else ""

# キャラクターピックアップリスト
PICKUP = config_data.get('generation', {}).get('pickup', [])

#############################################################################################################

### シナリオ名
SCENARIO_NAME = config_data.get('generation', {}).get('scenario_name', '')

### キーワード
KEYWORD = config_data.get('generation', {}).get('keyword', '')

#############################################################################################################
def load_seq_data():
    # 連番管理用YAMLファイルからデータを読み込む
    try:
        with SEQUENCE_PATH.open('r', encoding='utf-8') as f:
            seq_data = yaml.safe_load(f)
            if not isinstance(seq_data, dict):
                logger.error(f"Invalid format in {SEQUENCE_PATH}. Expected a dictionary.")
                return {}
            return seq_data
    except FileNotFoundError:
        logger.error(f"Sequence YAML file not found: {SEQUENCE_PATH}")
        return {}
    except yaml.YAMLError as e:
        logger.error(f"Could not parse sequence YAML file: {e}")
        return {}

#############################################################################################################
def post_with_one_retry(payload, timeout):
    try:
        return api_session.post(url=url, json=payload, timeout=timeout)
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
        logger.error(f"POST transient error: {e} -> retry once")
        time.sleep(1.0)
        return api_session.post(url=url, json=payload, timeout=timeout)

#############################################################################################################
def generate_img(char_prompt, payload, output_folder, rating='safe'):
    img_list = []

    try:
        connect_to = config_data.get("api", {}).get("connect_timeout", 10)
        read_to = config_data.get("api", {}).get("read_timeout", 3600)
        response = post_with_one_retry(payload, timeout=(connect_to, read_to))
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return []

    try:
        r = response.json()
    except ValueError:
        logger.error(f"API response is not JSON. status={response.status_code}, text_head={response.text[:200]}")
        return []

    images = r.get("images")
    if not isinstance(images, list) or len(images) == 0:
        logger.error(f"API response has no images. keys={list(r.keys())}")
        return []

    for idx, img_data in enumerate(images):
        try:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            filename = f"{char_prompt['name']}_{timestamp}_{idx+1}.png"
            output_path = os.path.join(output_folder, filename)

            img_bytes = base64.b64decode(img_data)
            img = Image.open(io.BytesIO(img_bytes))

            info = img.info.copy()
            parameters = info.get("parameters", "")

            png_info = PngImagePlugin.PngInfo()
            png_info.add_text("parameters", parameters)
            png_info.add_text(
                "ImageDescription",
                f"Title : {char_prompt['title']}\nCharacter : {char_prompt['name']}\nRating : {rating}"
            )

            img.save(output_path, pnginfo=png_info)
            img_list.append(output_path)
            logger.info(f"Image saved to: {output_path}")

        except Exception as e:
            logger.error(f"Image decode/save failed (idx={idx}): {e}")
            continue

    if len(img_list) == 0:
        logger.error("All images failed to decode/save.")
        return []

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
def detect_rating(prompt: str) -> str:
    # 例: "tag1, tag2, tag3" → {"tag1","tag2","tag3"}
    tags = {t.strip().lower() for t in prompt.split(",") if t.strip()}

    # 優先度: r18+ > r18 > yuri > safe
    if {"r18+", "nsfw"} <= tags:
        return "r18+"
    if {"r18", "nsfw"} <= tags:
        return "r18"
    if {"yuri", "nsfw"} <= tags:
        return "yuri"
    return "safe"

#############################################################################################################
def notify_error_slack(text: str):
    # 通知が失敗しても本体の例外処理を壊さない（例外は飲む）
    try:
        slack.send_slack_message(text)
    except Exception as e:
        logger.error(f"Slack notify failed: {e}")

#############################################################################################################
def run_step(name, func, *, critical=False, notify=True, context=""):
    try:
        return func()
    except Exception as e:
        logger.error(f"{name} failed: {e}")

        if notify:
            notify_error_slack(
                f"[ERROR] {name} failed\n"
                f"{context}\n"
                f"Exception: {e}"
            )

        if critical:
            raise
        return None
#############################################################################################################
def build_context(*, mode, char_prompt, current_char_idx, total_char_count, batch_count, rating, output_folder, scenario_idx=None, scenario_total=None):
    message = (
        f"\n Mode : {mode}\ncharacter : {char_prompt['name']} ({current_char_idx}/{total_char_count})\n"
        f"Title : {char_prompt['title']}\nBatch cnt : {batch_count}\nRating : {rating}"
    )
    if scenario_idx is not None and scenario_total is not None:
        message += f"\n Seq : {scenario_idx}/{scenario_total}"

    context = (
        f"Mode: {mode}\n"
        f"Character: {char_prompt['name']} ({current_char_idx}/{total_char_count})\n"
        f"Title: {char_prompt['title']}\n"
        f"Rating: {rating}\n"
        f"Output: {output_folder}"
    )
    return message, context

#############################################################################################################
def generate_images(*, char_prompt, payload, output_folder, rating):
    img_list = generate_img(char_prompt, payload, output_folder, rating=rating)
    if not img_list:
        raise RuntimeError("No images generated")
    return img_list

#############################################################################################################
def postprocess_images(*, output_folder, img_list, rating, config_data, logger, context):
    # NSFW: censor（img_list -> censored img_list）
    if rating != "safe":
        def do_censor():
            return censor.censor_files(
                img_list,
                mosaic_strength=config_data.get("censor", {}).get("mosaic_strength", 25),
                logger=logger,
                rules=censor.CENSOR_RULES,
            )
        censored = run_step("censor", do_censor, critical=False, notify=True, context=context)
        if censored is not None:
            img_list = censored

    # stamp（safeのみ）
    if rating == "safe":
        def do_stamp():
            return stamp2.add_stamp(output_folder, RELEASE_FOLDER, STAMP_IMG_PATH)
        run_step(
            "stamp",
            lambda: stamp2.add_stamp(output_folder, RELEASE_FOLDER, STAMP_IMG_PATH),
            critical=False,
            notify=True,
            context=context,
        )

    return img_list
#############################################################################################################
def sync_external(*, img_list, message, context, output_folder, mode, char_prompt, batch_count, rating):
    # Slack画像送信：失敗したらテキスト送信をチャレンジ（画像側の問題の可能性に備える）
    def send_slack_img_with_fallback():
        try:
            slack.send_slack_img(random.choice(img_list), message)
        except Exception as e:
            logger.error(f"Slack image upload failed: {e}")
            notify_error_slack(
                f"[WARN] Slack image upload failed; sent text only.\n{context}\nException: {e}"
            )

    # run_step側の notify を使うと二重通知になりやすいので、Slack送信は notify=False で運用
    run_step("slack_send_img", send_slack_img_with_fallback, critical=False, notify=False, context=context)

    # Immich
    run_step(
        "immich_update",
        lambda: imm.update_exif_info_to_postgres(output_folder),
        critical=False,
        notify=True,
        context=context,
    )

    # Notion
    run_step(
        "notion_add_record",
        lambda: notion.add_record(
            char_name=char_prompt["name"],
            date=datetime.now().date().isoformat(),
            title=char_prompt["title"],
            url=output_folder,
            batch_cnt=batch_count,
            mode_list=[mode],
            rating_list=[rating],
        ),
        critical=False,
        notify=True,
        context=context,
    )
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

        # rating判定
        rating = detect_rating(prompt)

        if rating == 'safe':
            output_folder = root_folder
        else:
            # NSFWはサブフォルダへ
            output_folder = os.path.join(root_folder, rating)
            os.makedirs(output_folder, exist_ok=True)

        logger.info(f"Character: {char_prompt['name']} | Rating: {rating} | Start generating...")

        payload = set_payload(prompt, seed=seed, batch_count=batch_count)        

        # img_list が生成できた（空でない）前提で、外部連携を run_step で統一する例
        # ※ message / context は Slack 通知やログに流用できるので最初に作る
        message, context = build_context(
            mode=mode,
            char_prompt=char_prompt,
            current_char_idx=current_char_idx,
            total_char_count=total_char_count,
            batch_count=batch_count,
            rating=rating,
            output_folder=output_folder,
            scenario_idx=i + 1 if mode == "scenario" else None,
            scenario_total=len(prompts_to_generate) if mode == "scenario" else None,
        )

        img_list = run_step(
            "generate",
            lambda: generate_images(char_prompt=char_prompt, payload=payload, output_folder=output_folder, rating=rating),
            critical=False,
            notify=True,
            context=context,
        )

        # 生成失敗（画像0枚）なら、Slackはテキストだけ送って次へ
        if not img_list:
            logger.error("No images generated. Skip Slack image upload.")
            try:
                slack.send_slack_message(
                    f"[ERROR] Image generation failed\n"
                    f"Mode: {mode}\nCharacter: {char_prompt['name']} ({current_char_idx}/{total_char_count})\n"
                    f"Title: {char_prompt['title']}\nRating: {rating}\n"
                    f"Output: {output_folder}"
                )
            except Exception as e:
                logger.error(f"Slack error notification failed: {e}")
            continue

        # Postprocess (censor/stamp)
        img_list = postprocess_images(
            output_folder=output_folder,
            img_list=img_list,
            rating=rating,
            config_data=config_data,
            logger=logger,
            context=context
        )

        # 外部連携（Immich/Notion/Slackなど）
        if run_mode is RunMode.SCENARIO and i <= len(prompts_to_generate) -2:
            logger.info("Skip external sync")
        else:
            sync_external(
                img_list=img_list,
                message=message,
                context=context,
                output_folder=output_folder,
                mode=mode,
                char_prompt=char_prompt,
                batch_count=batch_count if run_mode != RunMode.SCENARIO else len(prompts_to_generate), 
                rating=rating
            )

    logger.info("--- All images generated! ---")


#############################################################################################################
def create_seq_prompts():
    seq_data = load_seq_data()
    if not seq_data or 'seq' not in seq_data or SCENARIO_NAME not in seq_data['seq']:
        logger.error(f"Scenario '{SCENARIO_NAME}' not found in {SEQUENCE_PATH}.")
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
            choices = [m.value for m in RunMode],
        ).execute()

    b_cnt = int(args.count)
    c_num = args.char_num
    # 文字列からEnumに変換
    run_mode = RunMode(args.mode) 

    logger.info(f"Batch count >>> {b_cnt}")
    logger.info(f"Character number >>> {c_num} ")
    logger.info(f"Mode >>> {run_mode}")

    # キャラリスト初期化
    selected_list = char_gen.generate_list(run_mode, c_num, PICKUP)

    # プロンプト設定
    if run_mode is RunMode.KEYWORD:
        gen_keyword_list = create_prompt_from_keyword()
    elif run_mode is RunMode.SCENARIO:
        try:
            if isinstance(SCENARIO_NAME, str):
                # シナリオ指定
                gen_seq_list, seed = create_seq_prompts()
        except Exception as e:
            logger.error(f"Scenario prompt creation failed: {e}")

    total_chars = len(selected_list)
    for idx, char_prompt in enumerate(selected_list):
        current_idx = idx + 1
        if run_mode is RunMode.KEYWORD:
            # キーワード指定
            main(char_prompt, run_mode, gen_list=gen_keyword_list, batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)
        elif run_mode is RunMode.SCENARIO:
            # シナリオ指定
            main(char_prompt, run_mode, gen_list=gen_seq_list, seed=seed, batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)
        elif run_mode is RunMode.YURI:
            # 百合モード
            main(char_prompt, run_mode, gen_list=[YURI], batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)
        else:
            main(char_prompt, run_mode, batch_count=b_cnt, current_char_idx=current_idx, total_char_count=total_chars)

    # immich ライブラリをスキャン
    try:
        imm.scan_library(imm.LIBRARY_ID)
    except Exception as e:
        logger.error(f"Immich library scan failed: {e}")
# ======================