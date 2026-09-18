# 前端布局与中英文

顶部可切换中文 / English 及深色 / 浅色 / 系统主题，偏好保存在浏览器本地。
语言切换不重载页面，不改变输入值、文件路径、规则名称、报文数据或正在运行的任务。

布局采用侧栏导航、标签在上的表单分组及独立横向滚动的表格。
720px 以下导航转为顶部横向排列；减少动态效果的系统偏好会禁用过渡动画。
Tab 可聚焦导航，方向键及 Home / End 可切换页面。

`web/i18n.js` 管理中英词典和动态状态模板，原始中文绑定支持双向切换。
仅翻译界面文本和 placeholder / title / aria-label，不处理输入 value。
动态数据单元格默认排除；纯界面状态须显式标记 `data-ui`。
接收数据体不进入常规文本遍历，帧类型使用单独的呈现标记。
用户名称、DBC/场景内容及后端原始错误详情保持原文，以免改变诊断信息。
系统文件对话框和文件选择控件由操作系统/浏览器语言决定。

测试：

```
npm install --prefix build/ui-test-tools --no-save --package-lock=false jsdom
node tests/i18n_check.cjs
node tests/i18n_trigger_dom_check.cjs
node tests/trigger_editor_check.cjs
node tests/analysis_ui_check.cjs
.venv\Scripts\python.exe -m pytest -q
```

DOM 测试不等同于浏览器截图或真实窗口布局验收。
