/* 帮助中心入口：顶栏 ? → 当前页章节深链。 */

import { go, urlParams } from './router.js';
import { state } from './state.js';
import { topicIdForPage } from '../help/catalog.js';

/** 打开当前视图对应的帮助章节（可带 tab 等上下文）。 */
export function openPageHelp(view) {
  const v = view || state.view || 'start';
  const params = v === state.view ? urlParams() : {};
  const topic = topicIdForPage(v, params);
  go('help', { params: { topic }, push: true });
}

/** 打开指定章节。 */
export function openHelpTopic(topic, extra = {}) {
  go('help', { params: { topic: topic || 'intro', ...extra }, push: true });
}
