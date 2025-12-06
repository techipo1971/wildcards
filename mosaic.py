import cv2
import torch
from ultralytics import YOLO


# ============================
# 1. GPU の確認
# ============================
if not torch.cuda.is_available():
    raise RuntimeError("CUDAが利用できません。GPU環境を確認してください。")

print("CUDA device:", torch.cuda.get_device_name(0))


# ============================
# 2. YOLO モデル読み込み (GPU)
# ============================
# ※ 自分で学習したセンシティブ検出モデルを指定
model = YOLO("model.pt")     # ★ここに自分のモデル
DEVICE = "cuda"


# ============================
# 3. OpenCV CUDA でモザイク処理
# ============================
def mosaic_cuda(img, x1, y1, x2, y2, ratio=0.05):
    """
    OpenCV(CUDA) を使って対象範囲をモザイク化
    ratio: 小さくする割合（小さいほど荒いモザイク）
    """
    w, h = x2 - x1, y2 - y1
    cut = img[y1:y2, x1:x2]

    # GPU にアップロード
    gpu = cv2.cuda_GpuMat()
    gpu.upload(cut)

    # モザイク処理：縮小 → 拡大
    small = cv2.cuda.resize(gpu, (max(1, int(w * ratio)), max(1, int(h * ratio))))
    mosaic_gpu = cv2.cuda.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

    # CPU メモリに戻す
    mosaic = mosaic_gpu.download()

    # 元画像へ反映
    img[y1:y2, x1:x2] = mosaic
    return img


# ============================
# 4. 検出 + モザイク処理
# ============================
def process_image(input_path: str, output_path: str, mosaic_ratio=0.05):
    # 画像読み込み
    img = cv2.imread(input_path)
    if img is None:
        raise FileNotFoundError(f"画像が読み込めません: {input_path}")

    # 推論（GPU）
    results = model(input_path, device=DEVICE)[0]

    # バウンディングボックスごとに処理
    for box in results.boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        img = mosaic_cuda(img, x1, y1, x2, y2, ratio=mosaic_ratio)

    # 保存
    cv2.imwrite(output_path, img)
    print(f"処理完了: {output_path}")


# ============================
# 5. 実行例
# ============================
if __name__ == "__main__":
    process_image(
        input_path="input.png",
        output_path="output.png",
        mosaic_ratio=0.04,   # モザイク強め
    )
