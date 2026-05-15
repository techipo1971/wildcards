from nudenet import NudeDetector
import cv2
import logging
import shutil
from pathlib import Path

detector = NudeDetector()
nudel_weights = Path(r"C:\StabilityMatrix\Packages\Stable Diffusion WebUI\extensions\sd-dynamic-prompts\wildcards")
detector = NudeDetector(model_path=f"{nudel_weights}\\640m.onnx")

# ★ ここで全ての設定を管理
CENSOR_RULES = {
    "FEMALE_BREAST_EXPOSED":    {"enabled": False, "threshold": 0.5},  # ← モザイクしない
    "FEMALE_GENITALIA_EXPOSED": {"enabled": True,  "threshold": 0.3},
    "MALE_GENITALIA_EXPOSED":   {"enabled": True,  "threshold": 0.3},
    "BUTTOCKS_EXPOSED":         {"enabled": True,  "threshold": 0.6},
    "FACE_FEMALE":              {"enabled": False, "threshold": 0.5},
    "FACE_MALE":                {"enabled": False, "threshold": 0.5},
    "ANUS_EXPOSED":             {"enabled": True,  "threshold": 0.5},
}

SAFE_MODE_RULES = {
    "FEMALE_BREAST_EXPOSED":    {"enabled": True,  "threshold": 0.5},
    "FEMALE_GENITALIA_EXPOSED": {"enabled": True,  "threshold": 0.5},
    "MALE_GENITALIA_EXPOSED":   {"enabled": True,  "threshold": 0.5},
    "BUTTOCKS_EXPOSED":         {"enabled": False,  "threshold": 0.6}, #股間　お尻
    "FACE_FEMALE":              {"enabled": False, "threshold": 0.5},
    "FACE_MALE":                {"enabled": False, "threshold": 0.5},
    "ANUS_EXPOSED":             {"enabled": True,  "threshold": 0.5},
}

def setup_logger(log_path):
    """ログをファイルとコンソールの両方に出力するロガーを設定"""
    logger = logging.getLogger("censor")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # ファイル出力（追記モード）
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="a")
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # コンソール出力
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger

def apply_blur(image, x1, y1, x2, y2, strength=20):
    roi = image[y1:y2, x1:x2]
    # カーネルサイズは奇数である必要がある
    ksize = strength * 2 + 1
    blurred = cv2.GaussianBlur(roi, (ksize, ksize), 0)
    image[y1:y2, x1:x2] = blurred
    return image

def censor_image(input_path, output_path, mosaic_strength, logger, rules=CENSOR_RULES):
    logger.info(f"[開始] {input_path.name}")

    detections = detector.detect(str(input_path))
    image = cv2.imread(str(input_path))

    if image is None:
        logger.error(f"  ❌ 画像読み込み失敗: {input_path}")
        return False

    img_h, img_w = image.shape[:2]
    applied = 0

    for det in detections:
        class_name = det['class']
        score = det['score']

        if class_name not in rules:
            logger.info(f"  ⏭ ルール未定義のためスキップ: {class_name} (信頼度: {score:.2f})")
            continue

        rule = rules[class_name]

        if not rule["enabled"]:
            logger.info(f"  ⏭ 無効設定のためスキップ: {class_name} (信頼度: {score:.2f})")
            continue

        if score < rule["threshold"]:
            logger.info(f"  ⏭ 閾値未満のためスキップ: {class_name} (信頼度: {score:.2f})")
            continue

        box = det['box']
        x1 = max(0, int(box[0]))
        y1 = max(0, int(box[1]))
        x2 = min(img_w, int(box[0] + box[2]))
        y2 = min(img_h, int(box[1] + box[3]))

        if x2 - x1 <= 0 or y2 - y1 <= 0:
            logger.info(f"  ⏭ 座標が無効のためスキップ: {class_name}")
            continue

        image = apply_blur(image, x1, y1, x2, y2, mosaic_strength)
        logger.info(f"  ✅ ブラー適用: {class_name} (信頼度: {score:.2f})")
        applied += 1

    cv2.imwrite(str(output_path), image)

    if applied == 0:
        logger.info(f"  ℹ 検出なし（モザイク未適用）→ {output_path.name}")
    else:
        logger.info(f"  💾 保存完了 ({applied}件適用) → {output_path.name}")

    return applied

def batch_censor(input_folder, mosaic_strength=40, rules=CENSOR_RULES):
    input_dir = Path(input_folder)

    if not input_dir.exists():
        print(f"❌ フォルダが見つかりません: {input_folder}")
        return

    # 出力フォルダを作成（例: images → images_censored）
    output_dir = input_dir.parent / (input_dir.name + "_censored")
    output_dir.mkdir(exist_ok=True)

    # ロガー設定
    log_path = output_dir / "censored.log"
    logger = setup_logger(log_path)

    # 対象画像を収集
    extensions = {".png", ".jpg", ".jpeg"}
    images = sorted([f for f in input_dir.iterdir() if f.suffix.lower() in extensions])

    logger.info("=" * 60)
    logger.info(f"バッチ処理開始")
    logger.info(f"入力フォルダ : {input_dir}")
    logger.info(f"出力フォルダ : {output_dir}")
    logger.info(f"対象ファイル数: {len(images)}枚")
    logger.info(f"モザイク強度 : {mosaic_strength}")
    logger.info("=" * 60)

    if not images:
        logger.warning("対象画像が見つかりませんでした")
        return

    success = 0
    skipped = 0
    total_applied = 0

    for i, img_path in enumerate(images, 1):
        out_filename = f"{img_path.stem}_censored{img_path.suffix}"
        out_path = output_dir / out_filename

        logger.info(f"--- [{i}/{len(images)}] ---")
        result = censor_image(img_path, out_path, mosaic_strength, logger, rules=rules)

        if result is False:
            skipped += 1
        else:
            success += 1
            total_applied += result

    logger.info("=" * 60)
    logger.info(f"バッチ処理完了")
    logger.info(f"処理成功  : {success}枚")
    logger.info(f"スキップ  : {skipped}枚")
    logger.info(f"総適用件数: {total_applied}件")
    logger.info(f"ログ保存先: {log_path}")
    logger.info("=" * 60)


#############################################################################################################
def is_unsafe(image_path, rules=SAFE_MODE_RULES):
    """SAFE_MODE_RULES に基づき、画像がNSFWかどうかを判定する"""
    detections = detector.detect(str(image_path))
    for det in detections:
        class_name = det['class']
        score = det['score']
        if class_name not in rules:
            continue
        rule = rules[class_name]
        if rule["enabled"] and score >= rule["threshold"]:
            return True, class_name, score
    return False, None, None

#############################################################################################################
def filter_unsafe_images(input_folder, output_folder):
    """
    SAFE_MODE_RULES で検出された画像を output_folder に移動する。
    モザイク/ブラー処理は行わない。
    """
    input_dir = Path(input_folder)
    output_dir = Path(output_folder)

    if not input_dir.exists():
        print(f"❌ 入力フォルダが見つかりません: {input_folder}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # ロガー設定
    log_path = output_dir / "filter_unsafe.log"
    logger = setup_logger(log_path)

    # 対象画像を収集
    extensions = {".png", ".jpg", ".jpeg"}
    images = sorted([f for f in input_dir.iterdir() if f.suffix.lower() in extensions])

    logger.info("=" * 60)
    logger.info(f"NSFW フィルタリング開始")
    logger.info(f"入力フォルダ : {input_dir}")
    logger.info(f"移動先フォルダ: {output_dir}")
    logger.info(f"対象ファイル数: {len(images)}枚")
    logger.info("=" * 60)

    if not images:
        logger.warning("対象画像が見つかりませんでした")
        return

    moved = 0
    safe = 0

    for i, img_path in enumerate(images, 1):
        logger.info(f"--- [{i}/{len(images)}] {img_path.name} ---")
        unsafe, class_name, score = is_unsafe(img_path)

        if unsafe:
            dest = output_dir / img_path.name
            shutil.move(str(img_path), str(dest))
            logger.info(f"  🚫 NSFW検出 → 移動: {class_name} (信頼度: {score:.2f})")
            moved += 1
        else:
            logger.info(f"  ✅ セーフ（移動なし）")
            safe += 1

    logger.info("=" * 60)
    logger.info(f"フィルタリング完了")
    logger.info(f"移動済み: {moved}枚")
    logger.info(f"セーフ  : {safe}枚")
    logger.info(f"ログ保存先: {log_path}")
    logger.info("=" * 60)

#############################################################################################################
if __name__ == '__main__':

    # ★ 処理したいフォルダのパスを指定
    batch_censor(
        input_folder=r"Z:\StabilityMatrix\Images\censor\imgs",  # ← ここを変更
        mosaic_strength=40,
        rules=SAFE_MODE_RULES
    )
