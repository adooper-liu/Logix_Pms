/* 附件预览：带鉴权取回二进制，再用 blob URL 内联展示。
 *
 * 下载接口一律 attachment；预览单独走 /preview，只对 PDF/图片/文本开放。
 * 不能直接把受保护 URL 放进 iframe——浏览器不会带 Authorization 头。
 */
import { fetchBlob } from './api.js';
import { openModal } from './ui.js';
import { esc } from './format.js';

let objectUrl = null;

function releasePreview() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('pms:modal-closed', releasePreview);
}

export async function openPreview(previewUrl, kind, title) {
  releasePreview();
  const blob = await fetchBlob(previewUrl);
  objectUrl = URL.createObjectURL(blob);
  const body = kind === 'IMAGE'
    ? `<img class="preview-img" src="${objectUrl}" alt="${esc(title)}">`
    : `<iframe class="preview-frame" src="${objectUrl}" title="${esc(title)}"></iframe>`;
  openModal(
    `预览 · ${esc(title)}`,
    body,
    '<button class="btn btn-g" data-act="ui.close">关闭</button>',
    true,
  );
}
