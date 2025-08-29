#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import time
import datetime
import requests

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID")
FILE_PATH = os.environ.get("FILE_PATH", "calendar.png")
jst = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
today_str = jst.strftime("%Y-%m-%d")
INITIAL_COMMENT = f"本日（{today_str}）の離脱期間一覧カレンダーです。"
FILE_TITLE = os.environ.get("FILE_TITLE", "4-week calendar")
TIMEOUT = float(os.environ.get("SLACK_HTTP_TIMEOUT", "30"))

API_BASE = "https://slack.com/api"

def _fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def _slack_post(method: str, data=None, files=None, headers=None, json_body=None):
    url = f"{API_BASE}/{method}"
    hdrs = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    if headers:
        hdrs.update(headers)
    if json_body is not None:
        hdrs["Content-Type"] = "application/json; charset=utf-8"
        resp = requests.post(url, headers=hdrs, data=json.dumps(json_body), timeout=TIMEOUT)
    else:
        resp = requests.post(url, headers=hdrs, data=data, files=files, timeout=TIMEOUT)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"ok": False, "error": f"non_json_response:{resp.text[:200]}"}

def main():
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        _fail("SLACK_BOT_TOKEN or SLACK_CHANNEL_ID is not set.")

    if not os.path.exists(FILE_PATH):
        print(f"{FILE_PATH} not found. Exit 0.", file=sys.stderr)
        sys.exit(0)

    # ファイルサイズ・名前
    filename = os.path.basename(FILE_PATH)
    file_len = os.path.getsize(FILE_PATH)

    # 1) アップロードURLを取得
    # content-type: x-www-form-urlencoded と同等の form 送信でOK
    print(f"[1/3] Requesting upload URL for {filename} ({file_len} bytes)")
    status, j = _slack_post(
        "files.getUploadURLExternal",
        data={"filename": filename, "length": str(file_len)},
    )
    if not j.get("ok"):
        _fail(f"files.getUploadURLExternal failed (HTTP {status}): {j}")
    upload_url = j["upload_url"]
    file_id = j["file_id"]

    # 2) 取得したURLへファイル本体をアップロード（本文のみ、認証不要）
    print(f"[2/3] Uploading binary to Slack upload_url")
    with open(FILE_PATH, "rb") as f:
        # Slack側は POST/PUT 双方受け付けますが octet-stream で送れば安定
        resp = requests.post(upload_url, data=f, headers={"Content-Type": "application/octet-stream"}, timeout=TIMEOUT)
    if not resp.ok:
        _fail(f"binary upload failed (HTTP {resp.status_code}): {resp.text[:200]}")


    print(f"[3/3] Completing upload & sharing to channel {SLACK_CHANNEL_ID}")
    payload = {
        "channel_id": SLACK_CHANNEL_ID,
        "initial_comment": INITIAL_COMMENT,
        "files": [
            {
                "id": file_id,
                "title": FILE_TITLE or filename,
            }
        ],
    }
    status, j = _slack_post("files.completeUploadExternal", json_body=payload)
    if not j.get("ok"):
        _fail(f"files.completeUploadExternal failed (HTTP {status}): {j}")

    file_obj = j.get("files", [{}])[0]
    print(f"✅ Uploaded to Slack: file_id={file_obj.get('id')} name={file_obj.get('name')}")

if __name__ == "__main__":
    main()
