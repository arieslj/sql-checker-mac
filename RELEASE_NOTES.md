# SQL 检查器 v1.0.7 — 补全 DLI 多维分组一致性

修复上一版遇到 rollup/cube/grouping sets 整体跳过检查的缺陷。

- 车型表达式 + 原因 + count，但 rollup 只有车型表达式：最高优先级指出原因漏分组。
- 同时支持函数式与 WITH ROLLUP/CUBE、GROUPING SETS 前缀写法、空集合、tuple、嵌套及混合维度。
- 按已声明维度的全集核对，不把合法汇总行中的 NULL 当成未分组错误，也不指数展开 cube。
- 核对 grouping()/grouping_id() 上下文与参数、having/order by 未分组字段、where 直接聚合和显式集合遗漏前置维度的 NULL 风险。

官方文档依据及覆盖边界见仓库 docs/dli-grouping-coverage.md。不会自动增删分组项或修改统计粒度。字段、类型、DLI 引擎版本和配置仍须真实环境验证，不承诺全面替代 DLI。

133 项 Python 回归测试、原生通信、打包引擎和兼容性审计通过。用例为合成 SQL，不公开业务 SQL 或真实数据。

下载 SQL-Checker-macOS-AppleSilicon-v1.0.7.zip，退出旧版后替换。Apple Silicon / macOS 14+；未进行 Apple Developer ID 签名/公证。附源码 ZIP 和 SHA-256 校验文件。
