from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

import re

# 上書きする YAML ファイル
yaml_file = r"C:\StabilityMatrix\Packages\Stable Diffusion WebUI\extensions\sd-dynamic-prompts\wildcards\chara.yaml"

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096  # 長い行も折り返さず保持

with open(yaml_file, "r", encoding="utf-8") as f:
    data = yaml.load(f)

# 正規化処理＋${trg:変換（コメント保持）
for work_name, characters in data.items():
    if not isinstance(characters, dict):
        continue

    for char_name, char_info in characters.items():

        # dict の場合
        if isinstance(char_info, dict):
            if "name" not in char_info:
                char_info["name"] = char_name
            if "prompt" not in char_info or char_info["prompt"] is None:
                char_info["prompt"] = []

            prompts = char_info["prompt"]

            for i, p in enumerate(prompts):
                # p は ruamel.yaml scalar
                p_lines = str(p).splitlines()
                if p_lines and not p_lines[0].startswith("${trg:"):
                    # 行末コメントを保持
                    m = re.match(r"(.*?)(\s*#.*)?$", p_lines[0])
                    main_text = m.group(1).rstrip()
                    comment_text = m.group(2) or ""
                    p_lines[0] = "${trg:" + main_text + "}" + comment_text
                    # 元のノードを直接置き換え（コメント保持）
                    p.value = "\n".join(p_lines)

        # 文字列やリストの場合は dict に変換して正規化
        elif isinstance(char_info, str):
            lines = char_info.splitlines()
            if lines and not lines[0].startswith("${trg:"):
                m = re.match(r"(.*?)(\s*#.*)?$", lines[0])
                main_text = m.group(1).rstrip()
                comment_text = m.group(2) or ""
                lines[0] = "${trg:" + main_text + "}" + comment_text
            char_info = {"name": char_name, "prompt": [LiteralScalarString("\n".join(lines))]}
            data[work_name][char_name] = char_info

        elif isinstance(char_info, list):
            prompts = []
            for item in char_info:
                if isinstance(item, str):
                    lines = item.splitlines()
                    if lines and not lines[0].startswith("${trg:"):
                        m = re.match(r"(.*?)(\s*#.*)?$", lines[0])
                        main_text = m.group(1).rstrip()
                        comment_text = m.group(2) or ""
                        lines[0] = "${trg:" + main_text + "}" + comment_text
                    prompts.append(LiteralScalarString("\n".join(lines)))
            data[work_name][char_name] = {"name": char_name, "prompt": prompts}

# ====== 作品名とキャラ名のアルファベット順にソート ======
sorted_data = dict(sorted(data.items(), key=lambda x: x[0].lower()))
for work_name, characters in sorted_data.items():
    if isinstance(characters, dict):
        sorted_chars = dict(sorted(characters.items(), key=lambda x: x[0].lower()))
        sorted_data[work_name] = sorted_chars

# YAML 上書き保存
with open(yaml_file, "w", encoding="utf-8") as f:
    yaml.dump(sorted_data, f)

print(f"フォーマットと${{trg: …}}変換完了（前置きコメント保持）: {yaml_file}")
