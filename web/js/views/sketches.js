/* 视图：架构草图 —— 独立的 draw.io 白板，不参与 BPMN 建模与流程执行。 */
import { esc, dtShort, emptyRow } from '../core/format.js';
import { toast, openModal, closeModal, confirmDialog, viewEl, on } from '../core/ui.js';
import { state } from '../core/state.js';
import { renderAsync, RENDERERS } from '../core/router.js';
import { canWrite, canManage } from '../core/auth.js';
import { GET, POST, PATCH, DEL } from '../core/api.js';

on('sketch.open', ({ id }) => openSketchEditor(Number(id)));
on('sketch.edit', ({ id }) => editSketchModal(Number(id)));
on('sketch.delete', ({ id }) => deleteSketch(Number(id)));
on('sketch.create', () => createSketchModal());
on('sketch.close', () => closeModal());
on('sketch.closeEditor', () => closeSketchEditor());
on('sketch.submitNew', () => submitSketch(null));
on('sketch.submit', ({ id }) => submitSketch(Number(id)));

const EMPTY_MXFILE = `<mxfile host="embed.diagrams.net">
  <diagram id="page-1" name="Page-1">
    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" tooltips="1"
      connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1169"
      pageHeight="827" math="0" shadow="0">
      <root><mxCell id="0"/><mxCell id="1" parent="0"/></root>
    </mxGraphModel>
  </diagram>
</mxfile>`;

let drawioListener = null;

function embedOrigin(url) {
  try {
    return new URL(url, location.origin).origin;
  } catch (e) {
    return location.origin;
  }
}

/** draw.io embed 的 proto=json 模式收发的是 JSON 字符串，不是对象。
 *  两种都接受，避免协议升级或自托管实例差异导致消息被静默丢弃。 */
function parseEmbedMessage(data) {
  if (typeof data === 'string') {
    try {
      return JSON.parse(data);
    } catch (e) {
      return null;
    }
  }
  return data && typeof data === 'object' ? data : null;
}

function processLabel(row) {
  return 'L' + row.level + ' ' + row.code + ' ' + row.name;
}

const renderSketches = () => {
  return renderAsync('sketches',
    () => Promise.all([
      GET('/sketches'),
      GET('/sketches/meta'),
      GET('/process-map/flat'),
      GET('/projects?page_size=100'),
    ]),
    ([sketches, meta, processes, projects]) => {
      state.sketches = sketches;
      state.sketchMeta = meta;
      state.sketchProcesses = processes;
      state.sketchProjects = projects.items || [];

      const rows = sketches.map((s) => `
        <tr>
          <td><b>${esc(s.title)}</b><div class="tiny">${esc(s.description || '—')}</div></td>
          <td class="tiny">${s.process_code
            ? 'L' + esc(s.process_code) + ' ' + esc(s.process_name)
            : '—'}${s.project_code
            ? '<div>项目 ' + esc(s.project_code) + ' ' + esc(s.project_name) + '</div>' : ''}</td>
          <td class="tiny">${esc(s.created_by_name || '—')}</td>
          <td class="tiny">${dtShort(s.updated_at)}</td>
          <td>
            <button class="btn-sm" data-act="sketch.open" data-id="${s.id}"${
              canWrite() ? '' : ' disabled'}>打开</button>
            ${canWrite() ? `<button class="btn-sm" data-act="sketch.edit"
              data-id="${s.id}">编辑信息</button>` : ''}
            ${canManage() ? `<button class="btn-sm" data-act="sketch.delete"
              data-id="${s.id}">删除</button>` : ''}
          </td>
        </tr>`).join('') || emptyRow(5, '还没有架构草图');

      viewEl().innerHTML = `
        <div class="card page-head">
          <div class="between">
            <div>
              <h2>架构草图<span class="module-badge">draw.io 白板</span></h2>
              <div class="desc">自由画布 · 用于架构草图/汇报示意，独立于 BPMN 设计器与流程执行；
                不作为可执行流程模型</div>
            </div>
            ${canWrite()
              ? '<button class="btn btn-p" data-act="sketch.create">+ 新建草图</button>' : ''}
          </div>
        </div>
        <div class="card">
          <table class="tbl">
            <thead><tr><th>标题</th><th>关联</th><th>创建人</th><th>更新时间</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    });
};

function scopeOptions() {
  const processes = state.sketchProcesses || [];
  const projects = state.sketchProjects || [];
  return {
    processOpts: processes.map((p) =>
      `<option value="${p.id}">${esc(processLabel(p))}</option>`).join(''),
    projectOpts: projects.map((p) =>
      `<option value="${p.id}">${esc(p.code)} ${esc(p.name)}</option>`).join(''),
  };
}

function sketchForm(sketch) {
  const { processOpts, projectOpts } = scopeOptions();
  return `
    <div class="field"><label>标题 *</label>
      <input id="skTitle" value="${esc(sketch ? sketch.title : '')}" placeholder="例如：华东基地流程架构草图"></div>
    <div class="field"><label>说明</label>
      <textarea id="skDesc" placeholder="这张图用来表达什么">${esc(sketch ? (sketch.description || '') : '')}</textarea></div>
    <div class="row2">
      <div class="field"><label>关联流程（可选）</label>
        <select id="skProcess"><option value="">不关联</option>${processOpts}</select></div>
      <div class="field"><label>关联项目（可选）</label>
        <select id="skProject"><option value="">不关联</option>${projectOpts}</select></div>
    </div>
    <div class="hint">草图是独立白板，不会出现在流程执行的可启动流程里。</div>`;
}

function selectValue(id, value) {
  const el = document.getElementById(id);
  if (el) el.value = value ? String(value) : '';
}

function createSketchModal() {
  openModal('新建架构草图', sketchForm(null),
    `<button class="btn btn-g" data-act="sketch.close">取消</button>
     <button class="btn btn-p" data-act="sketch.submitNew">创建</button>`);
}

function editSketchModal(id) {
  const sketch = (state.sketches || []).find((s) => s.id === id);
  if (!sketch) return;
  openModal('编辑草图信息', sketchForm(sketch),
    `<button class="btn btn-g" data-act="sketch.close">取消</button>
     <button class="btn btn-p" data-act="sketch.submit" data-id="${id}">保存</button>`);
  selectValue('skProcess', sketch.process_id);
  selectValue('skProject', sketch.project_id);
}

async function submitSketch(id) {
  const title = document.getElementById('skTitle').value.trim();
  if (!title) return toast('标题必填', true);
  const processValue = document.getElementById('skProcess').value;
  const projectValue = document.getElementById('skProject').value;
  const payload = {
    title,
    description: document.getElementById('skDesc').value.trim() || null,
    process_id: processValue ? Number(processValue) : null,
    project_id: projectValue ? Number(projectValue) : null,
  };
  try {
    if (id) await PATCH('/sketches/' + id, payload);
    else await POST('/sketches', payload);
    closeModal();
    toast(id ? '草图信息已保存' : '草图已创建');
    RENDERERS.sketches();
  } catch (e) {
    toast(e.message, true);
  }
}

async function openSketchEditor(id) {
  let sketch;
  try {
    sketch = await GET('/sketches/' + id);
  } catch (e) {
    return toast(e.message, true);
  }
  const embedUrl = (state.sketchMeta && state.sketchMeta.embed_url) || '';
  if (!embedUrl) return toast('draw.io 编辑器未配置', true);
  const origin = embedOrigin(embedUrl);
  openModal('架构草图 · ' + sketch.title, `
    <div class="note mb">draw.io 白板 · 保存后写入草图，不进入 BPMN 模型。
      若使用外部 embed 服务，草图内容会发送到该服务；生产建议自托管。</div>
    <iframe id="drawioFrame" class="drawio-frame" src="${esc(embedUrl)}"
      title="draw.io 架构草图"></iframe>`,
    '<button class="btn btn-g" data-act="sketch.closeEditor">关闭</button>', true);

  const frame = document.getElementById('drawioFrame');
  const saveXml = async (xml) => {
    if (!xml) return;
    try {
      await PATCH('/sketches/' + id, { mxfile_xml: xml });
      sketch.mxfile_xml = xml;
      toast('草图已保存');
    } catch (e) {
      toast(e.message, true);
    }
  };
  const checkAlive = () => {
    if (document.getElementById('drawioFrame') === frame) return true;
    if (drawioListener) {
      window.removeEventListener('message', drawioListener);
      drawioListener = null;
    }
    return false;
  };
  drawioListener = (event) => {
    if (!checkAlive()) return;
    if (event.source !== frame.contentWindow) return;
    if (origin !== 'null' && event.origin !== origin) return;
    const data = parseEmbedMessage(event.data);
    if (!data || !data.event) return;
    if (data.event === 'init') {
      frame.contentWindow.postMessage(JSON.stringify({
        action: 'load',
        xml: sketch.mxfile_xml || EMPTY_MXFILE,
        title: sketch.title,
        autosave: 1,
      }), origin);
    } else if (data.event === 'save' || data.event === 'autosave') {
      saveXml(data.xml);
    } else if (data.event === 'exit') {
      closeSketchEditor();
    }
  };
  window.addEventListener('message', drawioListener);
}

function closeSketchEditor() {
  if (drawioListener) {
    window.removeEventListener('message', drawioListener);
    drawioListener = null;
  }
  closeModal();
  RENDERERS.sketches();
}

async function deleteSketch(id) {
  if (!(await confirmDialog('确定删除这张架构草图？', { danger: true, okText: '删除' }))) return;
  try {
    await DEL('/sketches/' + id);
    toast('草图已删除');
    RENDERERS.sketches();
  } catch (e) {
    toast(e.message, true);
  }
}

export { renderSketches };
