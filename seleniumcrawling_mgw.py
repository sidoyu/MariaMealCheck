"""
신 그룹웨어(mgw.mariababy.com)용 식단 크롤러.
2026-04-29 그룹웨어 전환 대비 예비 버전.

기존 seleniumcrawling3.py 대비 변경점:
1. 도메인: mail.mariababy.com → mgw.mariababy.com
2. 로그인 버튼 ID: imgLogin → btnLogin_web
3. 게시글 진입 방식: <a> 클릭 → 행의 ondblclick에서 URL 추출 후 driver.get
4. 본문 파싱(__se_tbl_ext, pandas) 로직은 기존과 동일

전환 절차:
  .github/workflows/schedule.yml 에서
    python seleniumcrawling3.py
  를
    python seleniumcrawling_mgw.py
  로 변경 후 커밋/푸시.
"""
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

HOST = "https://mgw.mariababy.com"

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

print("DEBUG: RUNNING seleniumcrawling_mgw.py - HEADLESS MODE ENABLED")

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

try:
    USER_ID = os.environ.get("MAIL_USER_ID")
    USER_PW = os.environ.get("MAIL_USER_PW")

    driver.get(HOST + "/")
    time.sleep(1)
    driver.find_element(By.ID, "txtUserid").send_keys(USER_ID)
    driver.find_element(By.ID, "txtPassword").send_keys(USER_PW)
    driver.find_element(By.ID, "btnLogin_web").click()
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

    driver.get(HOST + "/bbs/bbs_list.aspx?bbs_num=41")
    time.sleep(1)

    # dglist 테이블의 첫 게시글 행에서 ondblclick 속성 추출 → read_bbs URL
    dglist = driver.find_element(By.ID, "dglist")
    rows = dglist.find_elements(By.TAG_NAME, "tr")
    if len(rows) < 2:
        raise Exception("게시글 없음")

    target_row = rows[1]
    ondbl = target_row.get_attribute("ondblclick") or ""
    match = re.search(r"'(\.\./bbs/read_bbs\.aspx\?[^']+)'", ondbl)
    if not match:
        raise Exception(f"ondblclick에서 URL 추출 실패: {ondbl[:200]}")
    rel_url = match.group(1).replace("\\u0026", "&")
    post_link = HOST + "/" + rel_url.replace("../", "")

    # 게시글 제목 (행의 제목 컬럼 — 5번째 td, 인덱스 4)
    cells = target_row.find_elements(By.TAG_NAME, "td")
    post_title = cells[4].text.strip() if len(cells) >= 5 else "식단표"
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

    # latest_meal.json 저장 (기존 데이터와 병합)
    today = date.today()
    json_dict = {}
    for key in menu_dict:
        try:
            month, day = map(int, re.findall(r"\d+", key)[:2])
            full_date = date(today.year, month, day).strftime("%Y-%m-%d")
            json_dict[full_date] = menu_dict[key]
        except Exception as e:
            print(f"날짜 파싱 오류: {key} → {e}")

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
