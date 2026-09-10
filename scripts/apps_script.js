/**
 * Google Sheets에 최신 로또 당첨번호를 자동 추가하는 Apps Script
 *
 * 사용법:
 * 1. Google Sheets → 확장 프로그램 → Apps Script
 * 2. 이 코드 붙여넣기
 * 3. setupTrigger() 한 번 실행 → 매주 일요일 오전 9시 자동 실행
 */

const SHEET_NAME = 'Sheet1';  // 실제 시트 이름으로 변경

function fetchLatestLotto() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
  if (!sheet) {
    Logger.log('시트를 찾을 수 없습니다: ' + SHEET_NAME);
    return;
  }

  const lastRow = sheet.getLastRow();
  const lastDraw = sheet.getRange(lastRow, 1).getValue();
  const nextDraw = Number(lastDraw) + 1;

  Logger.log(`마지막 회차: ${lastDraw} → 다음 회차: ${nextDraw}`);

  const url = `https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo=${nextDraw}`;

  try {
    const response = UrlFetchApp.fetch(url, {muteHttpExceptions: true});
    const data = JSON.parse(response.getContentText());

    if (data.returnValue === 'success') {
      sheet.appendRow([
        data.drwNo, data.drwNoDate,
        data.drwtNo1, data.drwtNo2, data.drwtNo3,
        data.drwtNo4, data.drwtNo5, data.drwtNo6,
        data.bnusNo
      ]);
      Logger.log(`${data.drwNo}회차 추가 완료`);
    } else {
      Logger.log('아직 추첨되지 않았습니다: ' + data.returnValue);
    }
  } catch (e) {
    Logger.log('오류: ' + e.message);
  }
}

function setupTrigger() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('fetchLatestLotto')
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.SUNDAY)
    .atHour(9)
    .create();
  Logger.log('트리거 설정 완료: 매주 일요일 오전 9시');
}

function manualFetch() {
  fetchLatestLotto();
}