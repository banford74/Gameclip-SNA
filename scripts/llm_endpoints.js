// 统一 LLM 端点：OpenCode Go（OpenAI 兼容 /chat/completions）
//
// 环境变量（仓库里不存 key）：
//   OPENCODE_API_KEY   必填（Go 订阅的 key）
//   OPENCODE_BASE_URL  可选，默认 https://opencode.ai/inference/go/openai/v1
//   OPENCODE_MODEL     可选，默认 deepseek-v4.1-flash
//   OPENCODE_SESSION   可选，x-opencode-session 头取值（默认每进程随机）
//
// 为什么要这个头：Go 端点按 session 做路由/额度归集，缺了直接 400
// MissingSessionID。同时注意 Go 端点和按量付费的 /inference/openai/v1 不是
// 同一个计费线——同一个 key 打到后者的付费模型会报 402 余额不足。
//
// 该端点前面有 Cloudflare：Node 默认 UA 能过，但这里仍显式带浏览器 UA，
// 避免指纹规则变动时整批 403。
const crypto = require('crypto');
const DEFAULT_BASE = 'https://opencode.ai/inference/go/openai/v1';
const DEFAULT_MODEL = 'deepseek-v4.1-flash';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         + '(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
// 一次进程一个 session id 即可（服务端只要求唯一，不校验格式）
const SESSION = process.env.OPENCODE_SESSION || 'dsh-' + crypto.randomUUID();

function baseURL() {
  return (process.env.OPENCODE_BASE_URL || DEFAULT_BASE).replace(/\/+$/, '');
}

function apiKey() {
  const k = process.env.OPENCODE_API_KEY || '';
  if (!k) throw new Error('缺少环境变量 OPENCODE_API_KEY（OpenCode Go 订阅的 key；仓库不存 key）');
  return k;
}

// name 只用于日志/结果文件，model 才是请求里的模型 id
function endpoint(model, name) {
  return {
    name: name || model,
    base: baseURL(),
    key: apiKey(),
    model: model || process.env.OPENCODE_MODEL || DEFAULT_MODEL,
  };
}

async function chatJSON(ep, body, timeoutMs = 180000) {
  const resp = await fetch(ep.base + '/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + ep.key,
      'Content-Type': 'application/json',
      'User-Agent': UA,
      'x-opencode-session': SESSION,
    },
    body: JSON.stringify({ temperature: 0, ...body, model: ep.model }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  const text = await resp.text();
  if (!resp.ok) throw new Error(`http ${resp.status}: ${text.slice(0, 200)}`);
  return JSON.parse(text);
}

module.exports = { endpoint, chatJSON, baseURL, apiKey, UA, SESSION, DEFAULT_BASE, DEFAULT_MODEL };
