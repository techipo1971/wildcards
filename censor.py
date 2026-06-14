import csv
import cv2
import os
import hashlib
import json
from pathlib import Path
from nudenet import NudeDetector
from typing import Any
import logging
from dataclasses import dataclass
from datetime import datetime
from dataclasses import asdict

# ===== 設定（ここだけ触ればOK） =====
# 環境変数があればそれを優先。無ければ ./models/640m.onnx を使う
MODEL_PATH = Path(os.getenv("NUDE_MODEL_PATH", "./models/640m.onnx")).expanduser().resolve()

def sha256_file(p: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()

def build_model_id(model_path: Path) -> str:
    # 例: "640m.onnx@<sha256先頭12桁>"
    try:
        return f"{model_path.name}@{sha256_file(model_path)[:12]}"
    except Exception:
        # 取得できない場合でも最低限ファイル名は残す
        return model_path.name

# 起動時チェック（ここで落ちたらパス設定ミス）
if not MODEL_PATH.exists():
    raise FileNotFoundError(f"NUDE_MODEL_PATH not found: {MODEL_PATH}")

MODEL_ID = build_model_id(MODEL_PATH)

# detector 初期化（以降は detector.detect(...) をそのまま使える）
detector = NudeDetector(model_path=str(MODEL_PATH))

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

#Jsonl保存関数
def append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

#実行コンテクスト
@dataclass
class RunContext:
    run_id: str
    output_dir: Path
    jsonl_path: Path
    ruleset_name: str
    model_id: str
    near_threshold_delta: float = 0.05

#モザイク関数
def apply_blur(image, x1, y1, x2, y2, strength=40):
    roi = image[y1:y2, x1:x2]
    # カーネルサイズは奇数である必要がある
    ksize = strength * 2 + 1
    blurred = cv2.GaussianBlur(roi, (ksize, ksize), 0)
    image[y1:y2, x1:x2] = blurred
    return image
#############################################################################################################
def build_run_context_or_none():
    run_dir = os.getenv("RUN_DIR")
    if not run_dir:
        return None

    run_dir_p = Path(run_dir).expanduser().resolve()
    run_dir_p.mkdir(parents=True, exist_ok=True)

    run_id = run_dir_p.name  # フォルダ名を run_id にする

    return RunContext(
        run_id=run_id,
        output_dir=run_dir_p,
        jsonl_path=run_dir_p / "inference.jsonl",
        ruleset_name="CENSOR_RULES",
        model_id=MODEL_ID,
        near_threshold_delta=0.05,
    )

#############################################################################################################
# 変更点：
# - run: RunContext | None = None にする
# - run が None の場合、JSONL出力はしない

def censor_image(
    input_path: Path,
    output_path: Path,
    mosaic_strength: int,
    logger,
    *,
    rules: dict,
    run: "RunContext | None" = None,
    detector=None,
    apply_blur=apply_blur,
):
    """1枚処理。run が指定されたときだけ JSONL を書く（後方互換）。"""

    started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    record: dict[str, Any] = {
        "run_id": run.run_id if run else None,
        "ruleset": run.ruleset_name if run else None,
        "model_id": run.model_id if run else None,
        "started_at": started_at,
        "image_path": str(input_path),
        "image_hash": None,
        "thresholds": {k: v.get("threshold") for k, v in rules.items()},
        "detections": [],
        "applied": [],
        "applied_count": 0,
        "status": "unknown",
        "error": None,
    }

    def maybe_append_jsonl(rec: dict[str, Any]) -> None:
        if run is None:
            return
        append_jsonl(run.jsonl_path, rec)

    try:
        record["image_hash"] = sha256_file(input_path)
        detections = detector.detect(str(input_path))

        import cv2
        image = cv2.imread(str(input_path))
        if image is None:
            record["status"] = "read_error"
            record["error"] = f"cv2.imread failed: {input_path}"
            maybe_append_jsonl(record)
            logger.error(record["error"])
            return False

        img_h, img_w = image.shape[:2]

        for det in detections:
            cls = det.get("class")
            score = float(det.get("score", 0.0))
            box = det.get("box")
            if not (isinstance(box, (list, tuple)) and len(box) == 4):
                box = None
            record["detections"].append({"class": cls, "score": score, "box": box})

        applied = 0
        for det in detections:
            class_name = det["class"]
            score = float(det["score"])
            if class_name not in rules:
                continue
            rule = rules[class_name]
            if not rule.get("enabled", False):
                continue
            threshold = float(rule.get("threshold", 0.0))
            if score < threshold:
                continue

            box = det["box"]
            x1 = max(0, int(box[0]))
            y1 = max(0, int(box[1]))
            x2 = min(img_w, int(box[0] + box[2]))
            y2 = min(img_h, int(box[1] + box[3]))
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                continue

            image = apply_blur(image, x1, y1, x2, y2, mosaic_strength)
            record["applied"].append(
                {
                    "class": class_name,
                    "score": score,
                    "threshold": threshold,
                    "box": [x1, y1, x2 - x1, y2 - y1],
                }
            )
            applied += 1

        record["applied_count"] = applied

        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), image)

        record["status"] = "ok"
        maybe_append_jsonl(record)
        return applied

    except Exception as e:
        record["status"] = "exception"
        record["error"] = repr(e)
        maybe_append_jsonl(record)
        logger.exception(e)
        return False
    
#############################################################################################################
# Make run id
def make_run_id(prefix: str = "run") -> str:
    # 例: 2026-05-19_0915
    return datetime.now().strftime("%Y-%m-%d_%H%M")

#############################################################################################################
# Write csv
def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

#############################################################################################################
# Load jsonl
def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out

#############################################################################################################
def build_candidates(run_dir: Path, *, near_delta: float = 0.05, max_near: int = 500) -> None:
    """Phase1の成果物：no-detection / near-threshold の候補CSVとsummaryを作る"""
    jsonl = run_dir / "inference.jsonl"
    rows = load_jsonl(jsonl)

    # no-detection（画像単位）
    no_det = []
    # near-threshold（検出単位→あとで画像単位にまとめてもOK）
    near = []

    for r in rows:
        if r.get("status") != "ok":
            continue
        detections = r.get("detections") or []
        thresholds = r.get("thresholds") or {}

        if len(detections) == 0:
            no_det.append({
                "image_path": r.get("image_path"),
                "image_hash": r.get("image_hash"),
            })

        for d in detections:
            cls = d.get("class")
            score = d.get("score")
            if cls is None or score is None:
                continue
            thr = thresholds.get(cls)
            if thr is None:
                continue
            margin = abs(float(score) - float(thr))
            if margin <= near_delta:
                near.append({
                    "image_path": r.get("image_path"),
                    "image_hash": r.get("image_hash"),
                    "class": cls,
                    "score": float(score),
                    "threshold": float(thr),
                    "margin": float(margin),
                })

    # nearはmarginが小さい順に上位max_near
    near = sorted(near, key=lambda x: x["margin"])[:max_near]

    write_csv(
        run_dir / "candidates_no_detection.csv",
        no_det,
        fieldnames=["image_path", "image_hash"],
    )
    write_csv(
        run_dir / "candidates_near_threshold.csv",
        near,
        fieldnames=["image_path", "image_hash", "class", "score", "threshold", "margin"],
    )

    summary = {
        "run_dir": str(run_dir),
        "total_records": len(rows),
        "no_detection": len(no_det),
        "near_threshold": len(near),
        "near_delta": near_delta,
        "near_limit": max_near,
    }
    (run_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

#############################################################################################################
def batch_censor(input_folder: str, mosaic_strength: int = 40, rules=CENSOR_RULES, *, ruleset_name: str = "CENSOR_RULES"):
    input_dir = Path(input_folder)
    if not input_dir.exists():
        print(f"❌ フォルダが見つかりません: {input_folder}")
        return

    # 実行単位
    run_id = make_run_id()

    # runs の出力先は設定できるようにするのがおすすめ
    # - 例：スクリプトと同じ場所にログが散らばるのを防ぐ
    # - NAS運用でも「ログは専用ボリューム/専用フォルダ」に寄せられる
    # 優先順位：引数 run_root > 環境変数 CENSOR_RUNS_DIR > 既定 ./runs
    run_root = Path(os.getenv("CENSOR_RUNS_DIR", r"Z:\StabilityMatrix\Images\staging\runs")).expanduser().resolve()
    run_dir = run_root / run_id
    censored_dir = run_dir / "censored"
    censored_dir.mkdir(parents=True, exist_ok=True)
    # ロガー（既存の setup_logger を流用）
    log_path = run_dir / "censored.log"
    logger = setup_logger(log_path)

    # RunContext（前のセクションBで定義したものを使う）
    run = RunContext(
        run_id=run_id,
        output_dir=run_dir,
        jsonl_path=run_dir / "inference.jsonl",
        ruleset_name=ruleset_name,
        model_id=MODEL_ID,
        near_threshold_delta=0.05,
    )

    extensions = {".png", ".jpg", ".jpeg"}
    images = sorted([f for f in input_dir.iterdir() if f.suffix.lower() in extensions])
    if not images:
        logger.warning("対象画像が見つかりませんでした")
        return

    success = 0
    skipped = 0
    total_applied = 0

    logger.info(f"Run ID: {run_id}")
    logger.info(f"Input : {input_dir}")
    logger.info(f"Output: {censored_dir}")
    logger.info(f"JSONL : {run.jsonl_path}")

    for i, img_path in enumerate(images, 1):
        out_path = censored_dir / f"{img_path.stem}_censored{img_path.suffix}"
        logger.info(f"--- [{i}/{len(images)}] {img_path.name} ---")

        applied = censor_image(
            input_path=img_path,
            output_path=out_path,
            mosaic_strength=mosaic_strength,
            logger=logger,
            rules=rules,
            run=run,
            detector=detector,
            apply_blur=apply_blur,
        )

        if applied is False:
            skipped += 1
        else:
            success += 1
            total_applied += int(applied)

    logger.info(f"処理成功: {success} / スキップ: {skipped} / 総適用件数: {total_applied}")

    # Phase1成果物を生成
    build_candidates(run_dir, near_delta=run.near_threshold_delta, max_near=500)

    logger.info(f"完了: {run_dir}")
#############################################################################################################
def censor_files(img_list, *, mosaic_strength, logger, rules=CENSOR_RULES, run=None, detector=detector, apply_blur=apply_blur):
    ok = []

    for p in img_list:
        in_path = Path(p)
        # 出力先：入力フォルダと並列に「<input_folder>_censor」を作る
        # 例: /path/to/output -> /path/to/output_censor
        out_dir = in_path.parent.parent / (in_path.parent.name + "_censor")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / in_path.name  # 元ファイルは残し、加工後は別フォルダへ

        try:
            applied = censor_image(
                input_path=in_path,
                output_path=out_path,
                mosaic_strength=mosaic_strength,
                logger=logger,
                rules=rules,
                run=run,
                detector=detector,
                apply_blur=apply_blur,
            )
            # ok には「出力ファイルパス」を返す（以降の処理が加工後を使える）
            ok.append(str(out_path))
        except Exception as e:
            logger.error(f"Censor failed: {p}: {e}")

    return ok
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
        input_folder=r"Z:\StabilityMatrix\Images\staging\2026-05-19_workspace_r18\images",  # ← ここを変更
        mosaic_strength=40,
        rules=SAFE_MODE_RULES
    )
