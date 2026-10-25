/* 接口层：统一的请求、鉴权头、错误类型。
 *
 * 401 的处理通过回调注入，而不是直接 import 登录模块 ——
 * 否则 api ↔ auth 会形成循环依赖（auth 登录也要用 api）。
 */

export const API_BASE = '/api/v1';

let authToken = '';
let unauthorizedHandler = () => {};

export function setToken(token) {
  authToken = token || '';
}

export function getToken() {
  return authToken;
}

/** 由 auth 模块在初始化时注册：令牌失效要清身份并弹回登录页 */
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

/**
 * 统一请求：raw=true 时返回 Response（下载用），否则解析 JSON。
 * multipart 由调用方传 FormData，此时不能手动设置 Content-Type。
 */
async function request(path, options, raw) {
  const opts = Object.assign({ headers: {} }, options || {});
  const isForm = typeof FormData !== 'undefined' && opts.body instanceof FormData;
  if (!raw && !isForm && opts.body !== undefined && typeof opts.body !== 'string') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  if (authToken) opts.headers['Authorization'] = 'Bearer ' + authToken;

  let res;
  try {
    const url = path.startsWith(API_BASE + '/') ? path : API_BASE + path;
    res = await fetch(url, opts);
  } catch (e) {
    throw new Error('无法连接后端服务，请确认 uvicorn 正在运行：' + e.message);
  }

  if (res.status === 401) {
    // 令牌失效：清掉本地身份并弹回登录页，不要把 401 当普通错误抛给业务层
    unauthorizedHandler();
    const expired = new Error('未登录或登录已过期');
    expired.status = 401;
    throw expired;
  }

  if (!res.ok) {
    let detail = res.status + ' ' + res.statusText;
    try {
      const body = await res.json();
      if (body && body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch (_) { /* 响应不是 JSON，沿用状态码 */ }
    if (res.status === 403) detail = '权限不足：' + detail;
    const err = new Error(detail);
    err.status = res.status;    // 调用方需要区分 409（版本冲突）等情况
    throw err;
  }
  if (raw) return res;
  return res.status === 204 ? null : res.json();
}

export const api = (path, options) => request(path, options, false);
export const GET = (p) => api(p);
export const POST = (p, body) => api(p, { method: 'POST', body: body === undefined ? {} : body });
export const PATCH = (p, body) => api(p, { method: 'PATCH', body });
export const PUT = (p, body) => api(p, { method: 'PUT', body });
export const DEL = (p) => api(p, { method: 'DELETE' });
/** multipart 上传：body 必须是 FormData */
export const POST_FORM = (p, formData) =>
  request(p, { method: 'POST', body: formData }, false);

/** 带鉴权获取二进制内容，供预览使用（不触发下载） */
export async function fetchBlob(path) {
  const res = await request(path, {}, true);
  return res.blob();
}

/** 带鉴权下载并触发浏览器保存；文件名优先取响应头，其次用 fallback */
export async function download(path, fallback) {
  const res = await request(path, {}, true);
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') || '';
  const matched = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  let name = fallback || 'download';
  if (matched) {
    try { name = decodeURIComponent(matched[1]); } catch (_) { /* 保持 fallback */ }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
