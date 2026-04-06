"""
알리고 알림톡 API를 통한 카카오톡 식단 알림 발송 모듈.
"""

import os
import requests

ALIGO_API_KEY = os.environ.get("ALIGO_API_KEY", "7k7x7th7425mdzj10hsdbz7ckloyogpg")
ALIGO_USER_ID = os.environ.get("ALIGO_USER_ID", "sidoyu")
ALIGO_SENDER_KEY = os.environ.get("ALIGO_SENDER_KEY", "1ad86f2ec6662a73514aba2de3a51e2909527962")
ALIGO_SENDER = os.environ.get("ALIGO_SENDER", "01020241731")
TEMPLATE_CODE = "UG_7783"

# 수신자 전화번호 목록 (동료 추가 시 여기에 번호 추가)
RECEIVERS = os.environ.get("ALIGO_RECEIVERS", "").split(",")
# 예: ALIGO_RECEIVERS="01012345678,01087654321,..."


def send_alimtalk(title, date_str, menu_text):
    """등록된 모든 수신자에게 알림톡 발송"""
    receivers = [r.strip() for r in RECEIVERS if r.strip()]
    if not receivers:
        print("등록된 수신자가 없습니다.")
        return

    data = {
        "apikey": ALIGO_API_KEY,
        "userid": ALIGO_USER_ID,
        "senderkey": ALIGO_SENDER_KEY,
        "tpl_code": TEMPLATE_CODE,
        "sender": ALIGO_SENDER,
    }

    message_content = f"[{title}]\n\n{date_str}\n\n{menu_text}"

    for i, phone in enumerate(receivers, start=1):
        data[f"receiver_{i}"] = phone
        data[f"subject_{i}"] = "식단 알림"
        data[f"message_{i}"] = message_content

    resp = requests.post(
        "https://kakaoapi.aligo.in/akv10/alimtalk/send/",
        data=data,
    )
    result = resp.json()

    if str(result.get("code")) == "0":
        scnt = result.get("info", {}).get("scnt", 0)
        fcnt = result.get("info", {}).get("fcnt", 0)
        print(f"알림톡 발송 완료: 성공 {scnt}건, 실패 {fcnt}건")
    else:
        print(f"알림톡 발송 실패: {result}")

    return result
