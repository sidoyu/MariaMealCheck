import time
import re
import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, date

from io import StringIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoAlertPresentException

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

print("DEBUG: RUNNING seleniumcrawling3.py - HEADLESS MODE ENABLED")

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

try:
    USER_ID = os.environ.get("MAIL_USER_ID")
    USER_PW = os.environ.get("MAIL_USER_PW")

    driver.get("https://mail.mariababy.com/")
    time.sleep(1)
    driver.find_element(By.ID, "txtUserid").send_keys(USER_ID)
    driver.find_element(By.ID, "txtPassword").send_keys(USER_PW)
    driver.find_element(By.ID, "imgLogin").click()
    print("Login submitted")
    time.sleep(2)

    try:
        alert = driver.switch_to.alert
        print(f"Alert detected: {alert.text}")
        alert.accept()
        time.sleep(2)
    except NoAlertPresentException:
        print("No existing login alert detected.")

    if "ID 와 비밀번호를 정확히 넣어 주십시오." in driver.page_source:
        print("Login failed.")
        driver.quit()
        exit()
    print("Login successful")

    driver.get("https://mail.mariababy.com/bbs/bbs_list.aspx?bbs_num=41")
    time.sleep(1)
    latest_post = driver.find_element(By.XPATH, '//a[contains(@href, "read_bbs.aspx")]/span')
    post_title = latest_post.text.strip()
    post_link = latest_post.find_element(By.XPATH, "./..").get_attribute("href")
    print(f"Latest Post: {post_title} | {post_link}")

    driver.get(post_link)
    time.sleep(2)

    table_elem = driver.find_element(By.CLASS_NAME, "__se_tbl_ext")
    table_html = table_elem.get_attribute("outerHTML")

    df = pd.read_html(StringIO(table_html), flavor="lxml")[0]
    if df.shape[0] > 9:
        df = df.iloc[:-3, :]
    header_row = df.iloc[0].tolist()
    dates_raw = header_row[1:]
    dates = [str(val).strip() if not pd.isna(val) else "" for val in dates_raw]
    menu_dict = {d: [] for d in dates if d}

    for row_idx in range(1, df.shape[0]):
        row = df.iloc[row_idx].tolist()
        for col_idx, date_str in enumerate(dates, start=1):
            if date_str and col_idx < len(row) and not pd.isna(row[col_idx]):
                cell_text = str(row[col_idx]).strip()
                cell_text = re.sub(r"\(.*?\)", "", cell_text)
                lines = [ln.strip() for ln in cell_text.split("\n") if ln.strip()]
                menu_dict[date_str].extend(lines)

    for d in menu_dict:
        menu_dict[d] = [m for i, m in enumerate(menu_dict[d]) if i == 0 or m != menu_dict[d][i - 1]]

    # latest_meal.json 저장
    today = date.today()
    json_dict = {}
    for key in menu_dict:
        try:
            month, day = map(int, re.findall(r"\d+", key)[:2])
            full_date = date(today.year, month, day).strftime("%Y-%m-%d")
            json_dict[full_date] = menu_dict[key]
        except Exception as e:
            print(f"날짜 파싱 오류: {key} → {e}")
    # 기존 데이터와 병합 (다음 주 메뉴 크롤 시 이번 주 데이터 보존)
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_meal.json")
    existing = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    merged = {**existing, **json_dict}
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"latest_meal.json 저장 완료 (기존 {len(existing)}건 + 신규 {len(json_dict)}건 → 총 {len(merged)}건)")

    # Slack 전송 (Block Kit)
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": post_title, "emoji": True}}]
    for d in dates:
        if d in menu_dict:
            blocks.append({
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{d}*"},
                    {"type": "mrkdwn", "text": "\n".join(menu_dict[d])}
                ]
            })
            blocks.append({"type": "divider"})
    if blocks[-1]["type"] == "divider":
        blocks.pop()

    if WEBHOOK_URL:
        payload = {"blocks": blocks}
        resp = requests.post(WEBHOOK_URL, json=payload)
        if resp.status_code == 200:
            print("Slack 메시지 전송 성공")
        else:
            print(f"Slack 메시지 전송 실패: {resp.status_code}")
    else:
        print("SLACK_WEBHOOK_URL 미설정, Slack 전송 생략")

finally:
    driver.quit()
