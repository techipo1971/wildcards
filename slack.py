import os
from dotenv import load_dotenv
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# # .envファイルを読み込む
# # スクリプトと同じフォルダの.envを読む
# dotenv_path = Path(__file__).parent / ".env"
# print(f"Loading .env from: {dotenv_path}")

# load_dotenv(dotenv_path, override=True)

slack_token = os.getenv("SLACK_BOT_TOKEN")  # 環境変数から取得
slack_channel_id = os.getenv("SLACK_CHANNEL_ID")  # 投稿先のチャンネルID

# print(f"Token: {slack_token}")  # 確認用
# print(f"Channel: {slack_channel_id}")  # 確認用

#タイムアウトを設定（60秒）
timeout_seconds=60
client = WebClient(token=slack_token,timeout=timeout_seconds)

#############################################################################################################
def send_slack_img(img_path, message=''):

    try:
        resp = client.files_upload_v2(
            file=img_path,
            channel=slack_channel_id,
            initial_comment=message,
            # 必要ならファイル情報取得要求を無効化してエラー回避
            request_file_info=False,
        )
        print("✅ Slack upload success:", resp["file"]["name"])
    except SlackApiError as e:
        print(f"❌ Slack upload error: {e.response['error']}")

#############################################################################################################
def send_slack_message(message: str):
    """Slackにメッセージのみ送信する関数"""

    try:
        resp = client.chat_postMessage(
            channel=slack_channel_id,
            text=message
        )
        print("✅ メッセージ送信成功:", resp["ts"])
    except SlackApiError as e:
        print(f"❌ エラー: {e.response['error']}")

#############################################################################################################
if __name__ == '__main__':
    # テスト送信
    # send_slack_message("これはテストメッセージです。")
    send_slack_img(r"Z:\StabilityMatrix\Images\forRelease\moca aoba_20260509140942373484_58.png", "これはテスト画像です。")