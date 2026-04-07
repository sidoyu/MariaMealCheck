"""
카카오톡 식단 알림 전용 스크립트 (Mac Mini crontab용).
오늘 날짜의 식단만 크롤링하여 브랜드메시지로 발송.
"""

import time
import re
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

from io import StringIO
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoAlertPresentException

from kakao_send import send_brandtalk

options = Options()
options.add_argument("--headless")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

try:
    USER_ID = os.environ.get("MAIL_USER_ID")
    USER_PW = os.environ.get("MAIL_USER_PW")

    driver.get("https://mail.mariababy.com/")
    time.sleep(1)
    driver.find_element(By.ID, "txtUserid").send_keys(USER_ID)
    driver.find_element(By.ID, "txtPassword").send_keys(USER_PW)
    driver.find_element(By.ID, "imgLogin").click()
    time.sleep(2)

    try:
        alert = driver.switch_to.alert
        print(f"Alert detected: {alert.text}")
        alert.accept()
        time.sleep(2)
    except NoAlertPresentException:
        pass

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
    print(f"Latest Post: {post_title}")

    driver.get(post_link)
    time.sleep(2)

    table_elem = driver.find_element(By.CLASS_NAME, "__se_tbl_ext")
    table_html = table_elem.get_attribute("outerHTML")

    df = pd.read_html(StringIO(table_html), flavor="lxml")[0]
    if df.shape[0] > 9:
        df = df.iloc[:-3, :]

    header_row = df.iloc[0].tolist()
    dates = [str(val).strip() if not pd.isna(val) else "" for val in header_row[1:]]
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

    # 오늘 날짜 매칭
    today_str = datetime.now().strftime("%-m/%-d")
    today_menu = None
    today_date_key = None

    for d in menu_dict:
        if today_str in d:
            today_date_key = d
            today_menu = menu_dict.get(d, [])
            break

    if today_menu:
        menu_text = "\n".join(today_menu)
        print(f"\n===== 브랜드메시지 발송 ({today_date_key}) =====")
        print(menu_text)
        send_brandtalk(today_date_key, menu_text)
    else:
        print(f"\n오늘({today_str}) 식단 정보가 없습니다. 발송 생략.")

finally:
    driver.quit()
