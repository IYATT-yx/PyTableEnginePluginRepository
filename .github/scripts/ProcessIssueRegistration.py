import ast
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime

# 允许提交的白名单文件扩展名
ALLOWED_EXTENSIONS = {
    ".py",
    ".txt",
    ".md",
    ".gitignore",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".LICENSE",
    "",  # 无后缀文件
}

# 明确禁止的黑名单二进制文件扩展名
FORBIDDEN_EXTENSIONS = {
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".class",
    ".jar",
    ".pfx",
    ".crt",
}


def logAndExit(message, isSuccess=False, addLabels=None):
    """输出诊断日志并在 GitHub Issue 下回复，可指定打上的 Label"""
    issueNumber = os.getenv("ISSUE_NUMBER")
    ghToken = os.getenv("GH_TOKEN")

    if issueNumber and ghToken:
        commentBody = (
            f"### ❌ 插件校验/注册失败\n\n**原因**：\n{message}"
            if not isSuccess
            else message
        )
        subprocess.run(
            [
                "gh",
                "issue",
                "comment",
                issueNumber,
                "--body",
                commentBody,
            ],
            check=False,
        )
        if not isSuccess:
            labels = addLabels if addLabels else ["invalid"]
            for label in labels:
                subprocess.run(
                    [
                        "gh",
                        "issue",
                        "edit",
                        issueNumber,
                        "--add-label",
                        label,
                    ],
                    check=False,
                )

    print(message)
    sys.exit(0 if isSuccess else 1)


def checkUserAccountAge(username):
    """校验 GitHub 账号注册时长，要求必须满 7 天"""
    ghToken = os.getenv("GH_TOKEN")
    if not ghToken or not username:
        return True, 0

    url = f"https://api.github.com/users/{username}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {ghToken}",
            "User-Agent": "Plugin-Register-Bot",
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            createdAtStr = data.get("created_at")
            if createdAtStr:
                createdAt = datetime.strptime(
                    createdAtStr, "%Y-%m-%d%H:%M:%SZ"
                )
                daysOld = (datetime.utcnow() - createdAt).days
                if daysOld < 7:
                    return False, daysOld
    except Exception as e:
        print(f"⚠️ 账号注册天数查询跳过: {e}")
    return True, 0


def checkTitleUniquenessAndGetOriginalIssue(issueTitle, currentIssueNum):
    """检查 Issue 标题唯一性，发现同标题更早提交的 Issue 则提示警报"""
    ghToken = os.getenv("GH_TOKEN")
    if not ghToken or not issueTitle or not currentIssueNum:
        return True, None

    try:
        # 使用 gh cli 查询相同标题的所有 Issue
        cmd = [
            "gh",
            "issue",
            "list",
            "--search",
            f'"{issueTitle}" in:title',
            "--json",
            "number,title",
            "--state",
            "all",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            issues = json.loads(res.stdout)
            currNumInt = int(currentIssueNum)
            earlierIssues = []

            for issue in issues:
                # 只有标题完全一致才视为重复
                if issue.get("title", "").strip() == issueTitle.strip():
                    num = int(issue.get("number"))
                    if num < currNumInt:
                        earlierIssues.append(num)

            if earlierIssues:
                earlierIssues.sort()
                return False, earlierIssues[0]
    except Exception as e:
        print(f"⚠️ 校验标题唯一性查询跳过: {e}")

    return True, None


def fetchFirstIssueBody(issueNumber):
    """使用 GitHub API 获取 Issue 的第一条主贴内容（排除评论）"""
    ghToken = os.getenv("GH_TOKEN")
    if not ghToken or not issueNumber:
        return ""

    cmd = ["gh", "issue", "view", str(issueNumber), "--json", "body"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode == 0:
        data = json.loads(res.stdout)
        return data.get("body", "").strip()
    return ""


def loadBlacklist():
    """读取黑名单配置（blacklist.json）"""
    blacklistFile = "blacklist.json"
    blockedUsers = set()
    blockedRepos = set()

    if os.path.exists(blacklistFile):
        try:
            with open(blacklistFile, "r", encoding="utf-8") as f:
                data = json.load(f)
                blockedUsers = {
                    user.strip().lower()
                    for user in data.get("blockedUsers", [])
                }
                for repo in data.get("blockedRepos", []):
                    cleanRepo = (
                        repo.strip()
                        .lower()
                        .replace("https://github.com/", "")
                        .replace(".git", "")
                        .strip("/")
                    )
                    blockedRepos.add(cleanRepo)
        except Exception as error:
            print(f"⚠️ 读取 blacklist.json 失败: {error}")

    return blockedUsers, blockedRepos


def extractOwnerAndRepoFromUrl(repoUrl):
    """从 repoUrl 解析出 GitHub 用户名(owner) 和 仓库名(repo)"""
    if not repoUrl:
        return "", ""
    cleanUrl = (
        repoUrl.lower()
        .replace("https://github.com/", "")
        .replace(".git", "")
        .strip("/")
    )
    parts = cleanUrl.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return "", cleanUrl


def purgeFromIndex(indexData, blockedUsers, blockedRepos):
    """全量清洗 indexData"""
    if "plugins" not in indexData:
        return False, indexData

    removedCount = 0
    pluginsToKeep = {}

    for repoKey, pluginInfo in indexData["plugins"].items():
        repoUrl = pluginInfo.get("repoUrl", "")
        githubOwner, repoName = extractOwnerAndRepoFromUrl(repoUrl)

        pluginAuthor = pluginInfo.get("author", "").lower()
        githubOwner = githubOwner.lower()
        fullRepoPath = f"{githubOwner}/{repoName}".lower()

        isUserBlocked = (githubOwner in blockedUsers) or (
            pluginAuthor in blockedUsers
        )

        isRepoBlocked = False
        for blockedRepo in blockedRepos:
            if (
                blockedRepo == fullRepoPath
                or blockedRepo == repoKey.lower()
                or blockedRepo in repoUrl.lower()
            ):
                isRepoBlocked = True
                break

        if isUserBlocked or isRepoBlocked:
            removedCount += 1
            reason = (
                f"GitHub用户名/作者 [{githubOwner}/{pluginAuthor}]"
                if isUserBlocked
                else f"仓库 [{fullRepoPath}]"
            )
            print(
                f"🗑️ 自动移除黑名单项目: Key=`{repoKey}` (原因: 命中{reason}黑名单)"
            )
        else:
            pluginsToKeep[repoKey] = pluginInfo

    indexData["plugins"] = pluginsToKeep
    return removedCount > 0, indexData


def isBinaryFile(filePath):
    """检测文件前 1024 字节是否存在 Null Byte（判断二进制）"""
    try:
        with open(filePath, "rb") as file:
            chunk = file.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return True
    return False


def validateRepositoryFiles(repoPath):
    """递归遍历仓库，严格校验二进制及非法扩展名"""
    invalidFiles = []

    for root, dirs, files in os.walk(repoPath):
        if ".git" in root.split(os.sep):
            continue

        for fileName in files:
            fullPath = os.path.join(root, fileName)
            relativePath = os.path.relpath(fullPath, repoPath)

            _, extension = os.path.splitext(fileName)
            extensionLower = extension.lower()

            if extensionLower in FORBIDDEN_EXTENSIONS:
                invalidFiles.append(
                    f"`{relativePath}` (包含禁止提交的可执行/二进制格式: {extensionLower})"
                )
                continue

            if extensionLower not in ALLOWED_EXTENSIONS:
                invalidFiles.append(
                    f"`{relativePath}` (不支持的扩展名: `{extensionLower}`)"
                )
                continue

            if isBinaryFile(fullPath):
                invalidFiles.append(
                    f"`{relativePath}` (文件内容被判定为二进制文件)"
                )

    if invalidFiles:
        errorListStr = "\n".join([f"- {item}" for item in invalidFiles])
        logAndExit(
            f"仓库中包含不受支持的文件或二进制文件，拒绝注册：\n{errorListStr}"
        )


def parsePluginInfoViaAst(filePath):
    """静态 AST 解析提取 pluginInfo 字典数据"""
    with open(filePath, "r", encoding="utf-8") as file:
        tree = ast.parse(file.read(), filename=filePath)

    pluginInfo = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pluginInfo":
                    try:
                        pluginInfo = ast.literal_eval(node.value)
                    except ValueError:
                        raise ValueError(
                            "`pluginInfo` 格式不规范，必须为标准 dict 字面量。"
                        )

    if not isinstance(pluginInfo, dict):
        raise ValueError("文件中缺少 `pluginInfo` 字典定义！")

    return pluginInfo


def main():
    blockedUsers, blockedRepos = loadBlacklist()

    eventName = os.getenv("EVENT_NAME", "")
    issueBody = os.getenv("ISSUE_BODY", "").strip()
    issueTitle = os.getenv("ISSUE_TITLE", "").strip()
    issueNumber = os.getenv("ISSUE_NUMBER", "")
    issueAuthor = os.getenv("ISSUE_AUTHOR", "")

    indexFile = "index.json"
    indexData = {}
    if os.path.exists(indexFile):
        with open(indexFile, "r", encoding="utf-8") as file:
            try:
                indexData = json.load(file)
            except Exception:
                indexData = {}

    urlPattern = r"https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)"

    # =============================================================
    # 1. 全量清洗：修改 blacklist.json / 定时任务 / 手动触发
    # =============================================================
    if eventName in ["push", "schedule", "workflow_dispatch"]:
        print(
            "💡 收到系统巡检事件，开始对 index.json 执行全量黑名单清理巡检..."
        )
        hasChanges, indexData = purgeFromIndex(
            indexData, blockedUsers, blockedRepos
        )

        if hasChanges:
            with open(indexFile, "w", encoding="utf-8") as file:
                json.dump(indexData, file, indent=2, ensure_ascii=False)
            print("✅ 清洗完成！已成功剔除命中黑名单的项目并更新 index.json。")
        else:
            print("✨ 巡检完成，index.json 中未发现任何黑名单项目。")
        return

    # 没有获取到 Issue 编号，不进行 Issue 注册处理
    if not issueNumber:
        return

    # =============================================================
    # 2. 安全防刷 1：账号注册时长校验（必须 >= 7 天）
    # =============================================================
    isOldEnough, daysOld = checkUserAccountAge(issueAuthor)
    if not isOldEnough:
        logAndExit(
            f"安全防刷拦截：你的 GitHub 账号注册时长仅为 `{daysOld}` 天。\n"
            f"为了防止自动化脚本灌水，本仓库要求提交者账号必须注册满 **7 天** 以上！"
        )

    # =============================================================
    # 3. 校验 Issue 标题：必须为 "作者名_插件名" 格式
    # =============================================================
    if "_" not in issueTitle:
        logAndExit(
            f"Issue 标题 `{issueTitle}` 不符合规范！必须严格为 `作者名_插件名` 格式（如 `IYATT_DemoPlugin`）。"
        )

    titleParts = issueTitle.split("_")
    if len(titleParts) < 2 or not titleParts[0] or not titleParts[1]:
        logAndExit(
            f"Issue 标题 `{issueTitle}` 解析失败！必须为 `作者名_插件名` 格式。"
        )

    expectedAuthorFromTitle = titleParts[0]
    expectedPluginFromTitle = "_".join(titleParts[1:])
    expectedPluginId = issueTitle  # 即 作者名_插件名

    # =============================================================
    # 4. 校验 Issue 标题唯一性（禁止重复发 Issue）
    # =============================================================
    isUnique, originalIssueNum = checkTitleUniquenessAndGetOriginalIssue(
        issueTitle, issueNumber
    )
    if not isUnique:
        logAndExit(
            f"⚠️ 判定为重复提交！系统检测到插件 ID `{expectedPluginId}` 已存在早期提交的 Issue #{originalIssueNum}。\n"
            f"同名插件只能使用最初创建的 Issue 进行管理与更新。管理员已收到警告，将人工复核处理。",
            isSuccess=False,
            addLabels=["invalid", "duplicate"],
        )

    # =============================================================
    # 5. 校验 Issue 内容规范（第一条与后续更新）
    # =============================================================
    firstBody = fetchFirstIssueBody(issueNumber)
    firstMatch = re.search(urlPattern, firstBody) if firstBody else None

    if not firstMatch:
        logAndExit(
            "Issue 规则校验失败：Issue 的第 1 条内容（主贴）必须且仅能提交该插件的 GitHub 仓库地址！"
        )

    # 如果是评论（issue_comment），内容必须严格为 'update'
    if eventName == "issue_comment":
        if issueBody.lower() != "update":
            logAndExit(
                "互动规则拦截：后续更新只能在评论区发送 `update`！发送其他文字或自定义内容将被系统拦截。"
            )

    # 从 Issue 首贴的链接中解析 GitHub 仓库
    githubOwner, repoName = firstMatch.group(1), firstMatch.group(
        2
    ).replace(".git", "")
    fullRepoPath = f"{githubOwner}/{repoName}".lower()
    repoUrl = f"https://github.com/{githubOwner}/{repoName}.git"

    # 先清理一遍 index.json
    _, indexData = purgeFromIndex(indexData, blockedUsers, blockedRepos)

    # 校验提交者的 GitHub 用户名 (Owner) 或 仓库地址 是否在黑名单中
    if githubOwner.lower() in blockedUsers or fullRepoPath in blockedRepos:
        with open(indexFile, "w", encoding="utf-8") as file:
            json.dump(indexData, file, indent=2, ensure_ascii=False)
        logAndExit(
            f"GitHub 账号 `{githubOwner}` 或仓库 `{fullRepoPath}` 已被列入黑名单，拒绝注册！"
        )

    # =============================================================
    # 6. 一致性校验：项目名与 Issue 标题比对
    # =============================================================
    if repoName != expectedPluginId:
        logAndExit(
            f"名称不一致：GitHub 仓库名 `{repoName}` 必须与 Issue 标题 `{expectedPluginId}` 保持完全一致！"
        )

    # 校验是否为跨账号重复注册（相同插件 ID 但 GitHub Owner 不同）
    if "plugins" in indexData and repoName in indexData["plugins"]:
        existingOwner = indexData["plugins"][repoName].get("owner", "")
        if existingOwner and existingOwner.lower() != githubOwner.lower():
            logAndExit(
                f"注册冲突：插件 ID `{repoName}` 已经被 GitHub 用户 `{existingOwner}` 占用，拒绝更换账号注册！"
            )

    # Clone 仓库进行深度校验
    tempDir = f"/tmp/pluginCheck_{repoName}"
    subprocess.run(["rm", "-rf", tempDir], check=False)
    cloneResult = subprocess.run(
        ["git", "clone", "--depth", "1", repoUrl, tempDir],
        capture_output=True,
        text=True,
    )
    if cloneResult.returncode != 0:
        logAndExit(
            f"无法 Clone 目标仓库，请确认仓库是否公开：\n```\n{cloneResult.stderr}\n```"
        )

    validateRepositoryFiles(tempDir)

    commitHash = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tempDir)
        .decode()
        .strip()
    )

    # 入口文件必须严格为: 作者名_插件名.py
    entryFileName = f"{repoName}.py"
    entryFilePath = os.path.join(tempDir, entryFileName)
    if not os.path.exists(entryFilePath):
        logAndExit(
            f"仓库根目录下未找到对应的入口文件 `{entryFileName}`！入口文件名必须与插件 ID 完全同名。"
        )

    try:
        pluginInfo = parsePluginInfoViaAst(entryFilePath)
    except Exception as error:
        logAndExit(f"解析入口文件 `{entryFileName}` 失败：{str(error)}")

    # 必须包含 4 个核心字段：name, author, description, version
    name = pluginInfo.get("name")
    author = pluginInfo.get("author")
    description = pluginInfo.get("description")
    version = pluginInfo.get("version")

    if not name or not author or description is None or not version:
        logAndExit(
            "元数据不完整：入口文件中的 `pluginInfo` 字典必须完整包含 `name`、`author`、`description` 和 `version` 这 4 个字段！"
        )

    # 元数据一致性校验：name 必须为 插件名，author 必须为 作者名
    if name != expectedPluginFromTitle or author != expectedAuthorFromTitle:
        logAndExit(
            f"元数据不匹配：`pluginInfo` 中的 `author` (`{author}`) 和 `name` (`{name}`) "
            f"必须与 Issue 标题中的作者名 (`{expectedAuthorFromTitle}`) 及插件名 (`{expectedPluginFromTitle}`) 完全一致！"
        )

    # 校验代码里的 author 字段是否在黑名单中
    if author.lower() in blockedUsers:
        _, indexData = purgeFromIndex(indexData, blockedUsers, blockedRepos)
        with open(indexFile, "w", encoding="utf-8") as file:
            json.dump(indexData, file, indent=2, ensure_ascii=False)
        logAndExit(
            f"插件作者 `{author}` 已被列入黑名单，拒绝注册！"
        )

    # 写入 index.json
    if "plugins" not in indexData:
        indexData["plugins"] = {}

    currentTime = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    indexData["plugins"][repoName] = {
        "owner": githubOwner,
        "author": author,
        "pluginName": name,
        "description": description,
        "repoUrl": f"https://github.com/{githubOwner}/{repoName}",
        "entryFile": entryFileName,
        "version": version,
        "commitHash": commitHash,
        "updatedAt": currentTime,
    }

    with open(indexFile, "w", encoding="utf-8") as file:
        json.dump(indexData, file, indent=2, ensure_ascii=False)

    successReply = f"""### ✅ 插件注册/更新成功！

索引已更新并写入中心仓库：

* **插件 ID**：`{repoName}`
* **GitHub 账号**：`{githubOwner}`
* **作者**：`{author}`
* **插件名**：`{name}`
* **描述**：`{description}`
* **版本号**：`{version}`
* **最新 Commit 哈希**：`{commitHash}`
* **更新时间**：`{currentTime}`

> 该 Issue 已处理完成并自动关闭。
"""
    logAndExit(successReply, isSuccess=True)


if __name__ == "__main__":
    main()