# 资产页单主题收敛实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有流程资产页收敛为“能否生成资产包—当前阻断—唯一下一步”的单一主线，保留 Gate 5 与专家明细但不让多个主题抢占首屏。

**Architecture:** 只改现有 `asset.js` 与前端结构测试，不增加后端接口、数据库或新页面。资产 readiness 决定首屏结论；Gate 5 作为关键阻断来源和后续明细；经营状态、生成就绪度和原有阻断列表后置到折叠区。

**Tech Stack:** 原生 ES modules、现有 `pageShell`/`foldCard`、现有 API 和结构测试。

**Spec:** docs/superpowers/specs/2026-11-22-asset-page-single-topic-design.md

## Global Constraints

- 资产页首屏只回答能否生成资产包、关键阻断和唯一下一步。
- Gate 5 不取代资产 readiness 主结论，不新增 Gate 5 专用页面。
- 不修改后端状态、API、模型发布、运行实例或责任事实。
- 不写死 L3-032；通用 API 和通用前端结构验收为准，样本仅烟测。
- 页面布局只走现有 `pageShell`；明细使用现有折叠/后续区块。
- 前端不自行计算业务状态、不维护后端枚举口径。

## Review Focus

- Gate 5 BLOCKED 时，唯一下一步必须优先显示责任闭合，不被 KPI/资源明细抢走。
- Gate 5 不可用时，资产页仍能显示资产 readiness，不得整页空白。
- 资产可生成时，不应被 Gate 5 明细错误改成不可生成。
- 原有资产阻断和办理按钮必须保留，但后置，不得删除事实。
- 只读用户不因页面收敛获得新的写入动作。

## Task 1: 固定单主题首屏契约

**Files:**
- Modify: `tests/test_frontend_structure.py`
- Test behavior: `web/js/views/asset.js` source contract

- [ ] 写失败结构测试，断言资产概览存在资产主结论、唯一下一步和 Gate 5 后置明细标记；断言经营状态/生成就绪度不作为首屏并列主主题。
- [ ] 运行 `pytest tests/test_frontend_structure.py::<new_tests> -q`，预期因当前资产页仍平铺多主题而失败。
- [ ] 在测试中固定通用文案/结构断言，不引用 L3-032 字符串，不断言实现私有函数。

## Task 2: 收敛资产页首屏

**Files:**
- Modify: `web/js/views/asset.js`
- Modify: `web/js/views/shared/gate5.js` only if needed for post-section rendering

- [ ] 让 `overviewHtml(readiness, operating, blockers, writable, gate5)` 计算一个首屏 `primaryBlocker` 和 `nextAction`：Gate 5 BLOCKED 时优先使用 Gate 5 的下一步，否则使用资产 readiness 的 `next_action`。
- [ ] 首屏只保留三张摘要卡：资产产出结论、关键阻断、唯一下一步；Gate 5 卡片改为后续明细区，不与首屏摘要抢主题。
- [ ] 将流程经营状态、生成就绪度和原“阻断与下一步”收进后续 `foldCard`/明细区；保留原数据和办理按钮。
- [ ] Gate 5 API 失败或没有数据时，资产主线仍根据资产 readiness 正常渲染。
- [ ] 运行 Task 1 结构测试，预期 PASS。

## Task 3: 通用前端回归与实际页面复核

**Files:**
- No new production files
- Test: `tests/test_frontend_structure.py`

- [ ] 运行前端结构测试和 Gate 5 API 测试。
- [ ] 运行 `python scripts/check.py`，确认格式、静态检查和全量测试通过。
- [ ] 用当前服务实际打开任意流程资产页，核对首屏只有资产主线；Gate 5、经营状态和生成就绪度在后续明细区可见。
- [ ] 不把 L3-032 的业务阻断结果作为机制验收条件；仅记录页面烟测结果。
