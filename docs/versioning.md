# 版本与图标

版本号唯一来源：`app/build_info.py` 的 `APP_VERSION`，当前为 `1.1.1`。
页面通过 `/api/version` 获取版本。OpenAPI、状态接口和 Windows EXE 文件/产品版本使用同一值。
构建标识另行计算，包含版本号与前端资源内容，用来防止启动器复用旧界面进程。

图标源文件：`web/icon.svg`。浏览器标签页和页面标题使用 SVG，Windows EXE 使用多尺寸 `web/icon.ico`。
如修改 SVG，重新运行 `node scripts/build-icon.cjs`，然后重新打包。依赖安装命令写在脚本顶部。
ICO 包含 16、20、24、32、48、64、128、256 像素图像。

PyInstaller spec 同时写入应用图标与 Windows 版本资源。发布时应复制完整目录，不能单独移动 EXE。
