# SQL 检查器 for Mac v1.0.3

首次公开发布：面向 DLI / Spark SQL 的本地检查、修改建议与 SQL 美化工具。

## 下载使用

下载 `SQL-Checker-macOS-AppleSilicon-v1.0.3.zip`，解压后将「SQL 检查器.app」拖入「应用程序」，双击使用。无需安装 Python、无需终端、不需要联网。仅提供 Apple Silicon / M 系列版本。

`sql-checker-mac-source-v1.0.3.zip` 包含源码、README、requirements、启动与构建脚本、合成示例及测试。

## 功能

- SQLGlot Spark 解析、SQLFluff sparksql 检查。
- 按行号定位，显示级别、原因和修改建议。
- 全角标点、group by 尾逗号、错误 join 条件、未定义别名、除零、非聚合字段、日期边界、join 放大风险提示。
- `${dt}` / `${month_1}` 模板兼容，小写关键字、前置逗号格式化与复制。
- 原生 Mac 窗口和 SQL 编辑、美化图标。
- 界面直接加载，后台预热引擎；修复冻结后台辅助进程初始化。

## 验证与边界

23 项 Python 测试以及原生通信、冻结进程、打包烟雾测试通过；全部采用合成 SQL。实际 Mac 窗口内的检查、格式化、复制及退出已验证。

SQL 只在本机处理，不保存、不上传、不执行 SQL，不连接真实业务数据。字段、类型、函数签名和 join 基数需要数据库验证，不能完全代替 DLI。

仅本机 Apple Silicon 验证，其他 Mac 环境未验证；未做 Developer ID 签名或 Apple 公证，首次打开可能出现 macOS 确认提示。

校验文件：`SHA256SUMS.txt`。
