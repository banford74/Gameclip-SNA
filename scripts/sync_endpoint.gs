/**
 * Gameclip-SNA 标注同步端点（Google Apps Script，独立项目可直接用）
 *
 * 部署步骤（约 5 分钟）：
 *  1. https://script.google.com → 左上「新建项目」→ 项目名随便（如 gameclip-sync）
 *  2. 把本文件全部内容粘贴进去，替换默认的 Code.gs → Ctrl+S 保存
 *  3. 右上「部署」→「新建部署」→ 齿轮选「Web 应用」
 *       说明：gameclip-sync
 *       执行身份：我（Me）
 *       访问权限：任何人（Anyone）
 *     →「部署」→ 首次会跳授权：选账号 →「高级」→「转至 xxx（不安全）」→ 允许
 *  4. 复制「Web 应用」URL（https://script.google.com/macros/s/.../exec）
 *     —— 这个 URL 就是标注页要填的「同步地址」
 *  5. 用浏览器打开该 URL（GET）可看到 JSON：里面 spreadsheetUrl 就是数据表链接
 *
 * 数据：自动创建 Google 表格《Gameclip labels》→ 工作表 labels，
 *       按 (annotator, clip_id) 去重更新；表 ID 存在脚本属性里，重启也不丢。
 *
 * 注意：改了代码要「部署 → 管理部署 → 编辑 → 版本选新版本」才生效。
 */

function getSheet_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('SHEET_ID');
  var ss = null;
  if (id) {
    try { ss = SpreadsheetApp.openById(id); } catch (e) { ss = null; }
  }
  if (!ss) {
    ss = SpreadsheetApp.create('Gameclip labels');
    props.setProperty('SHEET_ID', ss.getId());
  }
  var sh = ss.getSheetByName('labels') || ss.insertSheet('labels');
  return { ss: ss, sh: sh };
}

var HEAD = ['annotator', 'clip_id', 'stance', 'intensity', 'p_codes', 'r_codes',
            'evidence', 'confidence', 'notes', 'annotated_at'];

function doGet(e) {
  var g = getSheet_();
  var p = (e && e.parameter) || {};
  if (String(p.format || '').toLowerCase() === 'csv') {
    // 进度页直接读：GET <exec>?format=csv  → labels 表全量 CSV（带 CORS）
    var values = g.sh.getDataRange().getValues();
    var lines = values.map(function (row) {
      return row.map(function (v) {
        v = String(v == null ? '' : v);
        return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v;
      }).join(',');
    });
    return ContentService.createTextOutput(lines.join('\n'))
      .setMimeType(ContentService.MimeType.CSV);
  }
  return ContentService.createTextOutput(JSON.stringify({
    ok: true,
    message: 'gameclip sync endpoint is up',
    spreadsheetUrl: g.ss.getUrl(),
    rows: Math.max(0, g.sh.getLastRow() - 1),
    csvUrl: ScriptApp.getService().getUrl() + '?format=csv'
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var body = {};
  try { body = JSON.parse(e.postData.contents); } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({ ok: false, error: 'bad json' }))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var g = getSheet_();
  var sh = g.sh;
  if (sh.getLastRow() === 0) sh.appendRow(HEAD);

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
    if (!r.stance) continue;
    var row = [annotator, cid, r.stance || '', r.intensity || '', r.p_codes || '',
               r.r_codes || '', r.evidence || '', r.confidence || '', r.notes || '',
               r.annotated_at || ''];
    var key = annotator + '|' + cid;
    if (existing[key]) updates.push({ row: existing[key], vals: row });
    else appends.push(row);
  }
  updates.forEach(function (u) { sh.getRange(u.row, 1, 1, HEAD.length).setValues([u.vals]); });
  if (appends.length) sh.getRange(sh.getLastRow() + 1, 1, appends.length, HEAD.length).setValues(appends);

  return ContentService.createTextOutput(JSON.stringify({
    ok: true, updated: updates.length, appended: appends.length,
    spreadsheetUrl: g.ss.getUrl()
  })).setMimeType(ContentService.MimeType.JSON);
}
