import sys
import re
import requests
import os
import glob
import logging
import traceback
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from pathlib import Path

from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")  # ここで1回だけ読み込む（CWD依存を排除）

import nas_env as nas

##################################################################
# ── 定数 ──
##################################################################

NOTION_DB_ID = nas.get_notion_params()["notion_database_id"]  # .env から OS 別に解決済み
NOTION_TOKEN = nas.get_notion_params()["notion_token"]  # .env から OS 別に解決済み
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}
ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "storage_state.json"
LOG_DIR = ROOT / "logs"
SCREENSHOT_DIR = ROOT / "screenshots"

# 画像フォルダのベースパス（nas_env が .env から OS 別に解決済み）
WORKSPACE_DIR = nas.get_img_dirs()['workspace']

def convert_folder_path(folder_url: str) -> str:
    """Notion DB のフォルダパスを実行環境のパスに変換する
    Notion DB には Windows パス（Z:\...\workspace\<キャラ名>\...）が格納されている。
    nas_env.img_dirs['workspace'] が OS 別の workspace ベースパスを提供するので、
    相対パス部分だけ抽出して結合する。
    """
    # バックスラッシュ → スラッシュに統一
    path = folder_url.replace("\\", "/")

    # "workspace/" 以降の相対パスを抽出
    marker = "workspace/"
    idx = path.lower().find(marker)
    if idx >= 0:
        relative = path[idx + len(marker):]
        return os.path.join(WORKSPACE_DIR, relative)

    # フォールバック: そのまま返す（すでにローカルパスの場合など）
    return os.path.normpath(folder_url)

##################################################################
# ── ロギング設定 ──
##################################################################
def setup_logging(mode: str):
    """ファイル＋コンソールの両方にログを出力する"""
    LOG_DIR.mkdir(exist_ok=True)
    log_file = LOG_DIR / f"schedule_post_{mode}.log"

    # ルートロガーをリセット
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ファイルハンドラ（追記、UTF-8）
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # コンソールハンドラ
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    return logging.getLogger("schedule_post")


def save_error_artifacts(page, mode: str, error: Exception):
    """失敗時にスクリーンショットとHTMLを保存する"""
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # スクリーンショット
    ss_path = SCREENSHOT_DIR / f"{mode}_{ts}.png"
    try:
        page.screenshot(path=str(ss_path), full_page=True)
        logging.getLogger("schedule_post").info(f"スクリーンショット保存: {ss_path}")
    except Exception as e:
        logging.getLogger("schedule_post").warning(f"スクリーンショット保存失敗: {e}")

    # HTML保存
    html_path = LOG_DIR / f"{mode}_{ts}.html"
    try:
        html_content = page.content()
        html_path.write_text(html_content, encoding="utf-8")
        logging.getLogger("schedule_post").info(f"HTML保存: {html_path}")
    except Exception as e:
        logging.getLogger("schedule_post").warning(f"HTML保存失敗: {e}")

##################################################################
# ── スケジューリング（統合版） ──
##################################################################
log = logging.getLogger("schedule_post")

def get_next_schedule(mode: str):
    """
    次回公開日と未投稿行を自動決定する。
    mode: "safe" or "nsfw"
    Returns: dict with keys:
        page_id, publish_date, publish_time, folder_url, character, rating
        or None（未投稿行がない場合）
    """
    if mode == "safe":
        return _get_next_safe()
    else:
        return _get_next_nsfw()


def _get_next_safe():
    # published 済みの safe 行 → 最大日付を取得
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=HEADERS,
        json={
            "filter": {
                "and": [
                    {"property": "rating", "multi_select": {"contains": "safe"}},
                    {"property": "published", "date": {"is_not_empty": True}},
                ]
            },
            "sorts": [{"property": "published", "direction": "descending"}],
            "page_size": 1,
        },
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    if results:
        last_date_str = results[0]["properties"]["published"]["date"]["start"]
        last_date = datetime.strptime(last_date_str[:10], "%Y-%m-%d").date()
        next_date = last_date + timedelta(days=1)
    else:
        next_date = datetime.now().date() + timedelta(days=1)

    # 未投稿の safe 行を1件取得
    row = _get_unpublished_row("safe")
    if row is None:
        return None

    row["publish_date"] = next_date.strftime("%Y-%m-%d")
    row["publish_time"] = "12:00"
    row["rating"] = "safe"
    return row


def _get_next_nsfw():
    # published 済みの NSFW 行 → 直近のNSFWを基準に「翌日07:00」を予約する（1日1投稿）
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=HEADERS,
        json={
            "filter": {
                "and": [
                    {
                        "or": [
                            {"property": "rating", "multi_select": {"contains": "r18"}},
                            {"property": "rating", "multi_select": {"contains": "r18+"}},
                        ]
                    },
                    {"property": "published", "date": {"is_not_empty": True}},
                ]
            },
            "sorts": [{"property": "published", "direction": "descending"}],
            "page_size": 1,  # 直近NSFWだけ見ればよい
        },
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])

    if results:
        last_date_str = results[0]["properties"]["published"]["date"]["start"]
        last_date = datetime.strptime(last_date_str[:10], "%Y-%m-%d").date()

        # 次回は必ず翌日 + 07:00 固定
        next_date = last_date + timedelta(days=1)
        next_time = "07:00"

        # rating は必ず交互
        last_ratings = [
            opt["name"]
            for opt in results[0]["properties"]["rating"]["multi_select"]
        ]
        next_rating = "r18" if "r18+" in last_ratings else "r18+"
    else:
        # 初回（NSFWの published がまだ無い場合）
        next_date = datetime.now().date() + timedelta(days=1)
        next_time = "09:00"
        next_rating = "r18"  # 初回は r18 から（必要なら変更）

    # 決定した rating の未投稿行を取得
    row = _get_unpublished_row(next_rating)
    if row is None:
        return None

    row["publish_date"] = next_date.strftime("%Y-%m-%d")
    row["publish_time"] = next_time
    row["rating"] = next_rating
    return row

def _get_unpublished_row(rating: str):
    """指定 rating の未投稿行を1件取得して dict で返す"""
    resp = requests.post(
        f"https://api.notion.com/v1/databases/{NOTION_DB_ID}/query",
        headers=HEADERS,
        json={
            "filter": {
                "and": [
                    {"property": "rating", "multi_select": {"contains": rating}},
                    {"property": "published", "date": {"is_empty": True}},
                ]
            },
            "sorts": [{"property": "日付", "direction": "ascending"}],
            "page_size": 1,
        },
    )
    resp.raise_for_status()
    unpublished = resp.json().get("results", [])

    if not unpublished:
        log.warning(f"未投稿の {rating} 行がありません")
        return None

    page = unpublished[0]
    page_id = page["id"]
    folder_url = page["properties"]["URL"]["url"]
    title_items = page["properties"]["character"]["title"]
    character = "".join([t["plain_text"] for t in title_items]) if title_items else "unknown"

    log.info(f"page_id={page_id}, character={character}, folder={folder_url}")
    return {
        "page_id": page_id,
        "folder_url": folder_url,
        "character": character,
    }

##################################################################
# ── 画像関連 ──
##################################################################
def get_image_files(folder_path, max_count=64):
    extensions = ("*.png", "*.jpg", "*.jpeg", "*.webp")
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(folder_path, ext)))
    files.sort(key=os.path.getmtime, reverse=True)
    selected = files[:max_count]
    log.info(f"画像 {len(selected)}/{len(files)} 枚を選択（フォルダ: {folder_path}）")
    return selected


def upload_images(page, folder_path):
    image_files = get_image_files(folder_path)
    if not image_files:
        raise RuntimeError(f"画像が見つかりません: {folder_path}")

    file_input = page.locator(
        'input[type="file"][accept="image/jpeg,image/png,image/gif,image/webp,image/avif,image/tiff"]'
    ).first
    file_input.set_input_files(image_files)
    file_input.evaluate("""el => {
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('input', {bubbles: true}));
    }""")

    log.info(f"{len(image_files)} 枚アップロード開始...")
    for attempt in range(120):
        page.wait_for_timeout(5000)
        thumbnails = page.locator('[data-tag="post-image"], img[src*="patreon"]').all()
        if len(thumbnails) >= len(image_files):
            break
        log.info(f"アップロード待ち: {len(thumbnails)}/{len(image_files)} 枚...")
    log.info("画像アップロード完了")

##################################################################
# ── Patreon UI 操作（共通） ──
##################################################################
def navigate_to_new_post(page):
    page.goto("https://www.patreon.com/posts/new", wait_until="domcontentloaded", timeout=60_000)
    log.info(f"現在のURL: {page.url}")
    # headless でログインページにリダイレクトされた場合の検出
    if "login" in page.url.lower():
        raise RuntimeError(f"ログインページにリダイレクトされました: {page.url} — storage_state.json の再取得が必要です")
    page.locator('div[contenteditable="true"]').first.wait_for(state="visible", timeout=30_000)
    log.info("New Post 画面に遷移しました")


def open_settings_panel(page):
    if page.locator("input[type='radio'][value='public']").count() > 0:
        return
    btn = page.get_by_role("button", name="設定")
    btn.first.wait_for(state="visible", timeout=30_000)
    btn.first.click()
    page.locator("input[type='radio'][value='public']").first.wait_for(timeout=30_000)


def configure_audience(page, rating: str):
    """rating に応じて公開範囲を切替"""
    public_input = page.locator("input[type='radio'][value='public']").first
    paid_input = page.locator("input[type='radio'][value='paid']").first
    public_input.wait_for(state="attached", timeout=30_000)
    paid_input.wait_for(state="attached", timeout=30_000)

    if rating == "safe":
        # safe → 無料でアクセス
        radio = page.get_by_role("radio", name="無料でアクセス")
        if radio.count() > 0:
            radio.first.scroll_into_view_if_needed()
            radio.first.click(force=True)
        else:
            public_input.click(force=True)
        log.info("audience: 無料でアクセス (public)")
    else:
        # r18 / r18+ → 有料会員のみ
        radio = page.get_by_role("radio", name="有料会員のみ")
        if radio.count() > 0:
            radio.first.scroll_into_view_if_needed()
            radio.first.click(force=True)
        else:
            paid_input.click(force=True)
        log.info(f"audience: 有料会員のみ (paid) — rating={rating}")


def configure_free_options_members(page):
    page.locator("text=その他のオプション").first.click()
    page.locator("text=無料会員と有料会員").first.click()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def configure_paid_tier(page, rating: str):
    """有料会員のランクを設定
    デフォルト: 有料会員チェック時に全ランク(Basic+Premium)がON
    R18 = 全ランクそのまま（操作不要）
    R18+ = Basicを外してPremiumのみにする
    """
    if rating == "r18":
        # R18 → 全ランク（デフォルトのままでOK、ドロップダウン触らない）
        log.info("paid tier: 全ランク Basic+Premium（デフォルト維持）")
        return

    # R18+ のみドロップダウンを開いて Basic を外す
    tier_btn = page.locator("div[class*='contentContainer']:has(div[class*='labelContainer'])").filter(has_text="ランク")
    if tier_btn.count() == 0:
        tier_btn = page.locator("div[class*='labelContainer']").filter(has_text="ランク")
    if tier_btn.count() == 0:
        tier_btn = page.get_by_text(re.compile(r'\d+件のランク'))
    tier_btn.first.wait_for(state="visible", timeout=10_000)
    tier_btn.first.scroll_into_view_if_needed()
    tier_btn.first.click(force=True)
    page.wait_for_timeout(1000)

    # Basic をクリックしてチェックを外す
    basic_item = page.get_by_text("Basic", exact=False).first
    if basic_item.count() > 0:
        basic_item.click()
        page.wait_for_timeout(500)
    log.info("paid tier: Basic を外して Premium のみに設定")

    # ドロップダウンを閉じる（エディタエリアをクリック）
    page.locator('div[contenteditable="true"]').first.click()
    page.wait_for_timeout(500)
    log.info("ランク設定完了")


def configure_sell_post(page, rating: str):
    """投稿を販売する設定（R18=$3, R18+=$5）"""
    price = "3" if rating == "r18" else "5"

    # 「この投稿を販売する」のラベルを探す
    sell_label = page.locator("text=この投稿を販売する").first
    sell_label.scroll_into_view_if_needed()

    # チェックボックス/スイッチを探す（ラベルの親要素内）
    sell_section = sell_label.locator("..")
    sell_toggle = sell_section.locator("input[type='checkbox'], [role='switch'], [role='checkbox']")
    if sell_toggle.count() > 0:
        if not sell_toggle.first.is_checked():
            sell_toggle.first.click(force=True)
    else:
        # ラベル自体をクリック（トグル連動の場合）
        sell_label.click()
    page.wait_for_timeout(1000)

    # 金額入力 — $ マークの近くの visible な input を探す
    # type='number' / inputmode='numeric' / inputmode='decimal' など
    price_input = page.locator("input:visible").filter(
        has_not=page.locator("[type='file'], [type='radio'], [type='checkbox'], [type='hidden'], [type='date'], [type='time']")
    )
    # 候補を絞り込む: 金額っぽい小さい入力欄
    found = False
    for i in range(price_input.count()):
        el = price_input.nth(i)
        tag = el.get_attribute("type") or ""
        mode = el.get_attribute("inputmode") or ""
        placeholder = el.get_attribute("placeholder") or ""
        if tag in ("number", "text", "") or mode in ("numeric", "decimal") or "$" in placeholder or "金額" in placeholder:
            el.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(price)
            found = True
            log.info(f"sell post: ${price} — rating={rating} (input #{i})")
            break

    if not found:
        # 最終フォールバック: $ テキストの隣の input
        dollar = page.locator("text=$").first
        if dollar.count() > 0:
            dollar.locator("..").locator("input").first.click()
            page.keyboard.press("Control+A")
            page.keyboard.type(price)
            log.info(f"sell post: ${price} — rating={rating} (fallback)")
        else:
            log.warning("金額入力欄が見つかりません")


def add_tags(page, character: str, rating: str):
    """タグを追加する（キャラ名 + NSFW時はrating）"""
    tags = [character]
    if rating in ("r18", "r18+"):
        tags.append(rating.upper())

    tag_input = page.locator("text=タグを追加する").locator("..").locator("input")
    if tag_input.count() == 0:
        # フォールバック: placeholder で探す
        tag_input = page.locator("input[placeholder*='入力']").last

    for tag in tags:
        tag_input.click()
        page.keyboard.type(tag)
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        log.info(f"tag added: {tag}")

    log.info(f"tags: {tags}")


def ensure_paid_member_checked(page):
    """有料会員チェックボックスを確実にONにする（ランク操作で外れる対策）"""
    # 設定パネルを再度開く（エディタクリックで閉じた可能性があるため）
    open_settings_panel(page)
    page.wait_for_timeout(500)

    # JavaScriptで「有料会員」テキストの横のチェックボックスを直接操作
    result = page.evaluate("""
        () => {
            // 「有料会員」テキストを含む要素を探す
            const allText = document.querySelectorAll('*');
            for (const el of allText) {
                if (el.children.length === 0 && el.textContent.trim() === '有料会員') {
                    // 親要素をたどってチェックボックスを探す
                    let parent = el.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        const cb = parent.querySelector('input[type="checkbox"], [role="checkbox"], [role="switch"]');
                        if (cb) {
                            const isChecked = cb.checked || cb.getAttribute('aria-checked') === 'true';
                            return { found: true, checked: isChecked, tagName: cb.tagName };
                        }
                        parent = parent.parentElement;
                    }
                }
            }
            return { found: false };
        }
    """)
    log.debug(f"有料会員CB状態: {result}")

    if result.get("found") and not result.get("checked"):
        # チェックが外れているのでクリックする
        # 「有料会員」テキストをクリック（ラベルとチェックボックスが連動）
        page.get_by_text("有料会員", exact=True).first.click()
        page.wait_for_timeout(500)
        log.warning("有料会員チェックボックスをONにしました（外れていた）")
    elif result.get("found") and result.get("checked"):
        log.info("有料会員チェックボックス: 既にON")
    else:
        # チェックボックスが見つからない場合、無条件でクリック
        page.get_by_text("有料会員", exact=True).first.click()
        page.wait_for_timeout(500)
        log.warning("有料会員ラベルをクリック（CB未検出フォールバック）")


def enable_schedule_toggle(page):
    toggle = page.locator("text=公開日を設定する").locator("..").locator(
        "input[type='checkbox'], [role='switch']"
    )
    if not toggle.is_checked():
        toggle.click(force=True)
    log.info("Schedule toggle ON")


def set_schedule_datetime(page, publish_date, publish_time):
    date_input = page.locator('input#date[type="date"]').first
    date_input.wait_for(state="attached", timeout=30_000)
    time_input = page.locator('input[type="time"]').first   # time input は id がないため type 属性で探す
    time_input.wait_for(state="attached", timeout=30_000)

    for el, val in [(date_input, publish_date), (time_input, publish_time)]:
        el.evaluate(
            """(el, v) => {
                const nativeSetter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                ).set;
                nativeSetter.call(el, v);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }""",
            val,
        )

    log.info(f"date={date_input.input_value()}, time={time_input.input_value()}")

def fill_title(page, title_text):
    title = page.locator("textarea").first
    if title.count() == 0:
        title = page.locator("input").first
    title.click()
    page.keyboard.press("Control+A")
    page.keyboard.type(title_text)
    log.info(f"title: {title_text}")


def click_schedule_button(page):
    btns = page.locator("button[data-tag='make-a-post-action-schedule_post']:visible")
    if btns.count() == 0:
        btns = page.locator("button[data-tag='make-a-post-action-schedule_post']")
    btn = btns.first
    btn.scroll_into_view_if_needed()
    page.wait_for_timeout(200)
    try:
        btn.click(timeout=10_000)
    except Exception:
        btn.click(timeout=10_000, force=True)
    log.info("clicked schedule button")


def handle_paywall_dialog_if_any(page):
    dialog = page.get_by_role("dialog")
    try:
        dialog.wait_for(timeout=3000)
    except Exception:
        return
    btn = page.locator("button", has_text="一般公開する")
    if btn.count() > 0:
        btn.first.click()
        log.info("paywall dialog: 一般公開する")


def handle_scheduled_success_dialog(page):
    try:
        page.locator("text=準備ができました").first.wait_for(timeout=10_000)
    except Exception:
        return
    ok = page.locator("button", has_text="OK")
    if ok.count() > 0:
        ok.first.click()
        log.info("success dialog: OK")
        return
    close = page.locator("button[aria-label='閉じる']")
    if close.count() > 0:
        close.first.click()
        log.info("success dialog: x")
        return
    page.keyboard.press("Escape")
    log.info("success dialog: Escape")


def update_notion_published(page_id: str, publish_date: str):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "published": {"date": {"start": publish_date}}
        }
    }
    resp = requests.patch(url, headers=HEADERS, json=payload)
    log.debug(f"Notion API status={resp.status_code}, body={resp.text}")
    resp.raise_for_status()
    log.info(f"Notion updated: page={page_id}, published={publish_date}")

##################################################################
# ── メイン ──
##################################################################
def main():
    # コマンドライン引数で mode を決定
    if len(sys.argv) < 2 or sys.argv[1] not in ("safe", "nsfw"):
        print("Usage: python schedule_post.py <safe|nsfw>")  # logging未初期化
        sys.exit(1)

    mode = sys.argv[1]
    log = setup_logging(mode)
    log.info(f"===== START mode={mode} =====")

    # ── 1. Notion から次回投稿データを自動取得 ──
    try:
        schedule = get_next_schedule(mode)
    except Exception as e:
        log.error(f"スケジュール取得失敗: {e}")
        log.debug(traceback.format_exc())
        sys.exit(1)

    if schedule is None:
        log.info("投稿対象なし。終了。")
        sys.exit(0)

    PAGE_ID = schedule["page_id"]
    PUBLISH_DATE = schedule["publish_date"]
    PUBLISH_TIME = schedule["publish_time"]
    FOLDER_URL = schedule["folder_url"]
    CHARACTER = schedule["character"].title()  # イニシャル大文字化
    RATING = schedule["rating"]
    if RATING == "safe":
        TITLE_TEXT = f"{CHARACTER} '{PUBLISH_DATE[2:].replace('-', '/')}"
    else:
        TITLE_TEXT = f"{CHARACTER} {RATING.upper()} '{PUBLISH_DATE[2:].replace('-', '/')}"

    log.info(f"rating={RATING}, date={PUBLISH_DATE}, time={PUBLISH_TIME}")
    log.info(f"title={TITLE_TEXT}")
    # フォルダパスを実行環境に合わせて変換
    FOLDER_URL = convert_folder_path(FOLDER_URL)
    log.info(f"folder={FOLDER_URL}")
    if not os.path.exists(FOLDER_URL):
        log.error(f"フォルダパスが存在しません: {FOLDER_URL}")
        sys.exit(1)

    page = None  # エラーハンドリング用
    try:
        with sync_playwright() as p:
            import platform
            is_headless = platform.system() != "Windows"
            browser = p.chromium.launch(headless=is_headless)
            context_opts = {
                "storage_state": str(STATE_PATH),
            }
            if is_headless:
                # headless 時はブラウザ検出を回避するため UA と viewport を明示
                context_opts["viewport"] = {"width": 1920, "height": 1080}
                context_opts["user_agent"] = (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                )
            context = browser.new_context(**context_opts)
            page = context.new_page()

            # 0) New Post画面に移動
            navigate_to_new_post(page)

            # 1) 設定パネルを開く
            open_settings_panel(page)

            # 2) 公開範囲を rating に応じて切替
            configure_audience(page, RATING)

            # 3) rating別の追加設定
            if RATING == "safe":
                configure_free_options_members(page)
            else:
                # NSFW: ランク設定 + 販売設定
                configure_paid_tier(page, RATING)
                configure_sell_post(page, RATING)

                # 有料会員チェックボックスを明示的にONにする
                # （ランク操作で外れることがあるため、最後にもう一度クリック）
                ensure_paid_member_checked(page)

            # 4) 公開日トグルON
            enable_schedule_toggle(page)

            # 5) 日時セット
            set_schedule_datetime(page, PUBLISH_DATE, PUBLISH_TIME)

            # 6) タイトル
            fill_title(page, TITLE_TEXT)
            page.wait_for_timeout(500)

            # 7) タグ追加
            add_tags(page, CHARACTER, RATING)
            page.wait_for_timeout(500)

            # 8) 画像アップロード
            upload_images(page, FOLDER_URL)

            # 9) スケジュール確定
            click_schedule_button(page)

            # 10) ダイアログ処理
            handle_paywall_dialog_if_any(page)
            handle_scheduled_success_dialog(page)

            # 11) Notion 更新
            update_notion_published(page_id=PAGE_ID, publish_date=PUBLISH_DATE)

            log.info(f"===== 完了 {mode} 予約投稿 + Notion 更新 done! =====")

            context.close()
            browser.close()

    except Exception as e:
        log.error(f"投稿処理でエラー発生: {e}")
        log.debug(traceback.format_exc())
    
        # スクリーンショット＋HTML保存
        if page is not None:
            try:
                save_error_artifacts(page, mode, e)
            except Exception:
                log.warning("エラーアーティファクト保存に失敗")

        sys.exit(1)


if __name__ == "__main__":
    main()