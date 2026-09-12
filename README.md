# PyTableEnginePluginRepository / 思能快表引擎插件中心仓库

## 简介 / Introduction

本仓库用于集中索引与自动化注册第三方插件，以支持 [PyTableEngine](https://github.com/IYATT-yx/PyTableEngine) 工具。  
如有疑问，请前往 PyTableEngine 仓库提交 Issue，本仓库只接收插件注册申请（自动审批）。  

GitHub 仓库地址：https://github.com/IYATT-yx/PyTableEnginePluginRepository  
配置中应填写：https://raw.githubusercontent.com/IYATT-yx/PyTableEnginePluginRepository/main/index.json  

Gitee 仓库地址（大陆建议）：https://gitee.com/iyatt/PyTableEnginePluginRepository  
配置中应填写：https://gitee.com/iyatt/PyTableEnginePluginRepository/raw/main/index.json  

---

This repository is used to centralize the indexing and automated registration of third-party plugins to support the [PyTableEngine](https://github.com/IYATT-yx/PyTableEngine) tool.  
For questions, please submit an Issue to the PyTableEngine repository. This repository only accepts plugin registration requests (automatically approved).  

GitHub Repository: https://github.com/IYATT-yx/PyTableEnginePluginRepository  
Configuration should be filled: https://raw.githubusercontent.com/IYATT-yx/PyTableEnginePluginRepository/main/index.json  

Gitee Repository (recommended for mainland China): https://gitee.com/iyatt/PyTableEnginePluginRepository  
Configuration should be filled: https://gitee.com/iyatt/PyTableEnginePluginRepository/raw/main/index.json  

##  向本插件中心仓库提交插件 / Submit a plugin to this plugin center repository

1. 只允许在 Github 仓库提交插件，Gitee 仓库仅作为镜像仓库，不接收插件提交。  
2. 如需提交插件，请前往 [Issues](https://github.com/IYATT-yx/PyTableEnginePluginRepository/issues) 发起 [New issue](https://github.com/IYATT-yx/PyTableEnginePluginRepository/issues/new)。title 为插件 ID，ID 格式为`作者名_插件名`（插件的项目名和入口程序名也必须使用 ID 命名，且入口程序文件中必须包含匹配的作者名和插件名信息，详见[PyTableEngine](https://github.com/IYATT-yx/PyTableEngine)），具有唯一性。description 填写 GitHub 仓库地址即可，不允许包含其它文字。  
3. 如果插件存在更新，请前往 Issues 曾经提交过的 issue 下发`update`评论即可触发更新收录，不允许重新提交 Issue  
4. 注意插件仓库中只允许后缀：.py、.txt、.md、.gitignore、.json、.yaml、.yml、.toml、.ini、.cfg、.LICENSE、.cmd、.bat、.ps1、无扩展名文件，且需通过非二进制文件检测，否则将无法收录（Issue 中自动校验后会回复结果）。  
5.Github 账号注册时间少于 7 天的用户提交的注册将不予采纳。  

---

1. Plugin submissions are only accepted on the GitHub repository. The Gitee repository serves purely as a mirror and does not process plugin submissions.
2. To submit a plugin, please go to [Issues](https://github.com/IYATT-yx/PyTableEnginePluginRepository/issues) and create a [New issue](https://github.com/IYATT-yx/PyTableEnginePluginRepository/issues/new). The issue title must be the unique Plugin ID in the format `AuthorName_PluginName` (the project name and entry script name must also use this ID, and the entry script file must contain matching author and plugin name metadata; see [PyTableEngine](https://github.com/IYATT-yx/PyTableEngine) for details). The description should contain only the GitHub repository URL, with no additional text.
3. If an update is available for a plugin, simply post an `update` comment under the original submission issue to trigger the update indexing process. Do not submit a new issue.
4. Only non-binary files with the following extensions are permitted in the plugin repository: `.py`, `.txt`, `.md`, `.gitignore`, `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.LICENSE`, `.cmd`, `.bat`, `.ps1`, or files without extensions. Submissions failing the non-binary file validation will not be indexed (automated check results will be posted in the issue response).
5. Submissions from GitHub accounts registered less than 7 days ago will not be accepted.


## 开源协议与免责声明 / License & Disclaimer

本仓库（包含自动化脚本与索引数据）基于 [MIT License](LICENSE) 开源。

**免责声明**：
1. 本仓库仅作为第三方插件的集中索引与自动化注册平台，索引中列出的插件均由各自作者独立开发与维护。
2. 本仓库及其维护者不对任何第三方插件的安全性、稳定性、合法性或可用性提供任何明示或暗示的担保。
3. 使用者因下载、安装或使用第三方插件所造成的任何直接或间接损失（包括但不限于数据丢失、系统损坏或法律纠纷），本仓库及其维护者概不承担任何法律责任。

---

This repository (including automation scripts and index data) is open-sourced under the [MIT License](LICENSE).

**Disclaimer**:
1. This repository serves solely as a centralized index and automated registration platform for third-party plugins. All plugins listed in the index are independently developed and maintained by their respective authors.
2. Neither this repository nor its maintainers provide any express or implied warranties regarding the security, stability, legality, or availability of any third-party plugins.
3. In no event shall this repository or its maintainers be liable for any direct, indirect, or consequential damages (including, but not limited to, data loss, system failure, or legal disputes) arising out of or in connection with downloading, installing, or using any third-party plugins.