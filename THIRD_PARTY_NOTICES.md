# 第三方组件与素材

本项目调用第三方库，不将其声称为原创。各库和其分发内容保留原许可证。完整的已安装依赖版本见 requirements.txt，构建依赖见 mac/requirements-build.txt。

| 组件 | 用途 | 许可证 / 官方项目 |
| --- | --- | --- |
| SQLGlot | Spark SQL 解析与作用域分析 | MIT — https://github.com/tobymao/sqlglot |
| SQLFluff | Spark SQL lint 与格式修复 | MIT — https://github.com/sqlfluff/sqlfluff |
| Flask | 本地 HTTP API | BSD-3-Clause — https://github.com/pallets/flask |
| Werkzeug | 本地服务 | BSD-3-Clause — https://github.com/pallets/werkzeug |
| PyInstaller | 打包 Python 运行时 | GPL-2.0-or-later with bootloader exception — https://github.com/pyinstaller/pyinstaller |
| Python | 打包运行时 | PSF — https://www.python.org/psf/license/ |

这些核心组件的许可证副本位于 `third_party_licenses/`；其他间接依赖按其发行包内的许可证使用。Mac 安装包保留收集到的依赖包元数据和许可证。

图标使用 imagegen 生成，主题为小写 sql、编辑笔、格式化代码与光芒；原图及设计提示词位于 mac/assets/。界面截图仅使用合成 SQL。
