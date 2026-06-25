---
name: cram-engine
description: "Use when the user wants to cram for exams, mentions cram load / cram next / cram status, or asks about exam prep and考前速成. AI exam cram engine with SM-2 spaced repetition, knowledge graph topological sorting, and a 6-stage state machine (diagnose, deconstruct, teach, test, remediate, review). Ingests past exams, textbooks, and lecture notes. Supports bilingual Chinese/English teaching."
---

# 期末速成引擎 (Cram Engine) for Codex

## 状态机硬约束

本技能维护严格的状态机。每次对话轮次开始时，你必须执行以下前置检查：

1. 读取进度文件获取 current_stage（0-5）和 current_node_id
2. 若进度文件不存在，判定为未初始化，引导用户执行 cram load
3. 若 current_stage 不在 0-5 范围内，报错并终止
4. 根据 current_stage 加载对应模板：stage{current_stage}-*.md
5. 本轮对话结束后，立即将新状态写回进度文件

禁止行为：跳过任何阶段、阶段3存在答错 must_know 节点时直接结束、阶段4存在未纠正 must_know 节点时标记完成、user_level 未知时跳过诊断直接进入阶段2。

## 命令路由

### cram load —— 首次加载课程

执行配置向导——逐项收集课程类型(subject_type)、教材、题型、复习资料、知识点列表、must_know编号（支持范围格式如 "3-5"）、key_point编号。

信息收集完成后按顺序执行：
1. 写入课程配置 YAML（含 language 字段：zh 中文 / en 英文）
2. 若有资料，执行 `ingest.py` 摄入
3. 生成教材知识画像（`textbook-profile.md` 模板），写入 `knowledge/<课名>/textbook_profile.json`
4. 执行 `indexer.py` 构建知识图谱（加载教材画像以校准术语和知识点顺序）
5. 执行 `progress.py init` 初始化进度（user_level=unknown）
6. 展示图谱摘要，等待确认后进入阶段0（诊断）

### cram next —— 核心命令，执行下一轮学习交互

读取当前进度，调用 `scheduler.py` 获取下一步动作，按当前 stage 模板执行一轮教学。

### cram status —— 展示学习全景

当前阶段、用户水平、已学/未学节点数、must_know掌握率、顽固点清单、SM-2到期复习列表。

### cram retry 知识点 —— 重走讲→测→补闭环

对指定知识点重走微型闭环，结果追加到进度文件。

## 阶段概要

### 阶段0 诊断（新增）
根据用户提供的资料出一套 8-10 题的诊断卷，评估用户水平为 beginner / intermediate / advanced。诊断结果决定阶段2的讲授深度和节奏。完成后 current_stage=2，开始讲授。

### 阶段1 拆解
在 cram load 的最后一步执行：展示自动构建的知识图谱摘要，确认拓扑顺序和依赖关系。
这是课程初始化的一部分，不在 cram next 的主循环中。
完成后由 cram load 流程转入阶段 0（诊断），无需手动操作。

### 阶段2 讲授
四步教学（Concrete First → Chunking → Elaboration → Generation），按拓扑序逐个节点推进，每3个节点暂停确认节奏。
讲授深度根据 user_level 自适应：
- beginner：更详细、更多场景、慢节奏
- intermediate：正常节奏
- advanced：更紧凑、侧重串联和深度追问

**知识点覆盖完整性**：如果知识点包含多个子维度（如"二叉树的遍历"含前序/中序/后序/层次），必须全部覆盖。
完成后 current_stage=3。

### 阶段3 检题
六种子模式覆盖所有题型。题目数量大幅增加：
- must_know 节点：6-8 题
- key_point 节点：4-6 题

采用自适应策略：第一轮 4 题全对 → 开放追问 → 通过则跳过第二轮。
陷阱题占 20%，干扰项来自同课其他知识点。
完成后根据 SM-2 算法更新间隔复习计划。
有 must_know 错题则 current_stage=4，全对则完成。

### 阶段4 补漏
诊断根因→换讲法→重测→顽固判定。
must_know 节点额外多出 3 道新题，两次全对方可过关。
连续 3 次纠正仍错 → 标记顽固点。

### 阶段5 复习（新增）
SM-2 到期复习。三步：闪回→快问→反馈。
must_know 节点答错 → 重新进入阶段4补漏。
key_point 节点答错 → 缩短间隔，下次再测。

## 文件路径约定

技能根目录即本 SKILL.md 所在目录。
- 课程配置：`configs/<课名>.yaml`
- 知识图谱：`knowledge/<课名>/index.json`
- 进度：`progress/<课名>.json`（含 `.json.bak` 备份）
- 摄入原始资料：`knowledge/<课名>/raw/`
- 提取文本：`knowledge/<课名>/extracted/`
- 脚本：`scripts/`（所有脚本统一 import `utils.py`）

## 脚本说明

| 脚本 | 功能 | 依赖 |
|------|------|------|
| `utils.py` | 公共工具：路径、JSON 读写、文本清洗、YAML 解析、SM-2 算法 | 无 |
| `ingest.py` | 资料摄入：txt/pdf/图片 → extracted/*.txt | utils |
| `indexer.py` | 知识图谱构建：config + 提取文本 → index.json | utils |
| `progress.py` | 进度管理：init/status/update | utils |
| `scheduler.py` | 课程调度：progress + index → 下一步动作 | utils |

### SM-2 间隔复习算法

位于 `utils.py`，提供两个核心函数：
- `sm2_update(sm2_state, quality)` — 根据答题质量更新间隔计划
- `sm2_quality_from_accuracy(correct, total, is_must_know)` — 从正确率推算 quality 值

阶段3 和 阶段5 结束后自动调用更新 SM-2 状态。

### must_know_ids 范围格式支持

YAML 配置中的 `must_know_ids` 支持以下格式：
```yaml
must_know_ids:
  - "7"
  - "11-15"    # 范围：11,12,13,14,15
  - "20"
```
解析器自动展开范围。同时支持数字列表格式 `["7", "11", "14", "15"]`。
