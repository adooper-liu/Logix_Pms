# 产品帮助中心（内容源说明）

产品内「帮助中心」是**唯一面向新人的帮助入口**。仓库里的
`usage-guide.md` / `training-zero-to-one.md` / `startup-path.md` 是**素材与深读**，
不是并列的三套产品帮助。

## 内容树（阅读序）

1. **定位** — 这是什么、为谁、解决什么  
2. **价值** — 为什么要用  
3. **边界** — 不做什么、模块怎么分  
4. **原理** — 核心对象与因果（发布快照、出边、分派…）  
5. **场景** — 按工作任务，不按菜单  
6. **实操** — 可点可抄的步骤  
7. **术语** — 一词一义  

运行时章节正文在 `web/js/help/catalog.js`（零构建前端直接 import）。
改口径时：**先改 catalog**，再视需要回写本目录或 usage-guide 摘要。

## 产品出口

| 出口 | 职责 |
|---|---|
| 顶栏 `?` | 打开**当前页**对应章节（深链 `#help?topic=…`） |
| `#help` 帮助页 | 目录浏览、场景、实操、术语 |
| 页内短 tip | 1～3 句即时口径；长文回帮助深链 |
| 「体系总览」 | 0→1 **带做**主线，不扩成百科 |

## 素材对照

| 素材 | 用途 |
|---|---|
| [usage-guide.md](../usage-guide.md) | 模块定位与误区（写入 catalog 的边界/模块章） |
| [training-zero-to-one.md](../training-zero-to-one.md) | 培训带练脚本（场景/实操素材） |
| [startup-path.md](../startup-path.md) | 九步原理与证据口径 |
| [ui-information-architecture.md](../ui-information-architecture.md) | 设计契约；帮助只摘「主问题/边界」 |
