import gradio as gr

# シンプルな関数
def greet(name):
    return f"こんにちは、{name} さん！"

# Gradio GUI
with gr.Blocks() as demo:
    gr.Markdown("## 👋 Gradio 簡単サンプル")

    with gr.Row():
        name = gr.Textbox(label="名前を入力")
        btn = gr.Button("実行")

    output = gr.Textbox(label="結果")

    btn.click(greet, inputs=name, outputs=output)

# 起動
if __name__ == "__main__":
    demo.launch()
