"""
카카오톡 식단 알림 전용 스크립트 (Mac Mini crontab용).
latest_meal.json에서 오늘 날짜의 식단을 찾아 알림톡으로 발송.
"""

import json
import os
import subprocess
import sys
import requests
from datetime import datetime

from kakao_send import send_alimtalk

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "https://script.google.com/macros/s/AKfycbxD8lBmeVQHUYA2lGRz8bHeGUdx4zXFmCBzbX_cnjtv0Ao9YViNr_p0sAQAf_fplJdPzg/exec")
APPS_SCRIPT_SECRET = os.environ.get("APPS_SCRIPT_SECRET", "")
MEAL_JSON_PATH = os.path.join(os.path.dirname(__file__), "latest_meal.json")


def get_subscribers_for_now():
    """현재 시각에 해당하는 구독자만 필터하여 반환. 실패 시 환경변수 폴백 (11:30 슬롯만)."""
    now = datetime.now()
    current_slot = f"{now.hour:02d}:{now.minute // 30 * 30:02d}"

    if APPS_SCRIPT_URL:
        try:
            params = {"action": "list"}
            if APPS_SCRIPT_SECRET:
                params["secret"] = APPS_SCRIPT_SECRET
            resp = requests.get(APPS_SCRIPT_URL, params=params, timeout=10)
            data = resp.json()

            if data.get("error") == "unauthorized":
                print("구독자 목록 조회 실패: secret 인증 오류")
            else:
                detail = data.get("subscribers_detail", [])
                total = data.get("count", len(detail))
                matched = [s["phone"] for s in detail if s.get("time", "11:30") == current_slot]
                print(f"구독자 총 {total}명 중 {current_slot} 슬롯 {len(matched)}명 발송 대상")
                return matched
        except Exception as e:
            print(f"구독자 목록 조회 실패, 환경변수 폴백: {e}")

    # 폴백: 11:30 슬롯에서만 환경변수 수신자로 발송
    if current_slot == "11:30":
        fallback = os.environ.get("ALIGO_RECEIVERS", "")
        receivers = [r.strip() for r in fallback.split(",") if r.strip()]
        print(f"구독자 {len(receivers)}명 로드 (환경변수 폴백, 11:30 슬롯)")
        return receivers

    print(f"폴백 모드에서 {current_slot} 슬롯은 발송 대상 없음")
    return []


def get_today_menu():
    """latest_meal.json에서 오늘 식단 가져오기."""
    if not os.path.exists(MEAL_JSON_PATH):
        print(f"식단 파일이 없습니다: {MEAL_JSON_PATH}")
        return None, None

    with open(MEAL_JSON_PATH, "r", encoding="utf-8") as f:
        meal_data = json.load(f)

    today_key = datetime.now().strftime("%Y-%m-%d")
    today_display = datetime.now().strftime("%-m/%-d") + "(" + "월화수목금토일"[datetime.now().weekday()] + ")"

    if today_key in meal_data:
        return today_display, meal_data[today_key]

    print(f"오늘({today_key}) 식단 정보가 없습니다.")
    return None, None


def try_crawl_fallback():
    """오늘 데이터가 없을 때 즉석 크롤링 재시도 + GitHub에 push (Worker 동기화)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("오늘 식단 데이터 없음 → 즉석 크롤링 재시도")
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(script_dir, "seleniumcrawling_mgw.py")],
            cwd=script_dir,
            capture_output=True, text=True, timeout=180,
        )
        if result.stdout:
            print(result.stdout[-800:])
        if result.returncode != 0 and result.stderr:
            print(f"[crawl stderr] {result.stderr[-500:]}")
    except Exception as e:
        print(f"크롤링 재시도 오류: {e}")
        return

    # 크롤링 결과를 GitHub에 push (Cloudflare Worker /menu 페이지 동기화)
    try:
        subprocess.run(["git", "-C", script_dir, "add", "latest_meal.json"], check=False, timeout=10)
        commit = subprocess.run(
            ["git", "-C", script_dir, "commit", "-m", f"🤖 폴백 크롤링 자동 커밋 ({datetime.now().strftime('%Y-%m-%d %H:%M')})"],
            capture_output=True, text=True, timeout=15,
        )
        if commit.returncode == 0:
            push = subprocess.run(
                ["git", "-C", script_dir, "push", "origin", "main"],
                capture_output=True, text=True, timeout=30,
            )
            if push.returncode == 0:
                print("GitHub push 성공 (Worker 동기화)")
            else:
                print(f"GitHub push 실패: {push.stderr[-300:]}")
        else:
            print(f"[git commit] {commit.stdout[-200:]} {commit.stderr[-200:]}")
    except Exception as e:
        print(f"git push 오류: {e}")


def notify_failure_slack():
    slack = os.environ.get("SLACK_WEBHOOK_URL")
    if not slack:
        return
    try:
        requests.post(
            slack,
            json={"text": f":warning: 식단 알림 발송 실패: {datetime.now().strftime('%Y-%m-%d')} 데이터 확보 불가"},
            timeout=5,
        )
    except Exception:
        pass


if __name__ == "__main__":
    date_str, menu_list = get_today_menu()

    if not menu_list:
        try_crawl_fallback()
        date_str, menu_list = get_today_menu()

    if menu_list:
        menu_text = "\n".join(menu_list)
        subscribers = get_subscribers_for_now()
        if not subscribers:
            print(f"현재 슬롯에 발송 대상 없음 — 생략")
        else:
            print(f"\n===== 알림톡 발송 ({date_str}, {len(subscribers)}명) =====")
            print(menu_text)
            send_alimtalk(date_str, menu_text, receivers=subscribers)
    else:
        print("발송 생략 — 오늘 데이터 확보 실패")
        notify_failure_slack()
