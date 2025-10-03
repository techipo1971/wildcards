import shutil
from pathlib import Path

# --- YAML 複数行リテラル変換 ---
def wrap_yaml_multiline(value: str, width: int = 70, base_indent: str = "") -> str:
    """
    文字列をカンマ区切りで折り返し、行末にカンマを付与。
    行長は base_indent を含めて width を超えないように調整。
    """
    parts = [p.strip() for p in value.split(",") if p.strip()]
    lines = []
    current = ""
    indent = base_indent + "    "  # 配列要素用インデント

    for part in parts:
        segment = (", " if current else "") + part
        # インデント込みで幅を計算
        if len(indent) + len(current) + len(segment) > width:
            lines.append(indent + current + ",")
            current = part
        else:
            current += segment

    if current:
        lines.append(indent + current + ",")
    return "\n".join(lines)


# --- YAML ファイル変換 ---
def process_yaml_file(file_path, width=70):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    result = []
    skip_next = False  # 次行が既存 - | の内容ならスキップ
    for i, line in enumerate(lines):
        if skip_next:
            result.append(line.rstrip())
            if line.strip() == "" or not line.startswith(" "):
                skip_next = False
            continue

        leading_ws_len = len(line) - len(line.lstrip(" "))
        indent = line[:leading_ws_len]
        stripped = line.strip()

        # 既存の - | を使っている行はそのままコピー
        if stripped.startswith("- |"):
            result.append(line.rstrip())
            skip_next = True
            continue

        if not stripped or stripped.startswith("#"):
            result.append(line.rstrip())
            continue

        # key: value
        if ":" in stripped and not stripped.startswith("- "):
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            # インデント込みで文字数をチェック
            if value and len(indent) + len("  - |") + len(value) > width:
                wrapped = wrap_yaml_multiline(value, width, base_indent=indent)
                result.append(f"{indent}{key}:")
                result.append(f"{indent}  - |")
                result.append(wrapped)
            else:
                result.append(line.rstrip())
        elif stripped.startswith("- "):
            content = stripped[2:].strip()
            if content and len(indent) + len("- |") + len(content) > width:
                wrapped = wrap_yaml_multiline(content, width, base_indent=indent)
                result.append(f"{indent}- |")
                result.append(wrapped)
            else:
                result.append(line.rstrip())
        else:
            result.append(line.rstrip())

    return "\n".join(result) + "\n"


# --- フォルダ直下の YAML を処理 ---
def process_folder(folder_path, width=70):
    folder = Path(folder_path)
    backup_folder = folder / "backup"
    backup_folder.mkdir(exist_ok=True)

    for file in folder.glob("*.yaml"):
        if file.is_file():
            # backup フォルダにコピー
            backup_path = backup_folder / file.name
            shutil.copy2(file, backup_path)

            # YAML 変換
            output_text = process_yaml_file(file, width)

            # 元ファイルに上書き
            with open(file, "w", encoding="utf-8") as f:
                f.write(output_text)

            print(f"Processed: {file} (backup: {backup_path})")


if __name__ == "__main__":
    script_folder = Path(__file__).parent
    process_folder(script_folder)
