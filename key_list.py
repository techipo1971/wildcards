import yaml
import os

def extract_keys_with_path(data, parent_key="", keys_set=None):
    """YAMLデータから全てのキーを親子階層付き(/区切り)で再帰的に抽出"""
    if keys_set is None:
        keys_set = set()

    if isinstance(data, dict):
        for key, value in data.items():
            full_key = f"{parent_key}/{key}" if parent_key else str(key)

            # 子要素がある場合のみ /* を付与
            if isinstance(value, dict) and value:
                keys_set.add(full_key + "/*")
            elif isinstance(value, list) and any(isinstance(i, dict) for i in value):
                keys_set.add(full_key + "/*")
            else:
                keys_set.add(full_key)

            extract_keys_with_path(value, full_key, keys_set)

    elif isinstance(data, list):
        for item in data:
            extract_keys_with_path(item, parent_key, keys_set)

    return keys_set

def process_yaml_file(yaml_path, output_txt_path):
    if not os.path.exists(yaml_path):
        print(f"ファイルが見つかりません: {yaml_path}")
        return

    # YAML読み込み
    with open(yaml_path, 'r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"YAMLの読み込みエラー ({yaml_path}): {e}")
            return

    if data is None:
        print(f"{yaml_path} は空のYAMLです。スキップします。")
        return

    # キー抽出
    keys = extract_keys_with_path(data)

    # 出力
    with open(output_txt_path, 'w', encoding='utf-8') as f:
        for key in sorted(keys):
            f.write(f"__{key}__\n")

    print(f"{yaml_path} → {output_txt_path} に {len(keys)} 個のキーを保存しました。")

if __name__ == "__main__":
    # ======= ここを手動で設定 =======
    files = [
        ("nsfw.yaml", "r18+.txt"),
        ("nude.yaml",  "r18.txt"),
        ("chara.yaml",  "chara.txt"),
        ("erotic.yaml",  "erotic.txt"),
        # ("別のファイル.yaml", "別の出力.txt"),
    ]
    # ==============================

    for yaml_file, output_file in files:
        process_yaml_file(yaml_file, output_file)





# import yaml
# import os

# def extract_keys_with_path(data, parent_key="", keys_set=None):
#     """YAMLデータから全てのキーを親子階層付き(/区切り)で再帰的に抽出"""
#     if keys_set is None:
#         keys_set = set()

#     if isinstance(data, dict):
#         for key, value in data.items():
#             full_key = f"{parent_key}/{key}" if parent_key else str(key)
#             # 子要素がある場合は /* を付ける
#             if isinstance(value, (dict, list)) and value:
#                 keys_set.add(full_key + "/*")
#             else:
#                 keys_set.add(full_key)
#             extract_keys_with_path(value, full_key, keys_set)
#     elif isinstance(data, list):
#         for item in data:
#             extract_keys_with_path(item, parent_key, keys_set)

#     return keys_set

# def process_yaml_file(yaml_path, output_txt_path):
#     if not os.path.exists(yaml_path):
#         print(f"ファイルが見つかりません: {yaml_path}")
#         return

#     # YAML読み込み
#     with open(yaml_path, 'r', encoding='utf-8') as f:
#         try:
#             data = yaml.safe_load(f)
#         except yaml.YAMLError as e:
#             print(f"YAMLの読み込みエラー ({yaml_path}): {e}")
#             return

#     if data is None:
#         print(f"{yaml_path} は空のYAMLです。スキップします。")
#         return

#     # キー抽出
#     keys = extract_keys_with_path(data)

#     # 出力
#     with open(output_txt_path, 'w', encoding='utf-8') as f:
#         for key in sorted(keys):
#             f.write(f"__{key}__\n")

#     print(f"{yaml_path} → {output_txt_path} に {len(keys)} 個のキーを保存しました。")



# import yaml

# def extract_keys_with_path(data, parent_key="", keys_set=None):
#     """YAMLデータから全てのキーを親子階層付き(/区切り)で再帰的に抽出"""
#     if keys_set is None:
#         keys_set = set()

#     if isinstance(data, dict):
#         for key, value in data.items():
#             full_key = f"{parent_key}/{key}" if parent_key else str(key)
#             # 子要素があるかどうか判定
#             if isinstance(value, (dict, list)) and value:
#                 keys_set.add(full_key + "/*")
#             else:
#                 keys_set.add(full_key)
#             extract_keys_with_path(value, full_key, keys_set)
#     elif isinstance(data, list):
#         for item in data:
#             extract_keys_with_path(item, parent_key, keys_set)

#     return keys_set

# def main(yaml_path, output_txt_path):
#     # YAMLファイル読み込み
#     with open(yaml_path, 'r', encoding='utf-8') as f:
#         data = yaml.safe_load(f)

#     # キーを抽出
#     keys = extract_keys_with_path(data)

#     # ソートして保存（__付き）
#     with open(output_txt_path, 'w', encoding='utf-8') as f:
#         for key in sorted(keys):
#             f.write(f"__{key}__\n")

#     print(f"階層付きキー（親は/*付き）を {output_txt_path} に保存しました。")

# if __name__ == "__main__":
#     yaml_file = "nsfw.yaml"      # 入力YAMLファイル
#     output_file = "r18+.txt" # 出力テキストファイル
#     # yaml_file = "nude.yaml"      # 入力YAMLファイル
#     # output_file = "r18.txt" # 出力テキストファイル
#     main(yaml_file, output_file)
