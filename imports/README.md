# PDF 自动导入说明

将 PDF 上传到本仓库的 `imports/` 文件夹，工作流会将其逐页转为 PNG，生成 `/exams/<filename>/index.html`，并自动部署 GitHub Pages。

首次配置请在 Settings → Pages → Build and deployment → Source 选择 **GitHub Actions**。此后每次向 main 分支上传 PDF，Actions 会重新构建网站，无需单独上传图片。

**2021 华科 831 的特殊约定**：请将原 PDF 重命名为 `2021-hust-831.pdf` 后上传到 `imports/`。转换器会将其前 6 页映射为 `assets/source-page-1.png` 到 `source-page-6.png`，后 7 页映射为 `assets/answer-page-7.png` 到 `answer-page-13.png`，自动补全原有的年度页面图片。

其他 PDF 上传后会自动出现按页浏览页面。若已知题目和答案的分界，可额外创建与 PDF 同名的 JSON，例如 `imports/2022-example.json`：
```json
{"title": "2022 示例真题与详解", "question_pages": 5}
```
未提供 JSON 时，所有页面均按原 PDF 页序连续显示，不会臆测哪页是答案。

**注意**：本仓库是公开的，放入 `imports/` 的 PDF 会公开存储在 GitHub 仓库中，仅上传有公开分享许可且不含敏感信息的资料。

普通 PDF 最多支持多少页和体积取决于 GitHub 上传限制及 Actions 资源配额。用户需要核对复杂电路图、答案归属和可能有误的解析。
