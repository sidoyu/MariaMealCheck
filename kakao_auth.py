"""
동료들이 카카오 로그인하여 토큰을 발급받는 Flask 서버.
실행: python kakao_auth.py
동료에게 http://<내IP>:5000 링크 공유 -> 카카오 로그인 -> 토큰 자동 저장
"""

import os
import json
import requests
from flask import Flask, redirect, request

app = Flask(__name__)

REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "642d14a35142a36d0b17431b8ce3924b")
CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET", "AEKncVr3gYDDWI9qk18PecV8GRKXddff")
REDIRECT_URI = "http://localhost:5001/callback"
TOKEN_FILE = "kakao_tokens.json"


def load_tokens():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return {}


def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2, ensure_ascii=False)


@app.route("/")
def index():
    # 카카오 로그인 페이지로 리다이렉트
    kakao_auth_url = (
        f"https://kauth.kakao.com/oauth/authorize"
        f"?client_id={REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=talk_message"
    )
    return redirect(kakao_auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "인가 코드가 없습니다. 다시 시도해주세요.", 400

    # 인가 코드 -> Access Token 교환
    token_resp = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": REST_API_KEY,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )

    if token_resp.status_code != 200:
        return f"토큰 발급 실패: {token_resp.text}", 400

    token_data = token_resp.json()
    access_token = token_data["access_token"]

    # 사용자 정보 조회 (닉네임 확인용)
    user_resp = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_info = user_resp.json()
    user_id = str(user_info["id"])
    nickname = user_info.get("kakao_account", {}).get("profile", {}).get("nickname", "알 수 없음")

    # 토큰 저장
    tokens = load_tokens()
    tokens[user_id] = {
        "nickname": nickname,
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_in": token_data.get("expires_in"),
        "refresh_token_expires_in": token_data.get("refresh_token_expires_in"),
    }
    save_tokens(tokens)

    return f"""
    <h2>등록 완료!</h2>
    <p><b>{nickname}</b>님, 식단 알림 등록이 완료되었습니다.</p>
    <p>매일 평일 11:30에 카카오톡으로 식단이 발송됩니다.</p>
    <p>이 페이지를 닫아도 됩니다.</p>
    """


if __name__ == "__main__":
    print("=== 카카오 인증 서버 시작 ===")
    print(f"동료에게 이 링크를 공유하세요: http://localhost:5000")
    print("Ctrl+C로 종료")
    app.run(host="0.0.0.0", port=5001)
