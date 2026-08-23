/**
 * Apps Script bridge for Sheet writeback (optional, if no Service Account).
 *
 * Setup:
 * 1. Open the Google Sheet → Extensions → Apps Script
 * 2. Paste this file, set WRITE_TOKEN to the same value as SHEETS_WEBHOOK_TOKEN / WEBHOOK_TOKEN
 * 3. Deploy → New deployment → Web app
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 4. Put the /exec URL into campaign .env:
 *    SHEETS_WEBHOOK_URL=https://script.google.com/macros/s/.../exec
 *    SHEETS_WEBHOOK_TOKEN=<same token>
 */

var WRITE_TOKEN = "mailru-secret-123";
var NOTE_HEADER = "Пометки Клиента";
var TRANSCRIPT_HEADER = "Транскрибация";
var STATUS_HEADER = "Статус (IVR=Положительный)";

function doPost(e) {
  try {
    var data = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    if (WRITE_TOKEN && data.token !== WRITE_TOKEN) {
      return _json({ ok: false, error: "unauthorized" });
    }
    var ss = SpreadsheetApp.openById(String(data.sheet_id || ""));
    var sheet =
      ss.getSheetByName(String(data.sheet_name || "")) ||
      ss.getSheets().filter(function (s) {
        return String(s.getSheetId()) === String(data.gid || "");
      })[0];
    if (!sheet) return _json({ ok: false, error: "sheet_not_found" });
    var row = Number(data.row || 0);
    if (!(row >= 2)) return _json({ ok: false, error: "bad_row" });
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    function col(name) {
      for (var i = 0; i < headers.length; i++) {
        if (String(headers[i] || "").trim() === name) return i + 1;
      }
      return 0;
    }
    var updated = [];
    function set(name, value) {
      var c = col(name);
      if (!c || !value) return;
      sheet.getRange(row, c).setValue(value);
      updated.push(name);
    }
    set(NOTE_HEADER, data.note || "");
    set(TRANSCRIPT_HEADER, data.transcript || "");
    set(STATUS_HEADER, data.status || "");
    return _json({ ok: true, updated: updated, row: row, phone: data.phone || "" });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function _json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(
    ContentService.MimeType.JSON
  );
}
