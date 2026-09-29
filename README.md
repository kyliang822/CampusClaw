# CampusClaw · 第4课：可追溯的班级知识库检索

在第3课系统上继续实现，保留梁老师/A班及全部已有材料。新增正文检索、向量库、混合排序、原文溯源。当前架构是 **Python + SQLite/FTS5 + Qdrant + 本地 FastEmbed**；不是课件的 Go + MySQL 部署。

## 快速运行

这台机器上已经安装向量依赖并缓存模型，可直接双击 `启动系统.command`；运行后打开 http://127.0.0.1:8765 。命令行也可以：

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

教师可上传、查看、下载、检索本班资料；学生可查看、下载、检索。角色、班级从服务端会话读取。密码仍为 PBKDF2-SHA256 加盐摘要，会话为 HttpOnly Cookie。默认端口只绑定本机地址。

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
