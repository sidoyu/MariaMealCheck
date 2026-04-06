"""
알리고 브랜드메시지(친구톡) API를 통한 카카오톡 식단 알림 발송 모듈.
"""

import os
import json
import requests

ALIGO_API_KEY = os.environ.get("ALIGO_API_KEY", "7k7x7th7425mdzj10hsdbz7ckloyogpg")
ALIGO_USER_ID = os.environ.get("ALIGO_USER_ID", "sidoyu")
ALIGO_SENDER_KEY = os.environ.get("ALIGO_SENDER_KEY", "1ad86f2ec6662a73514aba2de3a51e2909527962")
ALIGO_SENDER = os.environ.get("ALIGO_SENDER", "01020241731")
TEMPLATE_CODE = "AAAA1650"

# 수신자 전화번호 목록
RECEIVERS = os.environ.get("ALIGO_RECEIVERS", "").split(",")


def send_brandtalk(date_str, menu_text):
    """등록된 모든 수신자에게 브랜드메시지 발송"""
    receivers = [r.strip() for r in RECEIVERS if r.strip()]
    if not receivers:
        print("등록된 수신자가 없습니다.")
        return

    data = {
        "apikey": ALIGO_API_KEY,
        "userid": ALIGO_USER_ID,
        "senderkey": ALIGO_SENDER_KEY,
        "sender": ALIGO_SENDER,
        "template_code": TEMPLATE_CODE,
        "advert_yn": "N",
    }

    for i, phone in enumerate(receivers, start=1):
        data[f"receiver_{i}"] = phone
        data[f"receiver_{i}_message"] = json.dumps({
            "#{날짜}": date_str,
            "#{메뉴}": menu_text,
        }, ensure_ascii=False)

    resp = requests.post(
        "https://kakaoapi.aligo.in/brandtalk/template/send/",
        data=data,
    )
    result = resp.json()

    if str(result.get("code")) == "0":
        scnt = result.get("info", {}).get("scnt", 0)
        fcnt = result.get("info", {}).get("fcnt", 0)
        print(f"브랜드메시지 발송 완료: 성공 {scnt}건, 실패 {fcnt}건")
    else:
        print(f"브랜드메시지 발송 실패: {result}")

    return result
