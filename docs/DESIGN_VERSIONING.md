# 对话、设计运行与版本管理

本项目把“聊天历史”和“设计状态”拆成三个不同生命周期的对象，避免新对话继续修改同一个全局 `current_scheme.json`。

## 三个对象

- `ChatSession`：LangGraph 的 `thread_id` 与 checkpoint，只保存对话和 Agent 工作流状态。
- `DesignRun`：一次独立设计工作区，拥有自己的当前 Scheme、来源和版本链。
- `SchemeVersion`：DesignRun 内每次成功写入后的完整 Scheme 快照；文件一旦创建就不覆盖。

删除 ChatSession 只删除聊天 checkpoint 和绑定，不删除 DesignRun 或 SchemeVersion。恢复旧版本也不改写历史文件，而是以旧快照为内容创建一个新的当前版本。

## 新对话的三种模式

| 模式 | 设计起点 | 后续写入 |
| --- | --- | --- |
| `fresh`（默认） | 由 scene manifest 的 `default_asset_id` 生成完整中性技术基线 | 新建独立 DesignRun |
| `branch` | 复制指定 DesignRun 的当前完整版本 | 新建独立 DesignRun，来源可追溯 |
| `continue` | 指定 DesignRun 的当前版本 | 继续写入同一个 DesignRun |

`fresh` 的中性基线只用于满足 55 个稳定 target 的 Schema 和渲染完整性，不算设计决定。系统提示和 Graph 双重约束 Agent：整屋设计提交 Critic 前，所有锁定 target 都必须在这个 fresh 运行中被显式 `update_scheme`；遗漏任何一个都会被硬拒绝。

## JSON 持久化布局

运行时数据位于 `backend/data/design_runs/`（部署时位于 `DATA_DIR/design_runs/`）：

```text
design_runs/
  index.json                    # run 列表与当前激活 run
  session_bindings.json         # thread_id -> run_id + 对话模式
  run_<id>/
    metadata.json               # 来源、创建时间、当前版本
    head.json                   # 当前 Scheme，供快速读取
    versions/
      ver_<id>.json             # 不可变完整快照 + parent + reason
```

旧的 `current_scheme.json` 只在首次升级时导入为一个 `imported` DesignRun，并被记录为稳定 fallback；迁移前已有、尚无绑定记录的旧对话始终回落到这个 imported run，不会因为后来创建 fresh 会话而漂移。原设计不会被 fresh 会话覆盖。

## API 与渲染隔离

- `POST /api/sessions`：默认 fresh；可传 `mode` 与 `source_design_run_id`。
- `GET /api/design-runs`：列出运行；`GET .../{run_id}/versions`：查看版本链。
- `POST /api/design-runs/{run_id}/restore`：从历史快照创建新版本。
- `GET /api/scheme?design_run_id=...`：读取指定运行，不依赖全局当前方案。

聊天路由在调用 LangGraph 前设置 `design_run_id` 上下文；Scheme 工具据此解析到对应 `VersionedSchemeStore`。视觉命令也携带同一 ID，浏览器在截图前强制加载该运行的 Scheme。这样并行对话、隐藏渲染页和手动 3D 查看都不会串到别的方案。

## 验收重点

1. 新建默认对话得到新的 fresh run，且 55 个 target 的基线合法完整。
2. fresh 或 branch 中修改一个 target，不改变来源 run。
3. 每次成功修改新增版本文件，旧文件内容不变。
4. restore 新增一个版本，而不是回写旧版本。
5. continue 新对话复用 run；删除对话后 run 和版本仍可读取。
6. fresh、branch、continue 的写入都只影响各自绑定的 Design Run，版本历史保持不可变。
