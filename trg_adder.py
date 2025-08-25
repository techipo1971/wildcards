from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
import re

# 対象の YAML ファイル
yaml_file = r"C:\StabilityMatrix\Packages\Stable Diffusion WebUI\extensions\sd-dynamic-prompts\wildcards\chara.yaml"

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096

with open(yaml_file, "r", encoding="utf-8") as f:
    data = yaml.load(f)

# prompt の一行目に ${trg: がなければ追加
for work_name, characters in data.items():
    if not isinstance(characters, dict):
        continue

    for char_name, char_info in characters.items():
        if not isinstance(char_info, dict):
            continue

        prompts = char_info.get("prompt", [])
        new_prompts = []
        for p in prompts:
            lines = str(p).splitlines()
            if lines and not lines[0].startswith("${trg:"):
                # 行末コメントを保持
                m = re.match(r"(.*?)(\s*#.*)?$", lines[0])
                main_text = m.group(1).rstrip()
                comment_text = m.group(2) or ""
                lines[0] = "${trg:" + main_text + "}" + comment_text
            new_prompts.append(LiteralScalarString("\n".join(lines)))
        char_info["prompt"] = new_prompts

# 上書き保存
with open(yaml_file, "w", encoding="utf-8") as f:
    yaml.dump(data, f)

print("✅ ${trg: } の付与処理が完了しました")
