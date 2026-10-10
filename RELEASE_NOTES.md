# SQL 检查器 for Mac v1.0.4

新增高优先级 on 别名关联检测。

- 连接 a6 时，`on a6.area = a1.area and a5.region = a1.region` 会优先提示核对第二项，建议是否改为 `a6.region = a1.region`。即使 a5 已定义，也能识别。
- 检测 on 未引用当前 join 表，以及引用后续才加入的表别名。
- 清单优先展示，标记「优先处理」，复制清单保留该标记。
- 保留合法历史表别名连接、嵌套作用域与复杂条件；不自动修改业务逻辑。

高优先级关联风险不等同于确定性语法错误：历史表条件可能是有意的业务过滤，需要人工确认。完整字段/类型与 DLI 执行仍需数据库验证。

下载 `SQL-Checker-macOS-AppleSilicon-v1.0.4.zip`，退出旧版后替换。无需 Python 或终端，离线本机运行。仅 Apple Silicon 验证，尚未做 Apple Developer ID 签名/公证。

40 项 Python 测试及打包、原生界面验证通过。附源码 ZIP 和 SHA-256 校验文件。全部测试使用合成 SQL，没有发布或访问业务 SQL / 数据。
