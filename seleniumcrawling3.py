import time
import re
import requests
import pandas as pd
import numpy as np
import datetime
import json

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

# Slack Webhook URL
WEBHOOK_URL = "https://hooks.slack.com/services/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"

try:
    USER_ID = "dyshin"
    USER_PW = "workMR**1201"

    driver.get("https://mail.mariababy.com/")
    time.sleep(1)
    driver.find_element(By.ID, "txtUserid").send_keys(USER_ID)
    driver.find_element(By.ID, "txtPassword").send_keys(USER_PW)
    driver.find_element(By.ID, "imgLogin").click()
    print("Login submitted")
    time.sleep(2)

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

    # 게시판 이동 → 최신 글
    driver.get("https://mail.mariababy.com/bbs/bbs_list.aspx?bbs_num=41")
    time.sleep(1)
    latest_post = driver.find_element(By.XPATH, '//a[contains(@href, "read_bbs.aspx")]/span')
    post_title = latest_post.text.strip()
    post_link = latest_post.find_element(By.XPATH, "./..").get_attribute("href")
    print(f"Latest Post: {post_title} | {post_link}")

    driver.get(post_link)
    time.sleep(2)

    # 식단표 테이블 추출
    table_elem = driver.find_element(By.CLASS_NAME, "__se_tbl_ext")
    table_html = table_elem.get_attribute("outerHTML")

    # pandas로 파싱
    df_list = pd.read_html(StringIO(table_html), flavor="lxml")
    if not df_list:
        raise ValueError("식단표 테이블을 찾지 못했습니다.")
    df = df_list[0]
    print("DataFrame shape:", df.shape)

    if df.shape[0] > 9:
        df = df.iloc[:-3, :]
    print("After cutting footer:", df.shape)

    # 날짜 추출
    header_row = df.iloc[0].tolist()
    dates_raw = header_row[1:]
    dates = []
    for val in dates_raw:
        if pd.isna(val):
            dates.append("")
        else:
            dates.append(str(val).strip())

    # 식단 저장용 dict
    menu_dict = {}
    for d in dates:
        if d:
            menu_dict[d] = []

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
            cell_text = re.sub(r"\(.*?\)", "", cell_text)
            lines = [ln.strip() for ln in cell_text.split("\n") if ln.strip()]
            for ln in lines:
                menu_dict[date_str].append(ln)

    # 중복 제거
    for d in menu_dict:
        original_list = menu_dict[d]
        deduplicated_list = []
        for m in original_list:
            if not deduplicated_list or deduplicated_list[-1] != m:
                deduplicated_list.append(m)
        menu_dict[d] = deduplicated_list

    # ✅ JSON 저장용 형태로 변환
    today = datetime.date.today()
    meal_json = {}

    for d in menu_dict:
        try:
            month_day = d.split("(")[0]  # "3/25"
            month, day = month_day.split("/")
            full_date = datetime.date(today.year, int(month), int(day)).strftime("%Y-%m-%d")
            meal_json[full_date] = menu_dict[d]
        except Exception as e:
            print(f"날짜 파싱 오류: {d} → {e}")

    # ✅ JSON 파일로 저장
    with open("latest_meal.json", "w", encoding="utf-8") as f:
        json.dump(meal_json, f, ensure_ascii=False, indent=2)
    print("✅ latest_meal.json 파일 저장 완료")

    # ✅ 슬랙 메시지(Block Kit Divider)
    filtered_dates = [d for d in dates if d in menu_dict]
    blocks = []

    title_block = {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": post_title,
            "emoji": True
        }
    }
    blocks.append(title_block)

    for d in filtered_dates:
        left_field = {
            "type": "mrkdwn",
            "text": f"*{d}*"
        }
        menu_text = "\n".join(menu_dict[d]) if d in menu_dict else "(메뉴 없음)"
        right_field = {
            "type": "mrkdwn",
            "text": menu_text
        }

        day_block = {
            "type": "section",
            "fields": [left_field, right_field]
        }
        blocks.append(day_block)
        blocks.append({"type": "divider"})

    if blocks and blocks[-1]["type"] == "divider":
        blocks.pop()

    payload = {
        "blocks": blocks
    }

    print("\n===== 최종 Slack 메시지 Payload =====\n", payload)

    resp = requests.post(WEBHOOK_URL, json=payload)
    if resp.status_code == 200:
        print("✅ Slack 메시지 전송 성공")
    else:
        print(f"Slack 메시지 전송 실패: {resp.status_code}")

finally:
    driver.quit()
