import io
from PIL import Image
import requests
import gradio as gr
import random

SD_API_TXT2IMG = "http://127.0.0.1:7860/sdapi/v1/txt2img"
SD_API_UPSCALE = "http://127.0.0.1:7860/sdapi/v1/extra-single-image"
SD_API_UPSCALERS = "http://127.0.0.1:7860/sdapi/v1/upscalers"

stop_flag = False

# --------------------
# ユーティリティ関数
# --------------------
def get_models():
    try:
        response = requests.get("http://127.0.0.1:7860/sdapi/v1/sd-models")
        if response.status_code == 200:
            return [m["model_name"] for m in response.json()]
    except:
        pass
    return ["stable-diffusion-v1-5"]

def get_samplers():
    try:
        response = requests.get("http://127.0.0.1:7860/sdapi/v1/samplers")
        if response.status_code == 200:
            return [s["name"] for s in response.json()]
    except:
        pass
    return ["Euler a"]

def get_upscalers():
    try:
        response = requests.get(SD_API_UPSCALERS)
        if response.status_code == 200:
            return [u["name"] for u in response.json()]
    except:
        pass
    return ["Latent", "R-ESRGAN 4x+", "SwinIR_4x"]

# --------------------
# ステップ1: txt2img生成
# --------------------
def generate_images(prompt, neg_prompt, model, sampler, steps, cfg, seed, batch_size, batch_count):
    results = []
    for _ in range(int(batch_count)):
        actual_seed = int(seed) if seed >=0 else random.randint(0, 2**32-1)
        payload = {
            "prompt": prompt,
            "negative_prompt": neg_prompt,
            "steps": int(steps),
            "cfg_scale": float(cfg),
            "sampler_name": sampler,
            "seed": actual_seed,
            "batch_size": int(batch_size),
        }
        response = requests.post(SD_API_TXT2IMG, json=payload)
        if response.status_code == 200:
            r = response.json()
            for img_b64 in r["images"]:
                img_bytes = io.BytesIO(base64.b64decode(img_b64))
                results.append(Image.open(img_bytes))
    return results

# --------------------
# ステップ2: アップスケール
# --------------------
def upscale_images(files, scale, upscaler, repeat):
    global stop_flag
    outputs = []
    valid_exts = [".png", ".jpg", ".jpeg", ".webp"]
    images = [f for f in files if any(f.name.lower().endswith(ext) for ext in valid_exts)]

    for img_file in images:
        if stop_flag: break
        img_bytes = img_file.read()
        result_img = img_bytes
        for _ in range(int(repeat)):
            if stop_flag: break
            payload = {
                "resize_mode": 0,
                "upscaler_1": upscaler,
                "upscaler_2": "None",
                "extras_upscaler_1": upscaler,
                "extras_upscaler_2": "None",
                "upscaling_resize": float(scale),
                "upscaling_resize_w": 0,
                "upscaling_resize_h": 0,
                "upscaling_crop": True,
            }
            response = requests.post(
                SD_API_UPSCALE,
                files={"image": ("image.png", result_img, "image/png")},
                json=payload
            )
            if response.status_code == 200:
                result_img = response.content
            else:
                break
        outputs.append(Image.open(io.BytesIO(result_img)))
    stop_flag = False
    return outputs

def cancel_process():
    global stop_flag
    stop_flag = True

# --------------------
# GUI構築
# --------------------
models = get_models()
samplers = get_samplers()
upscalers = get_upscalers()

with gr.Blocks() as demo:
    gr.Markdown("## SD 画像生成 + 選択画像アップスケーラー (Gradio 5.43.1)")

    # --------------------
    # ステップ1
    # --------------------
    with gr.Tab("ステップ1: 画像生成"):
        with gr.Column():
            prompt = gr.Textbox(label="プロンプト")
            neg_prompt = gr.Textbox(label="ネガティブプロンプト")
            model_dropdown = gr.Dropdown(choices=models, value=models[0], label="モデル")
            sampler_dropdown = gr.Dropdown(choices=samplers, value=samplers[0], label="Sampler")
            steps_num = gr.Number(value=20, label="Steps")
            cfg_scale = gr.Number(value=7.0, label="CFG Scale")
            seed_num = gr.Number(value=-1, label="Seed (-1でランダム)")
            batch_size = gr.Number(value=1, label="Batch Size")
            batch_count = gr.Number(value=1, label="Batch Count")
            generate_btn = gr.Button("生成開始")
            gen_gallery = gr.Gallery(label="生成結果")

    # --------------------
    # ステップ2
    # --------------------
    with gr.Tab("ステップ2: 選択画像アップスケール"):
        with gr.Row():
            img_input = gr.File(
                label="アップスケールする画像を選択",
                type="binary",
                file_count="multiple",
                file_types=[".png", ".jpg", ".jpeg", ".webp"]
            )
            upscaler_dropdown = gr.Dropdown(choices=upscalers, value=upscalers[0], label="アップスケーラー")
        with gr.Row():
            scale_num = gr.Number(value=2.0, label="倍率")
            repeat_num = gr.Number(value=1, label="繰り返し回数")
        gallery_output = gr.Gallery(label="アップスケール結果")
        upscale_btn = gr.Button("アップスケール開始")
        cancel_btn = gr.Button("キャンセル")

    # --------------------
    # イベント
    # --------------------
    generate_btn.click(
        generate_images,
        inputs=[prompt, neg_prompt, model_dropdown, sampler_dropdown, steps_num, cfg_scale, seed_num, batch_size, batch_count],
        outputs=[gen_gallery]
    )

    upscale_btn.click(
        upscale_images,
        inputs=[img_input, scale_num, upscaler_dropdown, repeat_num],
        outputs=[gallery_output]
    )

    cancel_btn.click(cancel_process, inputs=None, outputs=None)

demo.launch()
