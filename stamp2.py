import os
from tkinter import filedialog, Tk
from tkinter import Button, Label
from PIL import Image, PngImagePlugin

# 画像スタンプを画像に追加する関数
def add_stamp(input_folder, output_folder, stamp_image_path):
    # スタンプ画像を開く
    stamp_image = Image.open(stamp_image_path).convert("RGBA")

    # 入力フォルダ内の画像ファイルを取得
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif')):
            input_image_path = os.path.join(input_folder, filename)
            output_image_path = os.path.join(output_folder, filename)

            # 画像を開く
            image = Image.open(input_image_path).convert("RGBA")

            # メタデータを取得
            metadata = None
            exif_data = None
            if filename.lower().endswith(".png"):
                metadata = image.info  # PNGのメタデータ
            elif filename.lower().endswith(('.jpg', '.jpeg')):
                exif_data = image.getexif()  # JPEGのExifデータ

            # スタンプ画像のサイズを調整
            stamp_width = image.width // 2
            stamp_height = int(stamp_width * stamp_image.height / stamp_image.width)
            stamp_image_resized = stamp_image.resize((stamp_width, stamp_height))

            # スタンプを画像の右下に配置
            position = (image.width - stamp_width - 10, image.height - stamp_height - 300)

            # スタンプを合成
            image.paste(stamp_image_resized, position, stamp_image_resized)

            # PNGの場合はメタデータを維持
            if filename.lower().endswith(".png") and metadata:
                png_info = PngImagePlugin.PngInfo()
                for key, value in metadata.items():
                    png_info.add_text(key, str(value))
                image.save(output_image_path, pnginfo=png_info)

            # JPEGの場合はExifを維持
            elif filename.lower().endswith(('.jpg', '.jpeg')) and exif_data:
                image = image.convert("RGB")  # JPEGはRGBAをサポートしないため変換
                image.save(output_image_path, exif=exif_data)

            else:
                image.save(output_image_path)

            print(f"スタンプを追加した画像を保存しました: {output_image_path}")

# フォルダ選択のためのGUIを作成
def select_folders_and_stamp_image():
    # Tkinterウィンドウの設定
    root = Tk()
    root.withdraw()  # メインウィンドウを表示しない

    # 入力フォルダを選択
    input_folder = filedialog.askdirectory(title="入力フォルダを選択してください")
    if not input_folder:
        print("入力フォルダが選択されていません。終了します。")
        return

    # 出力フォルダを選択
    output_folder = filedialog.askdirectory(title="出力フォルダを選択してください")
    if not output_folder:
        print("出力フォルダが選択されていません。終了します。")
        return

    # スタンプ画像を選択
    stamp_image_path = r"C:\tmp\Mabo.AiArt2.png"  # 固定パス（必要なら変更）
    if not stamp_image_path:
        print("スタンプ画像が選択されていません。終了します。")
        return

    # 画像にスタンプを追加する処理を実行
    add_stamp(input_folder, output_folder, stamp_image_path)

    print("処理が完了しました。")

# GUI実行
if __name__ == "__main__":
    select_folders_and_stamp_image()
 