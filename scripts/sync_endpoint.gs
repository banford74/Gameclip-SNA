/**
 * Gameclip-SNA 标注同步端点（Google Apps Script）
 *
 * 部署方法：
 *  1. 打开 https://script.google.com → 新建项目 → 粘贴本文件 → 保存
 *  2. 部署 → 新建部署 → 类型「Web 应用」
 *     执行身份：我（Me）
 *     访问权限：任何人（Anyone）
 *  3. 复制 Web 应用 URL（https://script.google.com/macros/s/.../exec）
 *  4. 发给标注员：打开标注页 → 底部「同步地址」粘贴一次（存浏览器），
 *     或直接发 https://banford74.github.io/Gameclip-SNA/?a=2&sync=<URL> 这样的链接
 *
 * 标注页每次保存（防抖 1.2s）会把该标注员的全量标注 POST 过来（text/plain，no-cors）。
 * 本脚本写入「labels」工作表，按 (annotator, clip_id) 去重更新。
 *
 * 进度汇总页读取方式：文件 → 共享 → 发布到网络 → 选「labels」工作表、格式 CSV → 复制链接，
 * 打开 https://banford74.github.io/Gameclip-SNA/progress.html?data=<CSV链接>，每 20 秒自动刷新。
 */
function doPost(e) {
  var body = JSON.parse(e.postData.contents);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('labels');
  if (!sh) sh = ss.insertSheet('labels');
  var HEAD = ['annotator', 'clip_id', 'stance', 'intensity', 'p_codes', 'r_codes',
              'evidence', 'confidence', 'notes', 'annotated_at'];
  if (sh.getLastRow() === 0) sh.appendRow(HEAD);

  // 现有 (annotator, clip_id) → 行号
  var last = sh.getLastRow();
  var existing = {};
  if (last > 1) {
    var data = sh.getRange(2, 1, last - 1, 2).getValues();
    for (var i = 0; i < data.length; i++) existing[data[i][0] + '|' + data[i][1]] = i + 2;
  }

  var annotator = String(body.annotator);
  var labels = body.labels || {};
  var updates = [];
  var appends = [];
  for (var cid in labels) {
    var r = labels[cid] || {};
    var row = [annotator, cid, r.stance || '', r.intensity || '', r.p_codes || '',
               r.r_codes || '', r.evidence || '', r.confidence || '', r.notes || '',
               r.annotated_at || ''];
    var key = annotator + '|' + cid;
    if (existing[key]) updates.push({ row: existing[key], vals: row });
    else appends.push(row);
  }
  updates.forEach(function (u) { sh.getRange(u.row, 1, 1, HEAD.length).setValues([u.vals]); });
  if (appends.length) sh.getRange(sh.getLastRow() + 1, 1, appends.length, HEAD.length).setValues(appends);

  return ContentService.createTextOutput(JSON.stringify({ ok: true, updated: updates.length, appended: appends.length }))
    .setMimeType(ContentService.MimeType.JSON);
}
