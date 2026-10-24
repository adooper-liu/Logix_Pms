/* 视图：designer（薄壳）。
 *
 * 实现已拆到 ./designer/：index 编排，canvas/providers/xml/panels/assignment/
 * lint/versions/transfer 各管一块。这里只保留 main.js 与跨视图 action 需要的导出。
 */

export { actions, openDesigner, renderDesigner } from './designer/index.js';
