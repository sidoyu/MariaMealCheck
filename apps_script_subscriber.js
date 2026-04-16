/**
 * 식단 알림톡 구독자 관리 Apps Script
 * Google Sheets를 DB로 사용, Cloudflare Workers 및 kakao_meal.py에서 호출
 *
 * 시트 구조 (시트명: subscribers)
 * A: 전화번호 (01012345678 형식)
 * B: 구독일시
 * C: 알림시간 (HH:MM 형식, 기본값 "11:30")
 *
 * 엔드포인트:
 * GET  ?action=list           → 활성 구독자 목록 반환 (시간 포함)
 * GET  ?action=subscribe      → 구독 신청 (time 파라미터 optional, 기본 "11:30")
 * GET  ?action=unsubscribe    → 구독 해지
 * GET  ?action=update_time    → 알림 시간 변경
 * GET  ?action=check          → 구독 여부 확인 (시간변경 페이지용)
 */

const SHEET_NAME = "subscribers";
const DEFAULT_TIME = "11:30";
const VALID_TIMES = [
  "08:00","08:30","09:00","09:30","10:00","10:30",
  "11:00","11:30","12:00","12:30","13:00"
];

/** Script Property "SHARED_SECRET" 와 일치 여부 검증 */
function verifySecret(e) {
  const expected = PropertiesService.getScriptProperties().getProperty("SHARED_SECRET");
  if (!expected) return false;
  return e.parameter.secret === expected;
}

function doGet(e) {
  if (!verifySecret(e)) {
    return jsonResponse({ error: "unauthorized" });
  }

  const action = e.parameter.action;
  const phone = normalizePhone(e.parameter.phone || "");
  const time = e.parameter.time || DEFAULT_TIME;

  if (action === "list") {
    return jsonResponse(getActiveSubscribers());
  }
  if (action === "check") {
    if (!phone) return jsonResponse({ error: "invalid_phone", message: "유효하지 않은 전화번호입니다." });
    return jsonResponse(checkSubscriber(phone));
  }
  if (action === "subscribe") {
    if (!phone) return jsonResponse({ error: "invalid_phone", message: "유효하지 않은 전화번호입니다." });
    return jsonResponse(subscribe(phone, time));
  }
  if (action === "unsubscribe") {
    if (!phone) return jsonResponse({ error: "invalid_phone", message: "유효하지 않은 전화번호입니다." });
    return jsonResponse(unsubscribe(phone));
  }
  if (action === "update_time") {
    if (!phone) return jsonResponse({ error: "invalid_phone", message: "유효하지 않은 전화번호입니다." });
    return jsonResponse(updateTime(phone, time));
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

/** 알림 시간 유효성 검증 */
function validateTime(time) {
  return VALID_TIMES.includes(time);
}

/** 셀 값에서 전화번호 읽기 (0 보정) */
function readPhone(val) {
  let p = String(val);
  if (p.length === 10 && p.startsWith("10")) p = "0" + p;
  return p;
}

/** 셀 값에서 알림시간 읽기 (Date 객체 대응 — Sheets가 "11:30"을 Time으로 자동 변환하는 문제) */
function readTime(val) {
  if (!val) return DEFAULT_TIME;
  if (val instanceof Date) {
    const h = String(val.getHours()).padStart(2, "0");
    const m = String(val.getMinutes()).padStart(2, "0");
    const t = h + ":" + m;
    return VALID_TIMES.includes(t) ? t : DEFAULT_TIME;
  }
  const t = String(val).trim();
  return VALID_TIMES.includes(t) ? t : DEFAULT_TIME;
}

/** 구독 신청. 이미 구독 중이면 시간이 다를 경우 자동 변경 */
function subscribe(phone, time) {
  if (!validateTime(time)) time = DEFAULT_TIME;

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    if (readPhone(data[i][0]) === phone) {
      var currentTime = readTime(data[i][2]);
      if (currentTime !== time) {
        sheet.getRange(i + 1, 3).setNumberFormat("@").setValue(time);
        return { status: "time_updated", message: "알림 시간이 " + time + "으로 변경되었습니다!", time: time };
      }
      return { status: "already_subscribed", message: "이미 구독 중이시네요!" };
    }
  }

  const newRow = sheet.getLastRow() + 1;
  sheet.getRange(newRow, 1).setNumberFormat("@").setValue(phone);
  sheet.getRange(newRow, 2).setValue(new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }));
  sheet.getRange(newRow, 3).setNumberFormat("@").setValue(time);
  const count = sheet.getLastRow() - 1;
  return { status: "subscribed", message: "구독이 완료되었습니다!", count: count, time: time };
}

/** 구독 해지 */
function unsubscribe(phone) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    if (readPhone(data[i][0]) === phone) {
      sheet.deleteRow(i + 1);
      const count = sheet.getLastRow() - 1;
      return { status: "unsubscribed", message: "구독이 해지되었습니다.", count: count };
    }
  }

  return { status: "not_found", message: "이미 해지 처리된 번호입니다." };
}

/** 알림 시간 변경 */
function updateTime(phone, time) {
  if (!validateTime(time)) {
    return { error: "invalid_time", message: "유효하지 않은 알림 시간입니다." };
  }

  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    if (readPhone(data[i][0]) === phone) {
      sheet.getRange(i + 1, 3).setNumberFormat("@").setValue(time);
      return { status: "time_updated", message: "알림 시간이 변경되었습니다!", time: time };
    }
  }

  return { status: "not_subscribed", message: "구독 중인 번호가 아닙니다. 먼저 구독 신청을 해주세요!" };
}

/** 구독 여부 확인 (시간변경 페이지에서 사용) */
function checkSubscriber(phone) {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();

  for (let i = 1; i < data.length; i++) {
    if (readPhone(data[i][0]) === phone) {
      return { status: "subscribed", time: readTime(data[i][2]) };
    }
  }

  return { status: "not_subscribed" };
}

/** 활성 구독자 목록 (하위호환: subscribers 배열 + 상세: subscribers_detail) */
function getActiveSubscribers() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  const data = sheet.getDataRange().getValues();
  const subscribers = [];
  const detail = [];

  for (let i = 1; i < data.length; i++) {
    const phone = readPhone(data[i][0]);
    const time = readTime(data[i][2]);
    subscribers.push(phone);
    detail.push({ phone: phone, time: time });
  }

  return { subscribers: subscribers, subscribers_detail: detail, count: subscribers.length };
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
 * 마이그레이션: C열 "알림시간" 추가 + 기존 구독자에 기본값 "11:30" 세팅
 * Apps Script 편집기에서 수동 1회 실행
 */
function migrateAddTimeColumn() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);

  // C1에 헤더 추가
  sheet.getRange(1, 3).setValue("알림시간");

  // 기존 구독자에 기본값 세팅 (C열이 비어있는 행만)
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    Logger.log("구독자 없음. 마이그레이션 완료.");
    return;
  }

  const timeCol = sheet.getRange(2, 3, lastRow - 1, 1).getValues();
  let updated = 0;
  for (let i = 0; i < timeCol.length; i++) {
    if (!timeCol[i][0] || String(timeCol[i][0]).trim() === "") {
      sheet.getRange(i + 2, 3).setNumberFormat("@").setValue(DEFAULT_TIME);
      updated++;
    }
  }

  Logger.log("마이그레이션 완료: " + updated + "명에 기본값 '" + DEFAULT_TIME + "' 세팅");
}
