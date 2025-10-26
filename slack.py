import os
from dotenv import load_dotenv

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# .envファイルを読み込む
load_dotenv()

#############################################################################################################
def send_slack_img(img_path, message=''):

    slack_token = os.getenv("SLACK_BOT_TOKEN")  # 環境変数から取得
    client = WebClient(token=slack_token)

    # ファイルパスとチャンネルID
    # file_path = "C:/StabilityMatrix/Images/2025-09-23_waiNSFWIllustrious_v150/20250923_060939_938658.png"
    channel_id = "C09G10F6SEB"  # 投稿先のチャンネルID

    try:
        resp = client.files_upload_v2(
            file=img_path,
            channel=channel_id,
            initial_comment=message,
            # 必要ならファイル情報取得要求を無効化してエラー回避
            request_file_info=False,
        )
        print("✅ アップロード成功:", resp["file"]["name"])
    except SlackApiError as e:
        print(f"❌ エラー: {e.response['error']}")

#############################################################################################################
def send_slack_message(message: str):
    """Slackにメッセージのみ送信する関数"""

    slack_token = os.getenv("SLACK_BOT_TOKEN")  # 環境変数から取得
    client = WebClient(token=slack_token)

    channel_id = "C09G10F6SEB"  # 投稿先のチャンネルID

    try:
        resp = client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        print("✅ メッセージ送信成功:", resp["ts"])
    except SlackApiError as e:
        print(f"❌ エラー: {e.response['error']}")

#############################################################################################################
if __name__ == '__main__':
    # テスト送信
    send_slack_message("これはテストメッセージです。")
    # send_slack_img("C:/StabilityMatrix/Images/2025-09-23_waiNSFWIllustrious_v150/20250923_060939_938658.png", "これはテスト画像です。")