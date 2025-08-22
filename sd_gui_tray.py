import gradio as gr
import requests
import base64
import io
from PIL import Image
import threading
import pystray
from pystray import MenuItem as item
import sys
import os
import time

# =======================
# WebUI API設定
# =======================
API_URL = "http://127.0.0.1:7860"

# =======================
# チェックポイント一覧取得
# =======================
def get_checkpoints():
    try:
        r = requests.get(f"{API_URL}/sdapi/v1/sd-models")
        r.raise_for_status()
        return [m["title"] for m in r.json()]
    except Exception as e:
        print("モデル一覧取得失敗:", e)
        return ["default"]

# =======================
# モデル切替
# =======================
def switch_model(model_name):
    try:
        payload = {"sd_model_checkpoint": model_name}
        r = requests.post(f"{API_URL}/sdapi/v1/options", json=payload)
        r.raise_for_status()
        return f"モデル {model_name} に切り替えました"
    except Exception as e:
        return f"モデル切替失敗: {e}"

# =======================
# txt2img 画像生成
# =======================
def generate_image(prompt, model_name, steps=20, width=512, height=512):
    switch_model(model_name)
    payload = {
        "prompt": prompt,
        "steps": steps,
        "width": width,
        "height": height
    }
    r = requests.post(f"{API_URL}/sdapi/v1/txt2img", json=payload)
    data = r.json()
    img_base64 = data["images"][0]
    image = Image.open(io.BytesIO(base64.b64decode(img_base64)))
    return image

# =======================
# アップスケール
# =======================
def upscale_image(image, scale=2, upscaler="R-ESRGAN 4x+"):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    payload = {
        "image": img_str,
        "resize_mode": 0,
        "upscaler_1": upscaler,
        "scale": scale
    }
    r = requests.post(f"{API_URL}/sdapi/v1/extra-single-image", json=payload)
    data = r.json()
    img_base64 = data["image"]
    image = Image.open(io.BytesIO(base64.b64decode(img_base64)))
    return image

# =======================
# Gradio GUI
# =======================
def start_gui():
    with gr.Blocks() as demo:
        gr.Markdown("## Stability Matrix A1111 GUI (txt2img + アップスケール)")

        # モデル選択
        model_dropdown = gr.Dropdown(choices=get_checkpoints(), label="モデル選択")

        # txt2img
        with gr.Tab("テキスト生成"):
            prompt_input = gr.Textbox(label="プロンプト", placeholder="例: a fantasy landscape")
            steps_slider = gr.Slider(1, 50, value=20, step=1, label="ステップ数")
            gen_btn = gr.Button("生成")
            gen_output = gr.Image(label="生成結果")
            gen_btn.click(generate_image, inputs=[prompt_input, model_dropdown, steps_slider], outputs=gen_output)

        # アップスケール
        with gr.Tab("アップスケール"):
            img_input = gr.Image(type="pil", label="アップスケールする画像")
            scale_slider = gr.Slider(1, 4, value=2, step=1, label="倍率")
            upscaler_dropdown = gr.Dropdown(choices=["R-ESRGAN 4x+", "ESRGAN_4x", "Lanczos"], label="アップスケーラー", value="R-ESRGAN 4x+")
            up_btn = gr.Button("アップスケール実行")
            up_output = gr.Image(label="アップスケール結果")
            up_btn.click(upscale_image, inputs=[img_input, scale_slider, upscaler_dropdown], outputs=up_output)

        demo.launch(server_name="127.0.0.1", server_port=7861, share=False)

# =======================
# pystray タスクトレイ
# =======================
def create_tray():
    # アイコン作成
    image = Image.new('RGB', (64,64), (0,128,255))
    # 簡易な四角アイコン
    icon = pystray.Icon("SD_GUI", image, "SD GUI",
                        menu=pystray.Menu(
                            item('表示/非表示', lambda icon, item: threading.Thread(target=start_gui).start()),
                            item('終了', lambda icon, item: icon.stop())
                        ))
    icon.run()

# =======================
# 起動
# =======================
if __name__ == "__main__":
    # GUIをスレッドで起動してもタスクトレイをブロックしない
    threading.Thread(target=create_tray).start()
