# Cram Engine — AI 考前速成引擎

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/liaozhe789/cram-engine)](https://github.com/liaozhe789/cram-engine)

基于 **SM-2 间隔复习** + **知识图谱拓扑排序** + **硬性状态机** 的 AI 考前速成系统。为 [Codex](https://github.com/openai/codex) 设计，将往年真题、教材重点、老师题目摄入后自动构建知识图谱，按依赖关系和权重调度学习路径，四阶段闭环确保不跳阶段、不逃补漏、不错必考点。

---

## 核心设计

```
cram load          cram next (循环)
   |                  |
   v                  v
配置向导 ──→ 阶段0 诊断 ──→ 阶段2 讲授 ──→ 阶段3 检题 ──→ 阶段4 补漏
                |                    ^              |
                |                    |              v
                +──→ 阶段5 复习 ←────+──────→ 全部完成
```

### 六阶段状态机

| 阶段 | 动作 | 说明 |
|------|------|------|
| 0 | 诊断 | 5 档自评 或 8-10 题诊断卷，生成逐知识点掌握图谱（strong/developing/weak） |
| 1 | 拆解 | cram load 期间确认知识图谱拓扑顺序 |
| 2 | 讲授 | 四步费曼教学法，讲授深度综合用户水平 + 知识点掌握度 + must_know 权重自适应 |
| 3 | 检题 | 六种题型全覆盖，must_know 6-8 题 / key_point 4-6 题，含陷阱题和交叉复检 |
| 4 | 补漏 | 诊断根因 → 换讲法 → 重测，must_know 连续两次全对方可过关 |
| 5 | 复习 | SM-2 到期自动调度，三步闪回复习 |

硬性约束：阶段 3 存在答错 must_know 时禁止结束，强制进入阶段 4。

---

## 功能

### 资料摄入
- 支持 PDF（多后端自动提取：pdfplumber → PyPDF2 → pdfminer）、图片（Vision OCR）、Markdown/纯文本
- 自动清洗、分段、索引

### 知识图谱构建
- 自动推断知识点父类目和前置依赖（中英文双语关键词匹配）
- 支持 config 显式声明 `prerequisites`，精确控制学习顺序
- 拓扑排序：must_know 优先出队

### SM-2 间隔复习
- 完整实现 SM-2 算法：interval 递推、ease 因子衰减、遗忘重置
- must_know 节点评分更严格
- 阶段 2 中降频触发（累积 < 3 且无超 2 天未复习时不打断讲授）

### 自适应讲授
- 诊断阶段生成 `knowledge_map`：逐知识点 strong/developing/weak
- 阶段 2 按掌握度 + 权重动态调整：
  - strong + key_point → 快速回顾
  - weak + must_know → 放慢节奏，多场景例子
  - must_know 无论掌握度都完整讲一遍

### 题型覆盖
选择题、判断题、简答题、案例分析、情景应用、名词解释、编程/计算题、公式推导

### 记忆钩子
口诀（acronym）、对比表（contrast）、荒诞锚定（absurd）——自动推断最适合的类型

### 中英文双语
`config.yaml` 中设 `language: en` 即可切换。模板自动适配，indexer 双语关键词匹配。

---

## 快速开始

### 1. 加载课程
```
cram load
```
按引导输入课程名、教材、知识点列表、题型、must_know 编号。

### 2. 诊断测试
```
cram next
```
系统自动调度阶段 0：可选择"做一套诊断题"或直接自评水平（5 档）。

### 3. 持续学习
```
cram next    # 核心命令，每次执行一轮教学/检题/复习
cram status  # 查看进度全景
cram retry 知识点名  # 重走单个知识点的讲→测→补闭环
```

---

## 配置参考

`configs/<课程名>.yaml`：

```yaml
course: 数据结构
subject_type: engineering      # engineering / liberal_arts
language: zh                   # zh / en
textbook: "《数据结构》"
exam_types:                    # 考试题型
  - 选择题
  - 简答题
  - 算法设计题

key_points:                    # 知识点列表
  - 算法时间复杂度分析
  - 单链表的定义与基本操作
  - 二叉树的遍历

must_know_ids:                 # 必考点编号（1-based，支持范围 "3-5"）
  - "7"
  - "14-16"
  - "22"

# 可选：显式前置依赖（覆盖自动推断）
prerequisites:
  "5": ["critical-section-problem"]
  "8": ["semaphores-and-mutex"]

preferences:
  language: zh
  grading_strictness: strict
  example_domains:
    - 校园生活/学生管理系统
```

---

## 文件结构

```
cram-engine/
├── SKILL.md                     # Codex skill 主控文档
├── README.md
├── configs/                     # 课程配置
│   ├── example.yaml             #   英文示例（Operating Systems）
│   ├── 数据结构.yaml
│   └── ...
├── knowledge/                   # 知识图谱 + 摄入资料
│   └── <课程名>/
│       ├── index.json           #   节点、依赖、拓扑顺序
│       ├── raw/                 #   原始文件（PDF/图片）
│       └── extracted/           #   提取文本
├── progress/                    # 学习进度（含 SM-2 状态、knowledge_map）
│   └── <课程名>.json
├── scripts/                     # Python 核心脚本
│   ├── utils.py                 #   公共工具（SM-2、YAML、JSON、路径）
│   ├── ingest.py                #   资料摄入
│   ├── indexer.py               #   知识图谱构建
│   ├── progress.py              #   进度持久化
│   ├── scheduler.py             #   课程调度器
│   └── test_sm2.py              #   SM-2 算法测试（9 cases）
└── templates/                   # 阶段教学模板
    ├── stage0-diagnostic.md     #   诊断测试
    ├── stage1-deconstruct.md    #   知识图谱拆解
    ├── stage2-teach.md          #   四步费曼教学
    ├── stage3-test.md           #   六模式检题
    ├── stage4-remediate.md      #   闭环补漏
    └── stage5-review.md         #   SM-2 复习
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| 状态机 | `progress.json` 硬约束，`scheduler.py` 优先级调度 |
| 知识图谱 | `indexer.py` 双语关键词匹配 + 拓扑排序 |
| 间隔复习 | `utils.py` 完整 SM-2 实现 |
| 教学执行 | Codex LLM 按 `templates/` 模板驱动 |
| 资料处理 | pdfplumber / PyPDF2 / pdfminer 三级回退，Vision OCR |

---

## License

MIT — 随便用，随手点个 ⭐ 就更好了。
