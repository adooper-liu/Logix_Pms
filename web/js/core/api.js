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

export async function api(path, options) {
  const opts = Object.assign({ headers: {} }, options || {});
  if (opts.body !== undefined && typeof opts.body !== 'string') {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  if (authToken) opts.headers['Authorization'] = 'Bearer ' + authToken;

  let res;
  try {
    res = await fetch(API_BASE + path, opts);
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
  return res.status === 204 ? null : res.json();
}

export const GET = (p) => api(p);
export const POST = (p, body) => api(p, { method: 'POST', body: body === undefined ? {} : body });
export const PATCH = (p, body) => api(p, { method: 'PATCH', body });
export const PUT = (p, body) => api(p, { method: 'PUT', body });
export const DEL = (p) => api(p, { method: 'DELETE' });
