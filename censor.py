from nudenet import NudeDetector
import cv2
import logging
from pathlib import Path

detector = NudeDetector()

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

def apply_mosaic(image, x1, y1, x2, y2, strength=20):
    roi = image[y1:y2, x1:x2]
    h, w = roi.shape[:2]
    small_w = max(1, w // strength)
    small_h = max(1, h // strength)
    small = cv2.resize(roi, (small_w, small_h))
    mosaic = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    image[y1:y2, x1:x2] = mosaic
    return image

def censor_image(input_path, output_path, mosaic_strength, logger):
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

        if class_name not in CENSOR_RULES:
            logger.info(f"  ⏭ ルール未定義のためスキップ: {class_name} (信頼度: {score:.2f})")
            continue

        rule = CENSOR_RULES[class_name]

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

        image = apply_mosaic(image, x1, y1, x2, y2, mosaic_strength)
        logger.info(f"  ✅ モザイク適用: {class_name} (信頼度: {score:.2f})")
        applied += 1

    cv2.imwrite(str(output_path), image)

    if applied == 0:
        logger.info(f"  ℹ 検出なし（モザイク未適用）→ {output_path.name}")
    else:
        logger.info(f"  💾 保存完了 ({applied}件適用) → {output_path.name}")

    return applied

def batch_censor(input_folder, mosaic_strength=15):
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
        result = censor_image(img_path, out_path, mosaic_strength, logger)

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
if __name__ == '__main__':

    # ★ 処理したいフォルダのパスを指定
    batch_censor(
        input_folder=r"Z:\StabilityMatrix\Images\censor\imgs",  # ← ここを変更
        mosaic_strength=15
    )