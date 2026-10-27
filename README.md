# 多应用、Skill 与 MCP 扩展（2026-10-27）

当前新增知识问答、教案设计、练习与计算三个 AI 应用。教师可在问答页选择应用，编辑应用绑定与提示词模板，上传 Markdown Skill。应用可绑定本班知识库，调用内置算术、管理员配置的 HTTP/MCP 工具；每次新应用对话提供“查看本轮 LLM 请求与响应”入口。

- [完整图文验证报告](reports/platform-verification-report.html)：三幅流程图、五项问题逐项验证、完整可展开 HTTP 报文。
- [原始证据](reports/verification-evidence.json) / [测试日志](reports/test-results.txt)：40 项测试中 39 项通过，1 项 Qdrant 依赖相关测试跳过；使用本机确定性 LLM/MCP 服务，不是商业模型效果验证。
- 新增 `platform_runtime.py`；原接口不传 `app_id` 时兼容旧问答路径。新增 traces 与工具执行只适用于新应用路径。

```sh
python3 run.py
CAMPUS_WRITE_EVIDENCE=1 python3 -m unittest discover -s tests -v
python3 tools/build_verification_report.py
```

外部工具从进程环境 `CAMPUS_EXTERNAL_TOOLS` 读取（本地启动需先 `export`，Compose 可通过 `env_file` 注入）。以下仅为接入格式示例，地址须替换为真实服务：

```sh
export CAMPUS_EXTERNAL_TOOLS='[{"id":"school","kind":"mcp","url":"http://127.0.0.1:9000/mcp","allowed_tools":["lookup"],"token_env":"SCHOOL_MCP_TOKEN"}]'
python3 run.py
```

接入后在应用 `tool_ids` 中绑定 `school__lookup`。HTTP 工具配置 `kind:http`、`url`、`description` 和 `inputSchema`，以 POST JSON 传参。MCP 适配 2025-06-18 HTTP 请求/响应及有限 SSE，含初始化、会话头、工具分页与调用；不含 stdio、OAuth 或持久 SSE 重连。工具采用基础参数校验，复杂 Schema 由工具服务校验。仅管理员配置外部端点；教师绑定已接入工具。

Skill 为单份 Markdown 声明式工作流（最多 16000 字符），绑定后每次传入全文，允许声明工具；不会运行上传的 Shell/Python，不支持 ZIP 技能包。提示词模板支持 `{{class_name}}`、`{{question}}`。知识库仅注入最多 4 个命中切片，无命中时不调用模型。工具结果经 `role:tool` 回传；最多执行 3 轮工具调用。审计日志保存对话及工具结果，不含认证请求头，目前需自行制定数据保留策略。

API：`GET /api/platform`；教师 `POST /api/platform/apps|templates|skills`；`POST /api/chat` 传 `{app_id, question, conversation_id?}`；`GET /api/traces/{id}` 仅本人本班可读。写请求仍需 Bearer 与 CSRF。

可选运行 `python3 tools/verification_demo.py` 打开 `http://127.0.0.1:8879/chat`，这是临时数据库与确定性模拟模型演示，不会访问真实 AI 网关。真实模型、第三方 MCP、真实向量和页面点击/视觉需另行验收。

---

# 第5课更新：AI 知识问答与流式会话

本轮在原系统上新增 AI 问答，同时完成 Bearer Token 登录改造。源码目录保留第4课检索功能。

## 本机体验

本轮演示服务运行在 `http://127.0.0.1:8768/chat`，避免占用已有8765服务。梁老师账号 `teacher` / `Campus2026!`；学生 `student` / 同一密码。

- 问“磁铁能吸引木块吗？”，回答来自真实课程网关，附[1]来源，可点击定位原文。
- 教师点击“提示词与技能”保存角色提示词、开关解题引导。下一轮生效；学生无权修改。
- 开启引导时只给思路和实验方法，关闭时直接回答。当前演示为匹配示意图关闭引导，新班级默认开启。
- 可连续追问；历史会话保存在SQLite，只属于当前用户和班级。
- 无命中直接提示，不调用模型。异常明确显示并标记该回答未完成。

## 配置与运行

代码包不含密钥、数据库和虚拟环境。复制 `.env.example` 为 `.env`，填课程网关自己的密钥；然后 `python3 run.py`（默认8765）。本机当前 `.env` 已配置。

```dotenv
AI_BASE_URL=https://ai-gateway.devops.hello1023.com/v1
AI_API_KEY=你的密钥
AI_MODEL=course-chat
AI_RETRIEVAL_MODE=keyword
```

本轮本机环境没有向量依赖，演示明确使用关键词检索。安装 `python3 setup_vector.py` 并等待索引就绪后，可将 `AI_RETRIEVAL_MODE` 改为 `hybrid`（推荐）。也支持 `vector`；向量不可用时明确报错，不静默降级。模型配置只从后端读取；Docker Compose通过env_file注入，密钥不会打包到镜像。启动会导入7份教学示例，科学材料明确标为演示资料。

调用课程网关时发送本轮命中的本班片段（最多4条）、教师提示词及最近12条完整历史消息。API密钥不返回前端，`.env` 已加入Git和Docker忽略规则。教师上传资料仍限TXT/Markdown。

## API与实现

- `POST /api/login` 返回 `access_token`、`token_type: Bearer`、`expires_in`。后续请求加 `Authorization: Bearer <token>`，旧Cookie不能认证；退出撤销Token。写请求还需 `/api/me` 返回的 `csrf`，放在 `X-CSRF-Token`。
- `GET/POST /api/ai/settings`：读取/教师修改本班提示词和引导开关。
- `POST /api/chat`：JSON `{question, conversation_id?}`，返回SSE `meta`（会话、真实来源）、`delta`（片段）、`done` 或 `error`。
- `GET /api/conversations`、`GET /api/conversations/{id}`：本人的会话与消息。
- 班级始终从服务端身份读取。一个用户同一时间仅允许一次生成；HTTP断开或上游失败时不把半截内容标成完成。
- 默认上下文限制最近12条完整消息。引导行为由模型提示词约束，并做真实开关验证；模型不是确定性程序，仍需教师审阅回答。

验证：`python3 -m unittest discover -s tests`。本轮30项测试，29通过、1项Qdrant依赖缺失跳过；另行调用真实课程网关验证流式回答、引导与追问。Docker配置未实际启动验证。

---

# CampusClaw · 第4课：可追溯的班级知识库检索

在第3课系统上继续实现，保留梁老师/A班及全部已有材料。新增正文检索、向量库、混合排序、原文溯源。当前架构是 **Python + SQLite/FTS5 + Qdrant + 本地 FastEmbed**；不是课件的 Go + MySQL 部署。

## 快速运行

如已安装向量依赖并缓存模型，可直接双击 `启动系统.command`；运行后打开 http://127.0.0.1:8765 。命令行也可以：

```sh
python3 run.py
```

`run.py` 自动优先使用项目 `.venv`。如果服务已经运行，直接访问网页，不要重复启动。

### 在新目录/另一台机器上使用代码包

1. 安装 Python 3.10 或更新版本（完整语义检索需要）。
2. 在项目目录执行：

```sh
python3 setup_vector.py
python3 run.py
```

macOS 也可依次双击 `安装向量检索.command`、`启动系统.command`。首次加载会下载约 220 MB 的多语言 ONNX 模型及 tokenizer 文件到 `data/models`，随后在本机生成向量。无需付费 API Key，教学材料不会发送到外部模型 API。项目代码包不包含虚拟环境、数据库、登录会话及大体积模型缓存。

模型下载或索引期间，UI 显示“索引准备中”；可以先选择关键词模式。没有安装向量依赖时仍可用 Python 3.9+ 启动关键词版；vector/hybrid 会明确提示服务不可用，不会静默冒充关键词结果。

启动导入器通过鉴权接口幂等导入六份随附教学示例；相同文件名不重复导入。已有用户上传文件和账号不会被覆盖。示例文件是演示教学资料。

## 演示账号

| 账号 | 密码 | 角色 | 班级 |
| --- | --- | --- | --- |
| teacher | Campus2026! | 梁老师 / 教师 | A班 |
| student | Campus2026! | 李同学 / 学生 | A班 |
| teacher2 | Campus2026! | 王老师 / 教师 | B班 |
| student2 | Campus2026! | 陈同学 / 学生 | B班 |

教师可上传、查看、下载、检索本班资料；学生可查看、下载、检索。角色、班级从服务端会话读取。密码仍为 PBKDF2-SHA256 加盐摘要，认证使用服务端可撤销的 Bearer Token（前端 sessionStorage 保存，8小时有效，数据库只保存摘要）；写请求还保留 CSRF 校验。默认端口只绑定本机地址。

## 使用方法

1. 登录后点击侧栏“班级知识库”。
2. 输入问题，例如“如何帮助学生清晰表达自己的观点”。
3. 选择关键词、语义向量或混合检索，默认混合。
4. 点击结果的“定位原文”：显示完整原始文本，高亮对应字符区间，可下载原文件。
5. 输入“量子纠缠与黑洞蒸发”可检查演示A班的无依据情况，页面显示“资料中未找到相关内容”。

### 三种模式

| 模式 | 实现 |
| --- | --- |
| keyword | SQLite FTS5 匹配正文 token；中文双字 token、英文单词。候选按班级过滤，结合词频和命中覆盖排序，不调用嵌入模型。 |
| vector | 本地多语言 MiniLM 生成 384 维向量，Qdrant 余弦检索，阈值 0.35。 |
| hybrid | 两条路径分别召回最多40个候选，使用 RRF(k=60) 融合，默认返回最多5个片段。 |

分数用于相关性排序，不表示答案正确率。0.35 是本次按课件采用的阈值；使用不同模型或资料领域时仍需评估。系统返回原文证据，不生成自由形式的 AI 答案。

### 切片和溯源

- 默认按800个 Unicode 字符切分，重叠100字符。
- 上传时可选换行、空行、句号、Markdown标题、自定义分隔符；短分段会在800字内合并，标题章节单独保留，超长章节继续切窗。
- SQL保存每片的稳定UUID、材料ID、班级、序号、起止偏移、原文与SHA-256。
- API偏移是Unicode code point的零基半开区间 `[start_char,end_char)`；页面展示一基闭区间。Emoji也按Unicode字符定位。
- 长切片按120字符子窗嵌入，向量平均并归一化，保证覆盖切片全文而非静默截断。
- Qdrant只存向量及 `class_id/material_id/body_hash` 标识；point ID 与 SQL chunk ID 相同，不存原文、标题。
- 命中后回SQL二次校验班级、材料关联、正文指纹，再返回摘录。来源接口也独立鉴权。

### 索引一致性

上传原文件、正文、切片和关键词索引同一SQL事务提交。向量后台幂等upsert，成功后标记ready。失败保留pending并自动重试；教师可点击重试。旧材料启动时补切片；重启重放向量索引，支持向量库恢复。模型/算法变更使用不同collection，避免混用向量。

某班尚有未完成的索引时，该班vector/hybrid返回503；keyword仍可用。服务失败不会返回伪造的“无相关内容”。

## API

浏览器可在同一登录会话下直接打开GET接口。

| 方法/地址 | 说明 |
| --- | --- |
| `GET /api/search?q=课堂表达&mode=hybrid&limit=5` | 检索；mode默认hybrid；limit为1–20；问题1–500字符。 |
| `GET /api/chunks/{chunk_id}` | 返回原文切片及整份原始正文，用于高亮溯源。 |
| `GET /api/retrieval/status` | 仅返回本班的切片总数、已索引数及服务状态。 |
| `POST /api/retrieval/retry` | 教师可重试索引，须会话和CSRF令牌。 |
| `POST /api/materials` | 原上传接口新增 `chunk_strategy` / `chunk_separator`。 |

检索结果含 `material_id/title/filename/chunk_id/chunk_index/start_char/end_char/excerpt/body_hash/matched_by/score/vector_score/source_url`。无命中为200、`hits: []`，消息“资料中未找到相关内容”。未登录401；跨班来源404；错误参数400；向量未就绪503。

请求中的 `class_id` 不参与权限判定，无论是keyword还是vector都只能检索会话班级。

## 配置

| 环境变量 | 默认 / 说明 |
| --- | --- |
| `CAMPUS_DATA_DIR` | 项目 `data/`，保存SQLite、Qdrant本地数据和模型。 |
| `CAMPUS_VECTOR_MODE` | 安装依赖后默认local；off仅关键词；remote连接Qdrant服务。 |
| `CAMPUS_MODEL_CACHE` | `data/models`。 |
| `QDRANT_URL` | remote模式默认 `http://qdrant:6333`。 |
| `QDRANT_API_KEY` | 可选，只从环境读取。 |
| `CAMPUS_PORT` | run.py监听端口，默认8765。 |
| `CAMPUS_HOST` | 本机默认127.0.0.1，Docker内部0.0.0.0。 |
| `CAMPUS_SECURE_COOKIE` | HTTPS部署设为1。 |

当前代码固定采用支持的多语言MiniLM模型；如通过 `CAMPUS_EMBED_MODEL` 更换模型，必须选择FastEmbed支持且无需query/document前缀的模型，并重新验收召回质量。

## Docker（可选，当前环境未运行验证）

默认Qdrant本地模式，与应用同一进程，无须独立容器：

```sh
docker compose up --build
```

使用独立Qdrant服务：

```sh
docker compose -f compose.yaml -f compose.vector.yaml up --build
```

独立Qdrant没有 `ports` 映射，仅在Compose网络内可达。应用仍只发布 `127.0.0.1:8765`。数据与向量分别持久化。生产使用应选择经过验证的固定Qdrant镜像版本；当前可选配置使用官方latest镜像，未执行容器集成验收。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/verify_real_vector.py
```

Windows对应 `.venv\Scripts\python.exe`。第一条共24项自动化检查（含原10项回归）；不下载模型。第二条使用真实模型和临时SQL/Qdrant目录，验证改写语义召回、跨班拒绝、无依据空结果、来源偏移及向量payload不含正文。

测试不会修改已有材料。详见 `第4课验收记录.md`。

## 文件

- `server.py`：会话、上传/下载、检索与来源API。
- `retrieval.py`：切片、迁移、全文检索、嵌入、Qdrant、RRF。
- `web/retrieval-ui.js`：检索及来源高亮界面。
- `setup_vector.py` / `requirements-vector.txt`：项目内向量环境安装。
- `openspec/changes/add-traceable-vector-retrieval/`：本次变更范围、设计及验收场景。

原第3课说明与验收记录保留用于历史对照。未运行课程OpenSpec CLI validate/archive，也未实施Go/MySQL迁移。


## 2026-10-27 功能审查与真实调用验证

补全旧聊天接口追踪、历史追踪、失败记录、MCP协议过程及 .env 工具配置。报告、9张真实截图和 live-*.json 位于 reports/20261027。自动化43项：42通过，向量依赖缺失跳过1项。真实验证使用 keyword 检索。

隔离演示：python3 tools/run_live_verification.py，访问 http://127.0.0.1:8890/chat，账号 teacher / Campus2026!。需要配置 .env 网关；隔离数据保存在 data/verification。MCP演示是本地实际认证服务。

Skill为完整文本提示指令，不执行上传脚本。MCP支持HTTP JSON/有限SSE，不包含stdio、OAuth或全部JSON Schema校验。
