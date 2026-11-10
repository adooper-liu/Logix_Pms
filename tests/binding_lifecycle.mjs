// Real module lifecycle regression: stale same-process refresh must not replace new load.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

let source = await fs.readFile('web/js/views/designer/binding.js', 'utf8');
source = source.replace(/^import .*;\r?\n/gm, '');
const state = {view: 'designer', designer: {processId: 1, model: {draft_version: 2}, binding: null}};
let release;
const GET = () => new Promise(resolve => {release = resolve;});
const factory = new Function('state','GET','on','esc','tipHelp','foldCard',
    source.replace('export function createBinding', 'function createBinding') + ';return createBinding;');
const createBinding = factory(state, GET, () => {}, String, () => '', () => '');
const binding = createBinding({getModeler: () => null, renderSelection: () => {}});
const pending = binding.refresh();
state.view = 'workbench';
state.view = 'designer';
state.designer.model = {draft_version: 3};
binding.accept({data: {process_id: 1, model_version: 3}});
release({process_id: 1, model_version: 2});
await pending;
assert.equal(state.designer.binding.model_version, 3, 'old refresh overwrote newer same-process load');
console.log('PASS stale refresh ignored after same-process reentry');
binding.accept({data: {process_id: 1, model_version: 2}});
assert.equal(state.designer.binding, null, 'mismatched initial model must not paint old readiness');
assert.match(state.designer.bindingError, /模型已变化/);
