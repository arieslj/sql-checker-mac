# SQL 检查器 for Mac

<img src="mac/assets/sql-checker-icon-v2.png" width="112" alt="SQL 编辑和美化图标">

面向华为云 DLI / Spark SQL 的本地 SQL 检查与美化工具。直接粘贴 SQL，查看按行号定位的错误、风险和修改建议；支持小写关键字、前置逗号格式化，以及复制 SQL / 检查清单。

**SQL 在本机处理，不执行 SQL、不连接数据库、不上传或保存 SQL。**

## 下载与使用

[下载 Mac 应用 v1.0.3（Apple Silicon / M 系列）](https://github.com/arieslj/sql-checker-mac/releases/download/v1.0.3/SQL-Checker-macOS-AppleSilicon-v1.0.3.zip) · [全部 Release](https://github.com/arieslj/sql-checker-mac/releases)

解压后将「SQL 检查器.app」拖入「应用程序」，双击使用。无需安装 Python、无需终端、不需要联网。升级时先退出旧版再替换。

应用使用临时本地签名，尚未完成 Apple Developer ID 签名/公证；macOS 首次打开时可能要求确认。仅 Apple Silicon 版本在开发机器完成验证，Intel Mac、其他电脑和较旧 macOS 未验证。

![应用界面（合成示例）](mac/startup-preview.png)

## 检查能力

复用 [SQLGlot](https://github.com/tobymao/sqlglot) 的 Spark 解析器与 [SQLFluff](https://github.com/sqlfluff/sqlfluff) 的 sparksql 格式检查，增加保守静态规则：

| 类型 | 检查内容 |
| --- | --- |
| 确定性语法错误 | SQL 代码中的中文全角标点、group by 末尾多余逗号 |
| 解析器报错 | SQLGlot 解析失败，带行号和列号；需核对 DLI 专有语法 |
| 静态结构问题 | 当前或外层作用域未定义的表别名 |
| 静态风险 | 两侧同字段的 join 条件、可能除零、未分组的非聚合输出、日期区间边界 |
| 数据库验证提示 | join 连接键重复导致的潜在行数放大 |
| 格式建议 | SQL 关键字小写、前置逗号、四空格缩进与空格 |

支持 `${dt}`、`${month_1}` 等简单模板，检查时等长替换以保留位置，格式化后恢复原文。支持 Spark 常见函数调用与中文反引号别名。未知 DLI 函数可以作为普通调用解析，但不验证函数存在性和参数类型。

**静态检查不能完全代替 DLI。** 表和字段存在性、类型、权限、函数签名、分区、连接基数和执行计划必须在数据库验证。解析成功不表示 SQL 能在 DLI 执行。

join 提示不表示已确认行数放大。除零检测只明确识别 `nullif` 防护，`case when` 等防护可能仍收到提示。复杂分组表达式、分组序号、rollup/cube/grouping sets 的覆盖有限。日期提示不能推断真实字段类型；完整 Jinja / 动态 SQL 不支持。

格式化通过词法 token、字面量、引用标识符和注释比较，拒绝结构变化或无法解析的输入。格式化后需要重新检查。单次 SQL 上限为 50,000 字符。

## 启动优化

v1.0.3 让界面直接从应用内文件加载，检查引擎后台预热；准备期间可以输入 SQL，不刷新页面或覆盖输入。修复冻结应用后台辅助进程错误启动服务的问题。

本机一次测量：从应用主程序开始，编辑界面约 1.14 秒可用，引擎约 1.44 秒就绪。不包含 macOS 启动前的首次安全检查，也不保证其他电脑的速度。立刻点击检查仍可能短暂等待引擎。[测量方法与边界](mac/startup-performance.md)。

## 从源码运行网页版

需要 Python 3.9 或更新版本；推荐使用独立虚拟环境。首次安装依赖需要联网，运行时不需要。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

打开 http://127.0.0.1:8765 ，按 Ctrl+C 停止。也可以双击 `start.command`，或在项目目录执行 `bash start.command`。

网页版仅监听 127.0.0.1，限制 Host / 跨站 Origin，不加载 CDN、遥测或外部资源。Mac 应用通过原生桥接访问本机临时端口，并使用不持久化的 WebKit 会话。复制操作写入系统剪贴板。请勿将服务改为公网监听。

## 测试与打包

```bash
.venv/bin/python -m pytest -q
node mac/test_bridge.cjs
```

本机 23 项 Python 测试通过，覆盖检测规则、作用域、行号、模板、格式化、API 验证及轻量启动。原生通信成功/错误/超时/网页版回退、冻结进程和实际 Mac 窗口操作已验证。全部使用合成 SQL，没有读取业务数据。

[Mac 构建与打包说明](mac/README.md)。仓库附有自动测试工作流。CI 的结果以 GitHub Actions 实际运行结果为准。

## 第三方组件

SQLGlot、SQLFluff 使用 MIT 许可证；Flask、Werkzeug 使用 BSD 许可证；PyInstaller 使用 GPL 及打包产物例外许可。[第三方说明](THIRD_PARTY_NOTICES.md)。本项目暂未指定独立源码许可证。
