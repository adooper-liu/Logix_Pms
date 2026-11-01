/* 决策表：新建受控决策表，并用一组输入试算。 */

import { esc } from '../../core/format.js';
import { toast, openModal, closeModal } from '../../core/ui.js';
import { GET, POST } from '../../core/api.js';
import { canManage } from '../../core/auth.js';
import { state } from '../../core/state.js';

const SAMPLE_DEF = `{
  "inputs": [
    {"name": "amount", "label": "金额", "type": "number"},
    {"name": "urgent", "label": "加急", "type": "boolean"}
  ],
  "outputs": [
    {"name": "level", "label": "审批级别", "type": "string"}
  ],
  "rules": [
    {"conditions": {"amount": {"op": "gt", "value": 10000}}, "outputs": {"level": "A"}},
    {"conditions": {"urgent": true}, "outputs": {"level": "B"}},
    {"conditions": {"amount": {"op": "always"}}, "outputs": {"level": "C"}}
  ]
}`;

function createBtn() {
  return canManage()
    ? '<button class="btn btn-p" data-act="designer.createDecision">+ 新建决策表</button>'
    : '';
}

function footerClose(extra = '') {
  return `<button class="btn btn-g" data-act="designer.close">关闭</button>${extra}`;
}

function helpHtml() {
  return `
    <details class="dmn-help mb">
      <summary>操作说明 · 完整示例：采购审批分级</summary>
      <div class="dmn-help-body">
        <h4>1. 业务场景</h4>
        <p>采购单要按金额和是否加急定审批级别，口头规定是：</p>
        <ul>
          <li>金额 &gt; 10000 → <b>A</b>（高层批）</li>
          <li>否则若加急 → <b>B</b>（加急通道）</li>
          <li>其余 → <b>C</b>（普通）</li>
        </ul>
        <p>写成决策表后，同一套规则可反复试算，改阈值不必改流程图。
          命中策略用 <b>FIRST</b>：从上往下，命中第一条就停。</p>

        <h4>2. 规则表（人话版）</h4>
        <table class="tbl">
          <thead>
            <tr><th>#</th><th>金额 amount</th><th>加急 urgent</th><th>→ 级别 level</th></tr>
          </thead>
          <tbody>
            <tr><td>1</td><td>&gt; 10000</td><td>（不看）</td><td><b>A</b></td></tr>
            <tr><td>2</td><td>（不看）</td><td>true</td><td><b>B</b></td></tr>
            <tr><td>3</td><td>always（兜底）</td><td>—</td><td><b>C</b></td></tr>
          </tbody>
        </table>
        <p>注意顺序：大额优先于加急。若把加急行放第一，大额加急单会先变成 B，口径就错了。</p>

        <h4>3. 在界面里怎么建（跟做）</h4>
        <ol>
          <li>设计器顶栏点「决策表」→「+ 新建决策表」（需流程管理科 / 管理员）。</li>
          <li>编码填 <code>PO-APPROVAL-LEVEL</code>，名称填「采购审批分级」，命中策略选 <b>FIRST</b>。</li>
          <li>定义 JSON 用下方完整内容（新建弹窗已预填同一模板，可直接创建）。</li>
          <li>创建后回到试算：选刚建的表，按第 5 节粘贴输入，点「求值」对结果。</li>
        </ol>
        <pre class="dmn-example-json">${esc(SAMPLE_DEF)}</pre>
        <p class="hint">条件键出现在某一行里，就必须出现在本次输入中才可能命中该行。
          第 1 行只写了 amount，所以只要金额满足就会命中，不必看 urgent。
          第 3 行用 <code>always</code> 做兜底，放在最后。</p>

        <h4>4. 三条试算（输入 → 期望输出）</h4>
        <table class="tbl">
          <thead><tr><th>场景</th><th>输入 JSON</th><th>期望</th><th>为何</th></tr></thead>
          <tbody>
            <tr>
              <td>大额</td>
              <td><code>{"amount": 20000, "urgent": false}</code></td>
              <td><code>{"level": "A"}</code></td>
              <td>命中第 1 行即停</td>
            </tr>
            <tr>
              <td>小额加急</td>
              <td><code>{"amount": 500, "urgent": true}</code></td>
              <td><code>{"level": "B"}</code></td>
              <td>第 1 行不中，命中第 2 行</td>
            </tr>
            <tr>
              <td>普通</td>
              <td><code>{"amount": 500, "urgent": false}</code></td>
              <td><code>{"level": "C"}</code></td>
              <td>前两行不中，兜底第 3 行</td>
            </tr>
          </tbody>
        </table>
        <p>求值只读，不会改流程。若结果不对：先检查规则顺序，再检查输入字段名是否与 inputs 的 <code>name</code> 一致。</p>

        <h4>5. 原理速记（看完示例再记）</h4>
        <ul>
          <li>一张表 = inputs + outputs + rules + 命中策略（FIRST / COLLECT）。</li>
          <li>op：eq / ne / gt / gte / lt / lte / in / contains / always；简写值等于 eq。</li>
          <li>和权责（谁 A）、授权（谁有权批）、网关（走哪条线）、执行分派（谁领任务）不是同一件事。</li>
          <li><b>当前</b>：建表 + 试算。运行时实例还不会自动套用本表。</li>
        </ul>
      </div>
    </details>`;
}

export function createDecisions() {
  async function open(preferCode) {
    let tables = [];
    try {
      tables = await GET('/decisions');
    } catch (e) {
      return toast(e.message, true);
    }
    if (!tables.length) {
      const hint = canManage()
        ? '还没有决策表。点下方按钮新建首张表（也可从模板改）。'
        : '还没有决策表。请用「流程管理科 / 管理员」账号新建。';
      return openModal('决策表',
        `${helpHtml()}<div class="empty">${hint}</div>`,
        footerClose(createBtn() ? ` ${createBtn()}` : ''),
        true);
    }
    const selected = preferCode || tables[0].code;
    const options = tables.map((row) =>
      `<option value="${esc(row.code)}"${row.code === selected ? ' selected' : ''}>${
        esc(row.code)} · ${esc(row.name)} v${row.version}</option>`).join('');
    openModal('决策表', `
      ${helpHtml()}
      <div class="note mb">先选表，再输入 JSON；求值只读，不会改流程状态。</div>
      <div class="field"><label>决策表</label><select id="dmnTable">${options}</select></div>
      <div class="field"><label>输入（JSON）</label>
        <textarea id="dmnInput" rows="4">{}</textarea></div>
      <div id="dmnResult" class="mt"></div>`,
    footerClose(`${createBtn() ? ` ${createBtn()}` : ''} <button class="btn btn-p" data-act="designer.evaluateDecision">求值</button>`),
    true);
  }

  function openCreate() {
    if (!canManage()) return toast('需要流程管理科或管理员权限', true);
    const pid = state.designer.processId;
    const codeHint = pid
      ? `建议用大写编码，如 PO-APPROVAL；可挂到当前流程 #${pid}`
      : '编码仅大写字母 / 数字 / _ / -，2–48 位';
    openModal('新建决策表', `
      ${helpHtml()}
      <div class="note mb">建表后可在本弹窗试算；运行时实例尚不会自动套用规则。</div>
      <div class="row2">
        <div class="field"><label>编码 *</label>
          <input id="dmnCode" placeholder="PO-APPROVAL-LEVEL" autocomplete="off">
          <div class="hint">${esc(codeHint)}</div></div>
        <div class="field"><label>名称 *</label>
          <input id="dmnName" placeholder="采购审批分级"></div>
      </div>
      <div class="row2">
        <div class="field"><label>命中策略</label>
          <select id="dmnHit">
            <option value="FIRST">FIRST · 命中第一条即停</option>
            <option value="COLLECT">COLLECT · 合并所有命中</option>
          </select></div>
        <div class="field"><label>归属当前流程</label>
          <label style="display:flex;align-items:center;gap:6px;margin-top:6px">
            <input type="checkbox" id="dmnBindProcess"${pid ? ' checked' : ' disabled'}>
            <span>${pid ? `挂到流程 #${pid}` : '当前未选流程'}</span></label></div>
      </div>
      <div class="field"><label>说明</label>
        <input id="dmnDesc" placeholder="可选：按金额 / 加急定审批级别"></div>
      <div class="field"><label>定义 JSON（inputs / outputs / rules）*</label>
        <textarea id="dmnDef" rows="14">${esc(SAMPLE_DEF)}</textarea>
        <div class="hint">条件 op：eq / ne / gt / gte / lt / lte / in / contains / always</div></div>`,
      `<button class="btn btn-g" data-act="designer.close">取消</button>
       <button class="btn btn-p" data-act="designer.submitDecision">创建</button>`,
      true);
  }

  async function submitCreate() {
    if (!canManage()) return toast('需要流程管理科或管理员权限', true);
    const code = (document.getElementById('dmnCode')?.value || '').trim().toUpperCase();
    const name = (document.getElementById('dmnName')?.value || '').trim();
    if (!code) return toast('请填写编码', true);
    if (!/^[A-Z0-9_-]{2,48}$/.test(code)) {
      return toast('编码须为 2–48 位大写字母、数字、_ 或 -', true);
    }
    if (!name) return toast('请填写名称', true);

    let def;
    try {
      def = JSON.parse(document.getElementById('dmnDef')?.value || '{}');
    } catch (_) {
      return toast('定义不是合法 JSON', true);
    }
    if (!Array.isArray(def.inputs) || !Array.isArray(def.outputs) || !Array.isArray(def.rules)) {
      return toast('定义须包含 inputs / outputs / rules 三个数组', true);
    }

    const bind = document.getElementById('dmnBindProcess')?.checked;
    const payload = {
      code,
      name,
      hit_policy: document.getElementById('dmnHit')?.value || 'FIRST',
      description: (document.getElementById('dmnDesc')?.value || '').trim() || null,
      process_id: bind && state.designer.processId ? state.designer.processId : null,
      inputs: def.inputs,
      outputs: def.outputs,
      rules: def.rules,
    };
    try {
      const created = await POST('/decisions', payload);
      closeModal();
      toast(`已创建 ${created.code}`);
      await open(created.code);
    } catch (e) {
      toast(e.message, true);
    }
  }

  async function evaluate() {
    const code = document.getElementById('dmnTable')?.value;
    const raw = document.getElementById('dmnInput')?.value || '{}';
    let inputs;
    try {
      inputs = JSON.parse(raw);
    } catch (_) {
      return toast('输入不是合法 JSON', true);
    }
    try {
      const result = await POST(`/decisions/${encodeURIComponent(code)}/evaluate`, { inputs });
      const box = document.getElementById('dmnResult');
      box.innerHTML = `
        <div class="note ${result.matched ? '' : 'warnbox'}">
          ${result.matched ? '命中 ' + result.matched_count + ' 条规则' : '没有命中规则'}
        </div>
        <div class="field"><label>输出</label>
          <pre>${esc(JSON.stringify(result.outputs, null, 2))}</pre></div>`;
    } catch (e) {
      toast(e.message, true);
    }
  }

  return { open, openCreate, submitCreate, evaluate };
}
