# JSON 格式化与检查器

检查 JSON 配置、接口响应和导出文件，按 2/4 个空格排版或压缩结构空白。保留键顺序、数字原写法及字符串转义，适合需要保留大整数精度的文件。

## 下载

[Windows x64 EXE](https://github.com/9999999-svg/json-formatter/releases/download/v1.0.0/JsonFormatter.exe) · [Python 源码 ZIP](https://github.com/9999999-svg/json-formatter/releases/download/v1.0.0/json-formatter-source-v1.0.0.zip) · [SHA-256 清单](https://github.com/9999999-svg/json-formatter/releases/download/v1.0.0/SHA256SUMS.txt)

EXE 约 12.5 MiB，内含 Python/Tcl/Tk，无需安装 Python，未签名。全部功能免费；自有代码 MIT，第三方许可随包提供。

## 使用

双击 EXE，选择输入 JSON 和新输出文件，设置缩进或压缩模式，点击「检查 / 预览」或「保存新文件」。预览最多 50000 字符；保存会重新读取输入。原文件保留，已有输出文件拒绝覆盖。

```powershell
python json_formatter.py "中文输入.json"
python json_formatter.py "中文输入.json" --output "格式化.json" --indent 4
JsonFormatter.exe "输入.json" --output "紧凑.json" --compact
```

命令行输出 JSON 状态，退出码 0 表示成功、2 表示失败、130 表示键盘中断。不带参数打开窗口。

## 必要限制

- 输入 UTF-8（可带 BOM），最多 10 MiB、64 层嵌套；输出 UTF-8 无 BOM，最多 50 MiB。
- 拒绝重复对象键、NaN/Infinity、注释、尾随逗号和多个顶层值；不处理 JSONL、GBK 或 UTF-16。
- 只改变结构空白。字符串内空格、转义、键顺序、数字大小写和小数位保持；不排序键或转换数值。
- 输入、输出父目录必须为普通路径，拒绝链接及目录联接。输出写入新文件，正常失败或取消会清理临时文件；强制结束进程可能留下 `.json-format-*.tmp`。
- 这是格式检查，不检查 JSON Schema，也不保证配置内容适合某个应用。

## 源码和构建

Python 3.11+，仅使用标准库和 Tkinter。使用已有虚拟环境可直接运行源码；构建需要 PyInstaller 6.21.0：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install pyinstaller==6.21.0
.venv\Scripts\python.exe build.py
```

EXE 在 `dist/JsonFormatter.exe`。依赖版本、体积和卸载见 [DEPENDENCIES.md](DEPENDENCIES.md)，第三方许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。卸载便携版直接删除 EXE；自行建立的虚拟环境可在关闭程序后删除。

## 自愿赞助

下载、源码和全部功能免费，赞助完全自愿。

<img src="assets/donate-wechat.png" alt="自愿微信赞助二维码" width="280">
