# Mac 应用构建

普通使用者直接下载 [Release](https://github.com/arieslj/sql-checker-mac/releases) 中的 ZIP，解压后双击应用，无需安装依赖。

## 构建环境

需要 Apple Silicon Mac、Xcode Command Line Tools 与 Python 虚拟环境。在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r mac/requirements-build.txt
bash mac/build.command
```

产物：`mac/dist/SQL 检查器.app` 与 `mac/SQL-Checker-macOS-AppleSilicon-v1.0.6.zip`。

PyInstaller 包含 Python 运行时与依赖；Swift AppKit / WebKit 提供原生窗口。构建脚本生成多尺寸 ICNS 图标，完成临时本地签名。没有 Developer ID 签名或 Apple 公证，不适用于 App Store 分发。

## 打包验证

```bash
python3 mac/smoke_test.py
python3 mac/test_frozen_multiprocessing.py
node mac/test_bridge.cjs
python3 mac/check_compatibility.py 'mac/dist/SQL 检查器.app'
codesign --verify --deep --strict 'mac/dist/SQL 检查器.app'
```

烟雾测试使用合成 SQL，包含高优先级关联检测；资源跟踪器测试验证后台辅助进程不会重新启动服务。原生窗口退出时停止内置服务和相关会话。

性能测量：

```bash
python3 mac/benchmark_startup.py 'mac/dist/SQL 检查器.app/Contents/Resources/backend/SQLCheckerBackend/SQLCheckerBackend' 5
```

该脚本只衡量本地后端准备与合成 SQL 首次检查，不等同于整个 Mac 窗口启动耗时。[详细结果](startup-performance.md)。正式构建不会记录启动测量或保存 SQL。

所有打包 arm64 二进制的最低系统版本已经审计，不高于 macOS 14；主程序显式以 arm64-apple-macos14.0 编译。最低要求 macOS 14，支持 M 系列架构。仅本机完成实机验证；Intel 和跨机器运行未验证。DLI 实际执行不属于离线测试范围。
