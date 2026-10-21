/* 站内通知：顶栏未读数、通知中心、全部已读与逾期扫描。 */

import { GET, POST } from './api.js';
import { canManage } from './auth.js';
import { dtShort, esc, skeleton } from './format.js';
import { go } from './router.js';
import { openModal, closeModal, toast } from './ui.js';

let items = [];

export async function refreshNotifications() {
  try {
    const summary = await GET('/notifications/summary');
    const badge = document.getElementById('notifBadge');
    if (badge) {
      badge.textContent = summary.unread > 99 ? '99+' : String(summary.unread);
      badge.classList.toggle('hide', !summary.unread);
      badge.title = summary.unread + ' 条未读';
    }
    return summary;
  } catch (e) {
    return null;
  }
}

export async function openNotifications() {
  openModal('通知中心', skeleton(4));
  try {
    items = await GET('/notifications?limit=50');
  } catch (e) {
    openModal('通知中心', `<div class="errbar"><div>${esc(e.message)}</div></div>`,
      '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
    return;
  }
  const unread = items.filter((n) => !n.is_read).length;
  const rows = items.map((n) => `
    <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="openNotification(${n.id})">
      <span class="notif-dot"></span>
      <div class="notif-main">
        <div class="notif-title">${esc(n.title)}</div>
        ${n.body ? '<div class="tiny">' + esc(n.body) + '</div>' : ''}
        <div class="tiny">${esc(n.type_label)} · ${dtShort(n.created_at)}</div>
      </div>
      <span class="alert-go">›</span>
    </div>`).join('') || '<div class="empty">没有通知</div>';

  openModal('通知中心', `
    <div class="between mb">
      <div class="desc" style="margin:0">${unread ? `${unread} 条未读` : '全部已读'}</div>
      <div class="gap">
        ${canManage() ? '<button class="btn-sm" onclick="scanNotifications()">扫描逾期</button>' : ''}
        <button class="btn-sm" onclick="markAllNotificationsRead()">全部已读</button>
      </div>
    </div>
    <div class="notif-list">${rows}</div>`,
    '<button class="btn btn-g" onclick="closeModal()">关闭</button>');
}

export async function openNotification(id) {
  const item = items.find((n) => n.id === id);
  try {
    await POST('/notifications/' + id + '/read', {});
  } catch (e) {
    toast(e.message, true);
  }
  await refreshNotifications();
  closeModal();
  if (item && item.link) go(item.link);
}

export async function markAllNotificationsRead() {
  try {
    await POST('/notifications/read-all', {});
    toast('已全部标记为已读');
    await refreshNotifications();
    await openNotifications();
  } catch (e) {
    toast(e.message, true);
  }
}

export async function scanNotifications() {
  try {
    const result = await POST('/notifications/scan', {});
    toast(result.created
      ? `扫描完成，新增 ${result.created} 条提醒`
      : '扫描完成，没有新的逾期提醒');
    await refreshNotifications();
    await openNotifications();
  } catch (e) {
    toast(e.message, true);
  }
}
