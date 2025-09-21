import os
import yaml

def search_yaml_in_folder(folder, search_text):
    results = []
    search_text_lower = search_text.lower()

    for filename in os.listdir(folder):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            filepath = os.path.join(folder, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception as e:
                print(f"[ERROR] {filepath}: {e}")
                continue

            def traverse(node):
                if isinstance(node, dict):
                    for v in node.values():
                        traverse(v)
                elif isinstance(node, list):
                    for item in node:
                        traverse(item)
                elif isinstance(node, str):
                    if search_text_lower in node.lower():
                        results.append(node)

            traverse(data)

    return results

# if __name__ == "__main__":
#     # 検索対象フォルダ（スクリプトと同じ場所なら "."）
#     folder = "."
#     search_text = input("検索文字列を入力してください: ")

#     matches = search_yaml_in_folder(folder, search_text)

#     if matches:
#         print("\n=== 検索結果 ===")
#         for filepath, path, value in matches:
#             print(f"{filepath} :: {path} -> {value}")
#     else:
#         print("一致する要素が見つかりませんでした。")
