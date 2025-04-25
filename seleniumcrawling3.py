import time
import re
import requests
import pandas as pd
import numpy as np
import os

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

# ✅ Slack Webhook URL은 환경변수에서 불러오기
WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")

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

    df_list = pd.read_html(StringIO(table_html), flavor="lxml")
    if not df_list:
        raise ValueError("식단표 테이블을 찾지 못했습니다.")
    df = df_list[0]
    print("DataFrame shape:", df.shape)

    if df.shape[0] > 9:
        df = df.iloc[:-3, :]
    print("After cutting footer:", df.shape)

    header_row = df.iloc[0].tolist()
    dates_raw = header_row[1:]
    dates = [str(val).strip() if not pd.isna(val) else "" for val in dates_raw]

    menu_dict = {d: [] for d in dates if d}

    for row_idx in range(1, df.shape[0]):
        row_data = df.iloc[row_idx].tolist()
        for col_idx, date_str in enumerate(dates, start=1):
            if not date_str:
                continue
            cell_val = row_data[col_idx] if col_idx < len(row_data) else np.nan
            if pd.isna(cell_val):
                continue
            cell_text = str(cell_val).strip()
            cell_text = re.sub(r"\(.*?\)", "", cell_text)
            lines = [ln.strip() for ln in cell_text.split("\n") if ln.strip()]
            menu_dict[date_str].extend(lines)

    for d in menu_dict:
        deduped = []
        for m in menu_dict[d]:
            if not deduped or deduped[-1] != m:
                deduped.append(m)
        menu_dict[d] = deduped

    filtered_dates = [d for d in dates if d in menu_dict]
    blocks = [{
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": post_title,
            "emoji": True
        }
    }]

    for d in filtered_dates:
        left = {"type": "mrkdwn", "text": f"*{d}*"}
        right = {"type": "mrkdwn", "text": "\n".join(menu_dict[d]) or "(메뉴 없음)"}
        blocks.append({"type": "section", "fields": [left, right]})
        blocks.append({"type": "divider"})

    if blocks and blocks[-1]["type"] == "divider":
        blocks.pop()

    payload = {"blocks": blocks}
    print("\n===== 최종 Block Kit 메시지 =====\n", payload)

    resp = requests.post(WEBHOOK_URL, json=payload)
    if resp.status_code == 200:
        print("✅ Slack 메시지 전송 성공")
    else:
        print(f"❌ Slack 메시지 전송 실패: {resp.status_code}")

finally:
    driver.quit()
