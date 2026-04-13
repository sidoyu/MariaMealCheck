/**
 * 식단 알림톡 구독자 관리 Apps Script
 * Google Sheets를 DB로 사용, Cloudflare Workers 및 kakao_meal.py에서 호출
 *
 * 시트 구조 (시트명: subscribers)
 * A: 전화번호 (01012345678 형식)
 * B: 구독일시
 *
 * 엔드포인트:
 * GET  ?action=list          → 활성 구독자 목록 반환
 * POST ?action=subscribe     → 구독 신청
 * POST ?action=unsubscribe   → 구독 해지
 */

const SHEET_NAME = "subscribers";

/** Script Property "SHARED_SECRET" 와 일치 여부 검증 */
function verifySecret(e) {
  const expected = PropertiesService.getScriptProperties().getProperty("SHARED_SECRET");
  if (!expected) return false; // secret 미설정이면 모두 차단
  return e.parameter.secret === expected;
}

function doGet(e) {
  if (!verifySecret(e)) {
    return jsonResponse({ error: "unauthorized" });
  }

  const action = e.parameter.action;
  const phone = normalizePhone(e.parameter.phone || "");

  if (action === "list") {
    return jsonResponse(getActiveSubscribers());
  }
  if (action === "subscribe" || action === "unsubscribe") {
    if (!phone) return jsonResponse({ error: "invalid_phone", message: "유효하지 않은 전화번호입니다." });
    if (action === "subscribe") return jsonResponse(subscribe(phone));
    if (action === "unsubscribe") return jsonResponse(unsubscribe(phone));
  }
  return jsonResponse({ error: "invalid action" });
}

function doPost(e) {
  const params = JSON.parse(e.postData.contents);
  return doGet({ parameter: params });
}

/** 전화번호 정규화: 010-1234-5678, 1012345678, 01012345678 → 01012345678 */
function normalizePhone(raw) {
  const digits = raw.replace(/[^0-9]/g, "");
  if (digits.length === 10 && digits.startsWith("10")) {
    return "0" + digits;
  }
  if (digits.length === 11 && digits.startsWith("010")) {
    return digits;
  }
  return null;
}

/** 셀 값에서 전화번호 읽기 (0 보정) */
function readPhone(val) {
  let p = String(val);
  if (p.length === 10 && p.startsWith("10")) p = "0" + p;
  return p;
}

/** 구독 신청 */
function subscribe(phone) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    if (readPhone(data[i][0]) === phone) {
      return { status: "already_subscribed", message: "이미 구독 중이시네요!" };
    }
  }

  const newRow = sheet.getLastRow() + 1;
  sheet.getRange(newRow, 1).setNumberFormat("@").setValue(phone);
  sheet.getRange(newRow, 2).setValue(new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }));
  const count = sheet.getLastRow() - 1;
  sendSlack("*:large_green_circle: 식단 알림 구독자 추가*\n현재 총 *`" + count + "명`* 구독 중");
  return { status: "subscribed", message: "구독이 완료되었습니다!" };
}

/** 구독 해지 */
function unsubscribe(phone) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    if (readPhone(data[i][0]) === phone) {
      sheet.deleteRow(i + 1);
      const count = sheet.getLastRow() - 1;
      sendSlack("*:red_circle: 식단 알림 구독자 해지*\n현재 총 *`" + count + "명`* 구독 중");
      return { status: "unsubscribed", message: "구독이 해지되었습니다." };
    }
  }

  return { status: "not_found", message: "이미 해지 처리된 번호입니다." };
}

/** 활성 구독자 목록 */
function getActiveSubscribers() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();
  const subscribers = [];

  for (let i = 1; i < data.length; i++) {
    subscribers.push(readPhone(data[i][0]));
  }

  return { subscribers: subscribers, count: subscribers.length };
}

/** Slack 알림 — Script Property "SLACK_WEBHOOK_URL" 사용 */
function sendSlack(text) {
  const url = PropertiesService.getScriptProperties().getProperty("SLACK_WEBHOOK_URL");
  if (!url) return;
  try {
    UrlFetchApp.fetch(url, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ text: text })
    });
  } catch (e) {
    // Slack 실패해도 구독 처리는 정상 진행
  }
}

/** JSON 응답 헬퍼 */
function jsonResponse(data, code) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * 초기 설정: 시트 헤더 생성 (최초 1회 실행)
 */
function initSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
  }
  sheet.getRange(1, 1, 1, 2).setValues([["전화번호", "구독일시"]]);

  const existing = [
    "01020241731", "01052297713", "01063185542", "01089194740", "01088348475",
    "01089474990", "01035804568", "01030082911", "01087864824", "01042477610"
  ];
  const now = new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
  for (let i = 0; i < existing.length; i++) {
    const row = i + 2;
    sheet.getRange(row, 1).setNumberFormat("@").setValue(existing[i]);
    sheet.getRange(row, 2).setValue(now);
  }
}
