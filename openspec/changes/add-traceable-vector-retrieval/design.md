# Design

1. SQLite `knowledge_chunks` 是原文切片与权限的事实来源；使用 Unicode code point 的零基半开区间 `[start_char,end_char)`。UI 显示一基闭区间。默认窗口 800，重叠 100；按分隔符的短段在 800 字内合并，Markdown 标题保留章节边界；超长章节继续切窗。
2. UUID5 ID 来源于材料 ID、起始偏移与切片 SHA-256。Qdrant point ID 与 SQL chunk ID 相同。payload 仅存 class_id、material_id、body_hash，绝不存正文或标题。
3. SQL 全文索引用 FTS5；中文采用可复现的双字 token，英文采用单词。先在 SQL 中限定 class_id 再返回候选；至少匹配 1 或 2 个非停用词 token，排序以命中词及词频为准。这是本地版的实现选择，并非 MySQL FULLTEXT。
4. FastEmbed 使用多语言 MiniLM ONNX 模型在本机推理，不调用远程嵌入 API。800 字切片按 120 字子窗嵌入并取平均归一化，覆盖整个切片，不依赖静默截断。查询采用相同向量算法。
5. Qdrant 在检索时必须传 class_id 过滤，并使用余弦阈值 0.35。回 SQL 时再次校验班级、材料关联及正文指纹，防止向量库陈旧/错误 payload 泄露。
6. hybrid 使用 RRF(k=60)，独立排名融合。无候选返回 hits=[] 及“资料中未找到相关内容”。向量服务错误/索引未完成返回 503，不能伪装成无命中，也不静默改为 keyword。
7. SQL 原文件、正文、切片和 FTS 在同事务提交。向量异步写入；成功后标记 ready。失败保留 pending 并自动重试，upsert 幂等。重启时重放索引以恢复向量库丢失；collection 名包含模型与算法指纹，避免混用不同模型。数据库迁移为新增表和索引，不重写原材料。
8. 本地 Qdrant 客户端与嵌入模型受线程锁保护。SQLite 连接按请求创建。默认 local，设置 CAMPUS_VECTOR_MODE=remote 可使用 Compose 中 Qdrant 服务。无向量依赖时 keyword 仍可单独工作，页面明确提示未启用向量。
