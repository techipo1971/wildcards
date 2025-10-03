import argparse
from InquirerPy import inquirer

parser = argparse.ArgumentParser(description="引数のサンプル")
parser.add_argument("--count", type=int, help="Batch countを入力してください")
parser.add_argument("--char_num", type=int, help="character numberを入力してください")
parser.add_argument("--mode", help="modeを入力してください")

args = parser.parse_args()

if not args.count:
    args.count = input("count ? : ")

if not args.char_num:
    args.char_num = input("character number ? : ")

choice = inquirer.select(
    message = "mode ? :",
    choices = ["random", "scenario", "keyword search", "prick up"]
).execute()

print(f"Batch count >>> {args.count}")
print(f"Character number >>> {args.char_num} ")
print(f"Mode >>> {choice}")
