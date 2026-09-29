# knowledge-retrieval

## ADDED Requirements

### Requirement: 班级内检索
服务端 MUST 仅从登录会话读取班级，教师和学生可检索，未登录返回 401。
#### Scenario: 伪造 class_id
- WHEN A班用户提交 B班 class_id
- THEN 仅返回 A班候选；关键词与向量路径都必须隔离。

### Requirement: 可验证的切片
每个结果 MUST 提供材料标题、材料 ID、切片 ID、序号、字符区间、SQL 原文摘录与来源链接。
#### Scenario: 来源定位
- WHEN 打开某一命中来源
- THEN 原文的 [start_char,end_char) 与 excerpt 完全一致；跨班来源访问返回 404。

### Requirement: 三类检索
keyword MUST 不调用嵌入服务；vector MUST 使用 0.35 余弦阈值；hybrid MUST 使用 RRF 融合且为默认模式。
#### Scenario: 无依据
- WHEN 两条相关路径过滤后均没有候选
- THEN 返回 hits=[] 和“资料中未找到相关内容”，不调用生成模型。
#### Scenario: 服务不可用
- WHEN 向量服务不可用或本班索引尚未完成
- THEN vector/hybrid 返回 503 与可理解提示，keyword 仍可用；不得伪造空结果。

### Requirement: 兼容已有材料
上传 MUST 在 SQL 同事务写入原文、切片与词索引，向量后台幂等建立。已有正文启动时自动补切片。
#### Scenario: 迁移和重启
- WHEN 已有第3课数据库启动新版服务
- THEN 原材料与账号保留，切片自动建立，多次启动不重复插入。
