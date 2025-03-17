import time
import re
import requests
import pandas as pd
import numpy as np

from io import StringIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import UnexpectedAlertPresentException, NoAlertPresentException

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

print("DEBUG: RUNNING seleniumcrawling3.py - HEADLESS MODE ENABLED")

WEBHOOK_URL = "https://hooks.slack.com/services/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"  # 실제 웹훅 URL로 교체

try:
    USER_ID = "dyshin"
    USER_PW = "workMR**1201"

    # 1) 인트라넷 로그인
    driver.get("https://mail.mariababy.com/")
    time.sleep(1)
    driver.find_element(By.ID, "txtUserid").send_keys(USER_ID)
    driver.find_element(By.ID, "txtPassword").send_keys(USER_PW)
    driver.find_element(By.ID, "imgLogin").click()
    print("Login submitted")
    time.sleep(2)

    # (이미 로그인된 세션 강제 종료)
    try:
        alert = driver.switch_to.alert
        alert_text = alert.text
        print(f"Alert detected: {alert_text}")
        if "Already logged in another place" in alert_text:
            print("Closing existing session and continuing login...")
            alert.accept()
            time.sleep(2)
    except NoAlertPresentException:
        print("No existing login alert detected, proceeding normally.")

    if "ID 와 비밀번호를 정확히 넣어 주십시오." in driver.page_source:
        print("Login failed.")
        driver.quit()
        exit()
    print("Login successful")

    # 2) 식단표 게시판 이동 -> 최신 글
    driver.get("https://mail.mariababy.com/bbs/bbs_list.aspx?bbs_num=41")
    time.sleep(1)
    latest_post = driver.find_element(By.XPATH, '//a[contains(@href, "read_bbs.aspx")]/span')
    post_title = latest_post.text.strip()
    post_link = latest_post.find_element(By.XPATH, "./..").get_attribute("href")
    print(f"Latest Post: {post_title} | {post_link}")

    driver.get(post_link)
    time.sleep(2)

    # 3) 본문 내 식단표 테이블 추출
    table_elem = driver.find_element(By.CLASS_NAME, "__se_tbl_ext")
    table_html = table_elem.get_attribute("outerHTML")

    # 4) pandas로 파싱
    df_list = pd.read_html(StringIO(table_html), flavor="lxml")
    if not df_list:
        raise ValueError("식단표 테이블을 찾지 못했습니다.")
    df = df_list[0]
    print("DataFrame shape:", df.shape)

    # 5) 하단 안내문(푸터) 제거
    if df.shape[0] > 9:
        df = df.iloc[:-3, :]
    print("After cutting footer:", df.shape)

    # 6) 첫 행 -> 날짜
    header_row = df.iloc[0].tolist()
    dates_raw = header_row[1:]  # 첫 열 제외
    dates = []
    for val in dates_raw:
        if pd.isna(val):
            dates.append("")
        else:
            dates.append(str(val).strip())

    # 메뉴 dict
    menu_dict = {}
    for d in dates:
        if d:
            menu_dict[d] = []

    # 7) 나머지 행 -> 메뉴
    for row_idx in range(1, df.shape[0]):
        row_data = df.iloc[row_idx].tolist()
        for col_idx, date_str in enumerate(dates, start=1):
            if not date_str:
                continue
            if col_idx < len(row_data):
                cell_val = row_data[col_idx]
            else:
                cell_val = np.nan

            if pd.isna(cell_val):
                continue

            cell_text = str(cell_val).strip()
            # 괄호 제거
            cell_text = re.sub(r"\(.*?\)", "", cell_text)
            lines = [ln.strip() for ln in cell_text.split("\n") if ln.strip()]

            for ln in lines:
                menu_dict[date_str].append(ln)

    # 8) 연속된 동일 항목 제거
    for d in menu_dict:
        original_list = menu_dict[d]
        deduplicated_list = []
        for m in original_list:
            if not deduplicated_list or deduplicated_list[-1] != m:
                deduplicated_list.append(m)
        menu_dict[d] = deduplicated_list

    # ------------------- (Block Kit 구성) -------------------
    # "월요일~금요일"만 식단을 표기한다고 가정.
    # dates가 "3/17(월)" ~ "3/23(일)" 등 여러 날짜가 있을 텐데,
    # 여기서는 M-F만 필터링하자.
    # (실제로는 date_str에서 요일을 추출하는 로직이 필요할 수 있음.)

    # 1) 원하는 날짜만 선택
    # 예: "월~금"에 해당하는 문자열만 뽑기 (주의: "3/17(월)" 이런 식으로 나올 거라 가정)
    # 간단히 예시로 "월", "화", "수", "목", "금"이 포함된 날짜만 쓰겠다.
    weekdays = ["(월)", "(화)", "(수)", "(목)", "(금)"]
    filtered_dates = []
    for d in dates:
        # 실제로 d가 "3/17(월)" 이런 식이라고 가정
        if any(day in d for day in weekdays):
            filtered_dates.append(d)

    # 2) 각 날짜별로 (날짜필드, 메뉴필드) 페어 만들기
    fields = []
    for d in filtered_dates:
        # 왼쪽 필드: 날짜 (굵게 표시 => *월요일*)
        left_field = {
            "type": "mrkdwn",
            "text": f"*{d}*"
        }
        # 오른쪽 필드: 메뉴들 줄바꿈
        # e.g. "닭곰탕&다대기\n해물콩나물찜\n..."
        menu_text = "\n".join(menu_dict[d]) if d in menu_dict else "(메뉴 없음)"
        right_field = {
            "type": "mrkdwn",
            "text": menu_text
        }

        fields.append(left_field)
        fields.append(right_field)

    # 3) 이 fields를 한 블록에 담기 (최대 10개까지 가능 => 5일치)
    blocks = [
        {
            "type": "section",
            "fields": fields
        }
    ]

    # 추가로 제목(타이틀) 블록을 하나 넣고 싶다면:
    title_block = {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": post_title,
            "emoji": True
        }
    }
    # 블록 리스트 맨 앞에 제목 블록 추가
    blocks.insert(0, title_block)

    # 최종 payload
    payload = {
        "blocks": blocks
    }

    print("\n===== 최종 Block Kit 메시지 =====\n", payload)

    # 4) 슬랙 전송
    resp = requests.post(WEBHOOK_URL, json=payload)
    if resp.status_code == 200:
        print("Menu data sent to Slack successfully.")
    else:
        print(f"Failed to send Slack message: {resp.status_code}")

finally:
    driver.quit()