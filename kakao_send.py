"""
카카오톡 메시지 발송 모듈.
- 저장된 토큰으로 "나에게 보내기" API를 사용하여 각 동료에게 식단 발송
- 토큰 만료 시 자동 갱신
"""

import os
import json
import requests

REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "642d14a35142a36d0b17431b8ce3924b")
CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "AEKncVr3gYDDWI9qk18PecV8GRKXddff")
TOKEN_FILE = "kakao_tokens.json"


def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)


def refresh_access_token(user_id, user_data):
    """Refresh Token으로 Access Token 갱신"""
    resp = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": REST_API_KEY,
            "client_secret": CLIENT_SECRET,
            "refresh_token": user_data["refresh_token"],
        },
    )

    if resp.status_code != 200:
        print(f"[{user_data['nickname']}] 토큰 갱신 실패: {resp.text}")
        return None

    new_data = resp.json()
    user_data["access_token"] = new_data["access_token"]
    # refresh_token이 응답에 포함되면 업데이트 (만료 임박 시 새로 발급됨)
    if "refresh_token" in new_data:
        user_data["refresh_token"] = new_data["refresh_token"]

    return user_data


def send_kakao_message(access_token, title, menu_text):
    """나에게 보내기 API로 텍스트 메시지 발송"""
    import json as _json

    template_object = {
        "object_type": "text",
        "text": f"[{title}]\n\n{menu_text}",
        "link": {
            "web_url": "https://mail.mariababy.com/bbs/bbs_list.aspx?bbs_num=41",
            "mobile_web_url": "https://mail.mariababy.com/bbs/bbs_list.aspx?bbs_num=41",
        },
        "button_title": "식단표 원본 보기",
    }

    resp = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": _json.dumps(template_object)},
    )
    return resp


def send_to_all(title, today_menu_text):
    """
    등록된 모든 사용자에게 카카오톡 메시지 발송.
    각 사용자의 "나에게 보내기" API를 호출하므로 친구 권한 불필요.
    """
    tokens = load_tokens()
    if not tokens:
        print("등록된 카카오톡 사용자가 없습니다.")
        return

    updated = False
    for user_id, user_data in tokens.items():
        nickname = user_data.get("nickname", user_id)

        # 메시지 발송 시도
        resp = send_kakao_message(user_data["access_token"], title, today_menu_text)

        # 토큰 만료 시 갱신 후 재시도
        if resp.status_code == 401:
            print(f"[{nickname}] 토큰 만료, 갱신 시도...")
            refreshed = refresh_access_token(user_id, user_data)
            if refreshed:
                tokens[user_id] = refreshed
                updated = True
                resp = send_kakao_message(refreshed["access_token"], title, today_menu_text)
            else:
                print(f"[{nickname}] 토큰 갱신 실패, 재인증 필요")
                continue

        if resp.status_code == 200:
            print(f"[{nickname}] 카카오톡 발송 성공")
        else:
            print(f"[{nickname}] 카카오톡 발송 실패: {resp.status_code} {resp.text}")

    if updated:
        save_tokens(tokens)
