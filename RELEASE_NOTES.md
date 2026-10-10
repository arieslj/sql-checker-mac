# SQL 检查器 for Mac v1.0.5 — 修复 macOS 兼容性

修复 v1.0.4 主程序意外编译为最低 macOS 27.2，导致 M 系列 Mac 显示“不能与此版本的 macOS 配合使用”的问题。

- 主程序显式编译为 arm64 / macOS 14。
- 应用声明与内置 Python 的最低要求统一为 macOS 14。
- 所有打包 arm64 Mach-O 二进制均进行最低系统版本审计；发现超出声明的依赖时构建会失败。
- 保留高优先级 on 关联检测、检查、格式化、复制以及启动优化。

支持 Apple Silicon 架构，包括 M4。运行要求 macOS 14 或更新版本；Intel 无对应安装包。本次完成最低版本静态审计、当前开发机器运行与功能测试；未在每一种 M 系列芯片和 macOS 版本上实机测试。应用未做 Apple Developer ID 签名/公证。

请下载 `SQL-Checker-macOS-AppleSilicon-v1.0.5.zip`，退出旧应用后替换。无需 Python 或终端。附源码 ZIP 和 SHA-256 校验文件。

SQL 完全本地处理，不执行 SQL，不上传、不保存 SQL，不能代替真实数据库的字段、类型和 DLI 执行验证。
