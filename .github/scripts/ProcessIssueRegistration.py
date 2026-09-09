import ast
import json
import os
import re
import subprocess
import sys
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


def logAndExit(message, isSuccess=False):
    """输出诊断日志并在 GitHub Issue 下回复"""
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
            subprocess.run(
                [
                    "gh",
                    "issue",
                    "edit",
                    issueNumber,
                    "--add-label",
                    "invalid",
                ],
                check=False,
            )

    print(message)
    sys.exit(0 if isSuccess else 1)


def loadBlacklist():
    """读取黑名单配置（blacklist.json）"""
    blacklistFile = "blacklist.json"
    blockedUsers = set()
    blockedRepos = set()

    if os.path.exists(blacklistFile):
        try:
            with open(blacklistFile, "r", encoding="utf-8") as f:
                data = json.load(f)
                # 统一转小写，方便不区分大小写比较
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
    """全量清洗 indexData，只要 GitHub 用户名(Owner)、插件作者(Author) 或 仓库地址命中黑名单即移除"""
    if "plugins" not in indexData:
        return False, indexData

    removedCount = 0
    pluginsToKeep = {}

    for repoKey, pluginInfo in indexData["plugins"].items():
        repoUrl = pluginInfo.get("repoUrl", "")
        githubOwner, repoName = extractOwnerAndRepoFromUrl(repoUrl)

        # 1. 获取要比对的几个关键标识（全部转小写）
        pluginAuthor = (
            pluginInfo.get("author", "").lower()
        )  # 代码里写死的 author 字段
        githubOwner = githubOwner.lower()  # GitHub 用户名
        fullRepoPath = f"{githubOwner}/{repoName}".lower()  # owner/repo 路径

        # 2. 检查 GitHub 用户名 或 作者名 是否在 blockedUsers 黑名单中
        isUserBlocked = (
            githubOwner in blockedUsers
        ) or (
            pluginAuthor in blockedUsers
        )

        # 3. 检查 仓库路径 或 完整URL 是否在 blockedRepos 黑名单中
        isRepoBlocked = False
        for blockedRepo in blockedRepos:
            if (
                blockedRepo == fullRepoPath
                or blockedRepo == repoKey.lower()
                or blockedRepo in repoUrl.lower()
            ):
                isRepoBlocked = True
                break

        # 4. 执行移除逻辑
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

    issueBody = os.getenv("ISSUE_BODY", "")
    issueNumber = os.getenv("ISSUE_NUMBER", "")

    indexFile = "index.json"
    indexData = {}
    if os.path.exists(indexFile):
        with open(indexFile, "r", encoding="utf-8") as file:
            try:
                indexData = json.load(file)
            except Exception:
                indexData = {}

    urlPattern = r"https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)"
    match = re.search(urlPattern, issueBody) if issueBody else None

    # =============================================================
    # 1. 全量清洗：修改 blacklist.json / 定时任务 / 手动触发
    # =============================================================
    if not match:
        print(
            "💡 未检测到 Issue 注册请求，开始对 index.json 执行全量黑名单清理巡检..."
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

    # =============================================================
    # 2. Issue 注册流程：提交校验与防穿透
    # =============================================================
    githubOwner, repoName = match.group(1), match.group(2).replace(".git", "")
    fullRepoPath = f"{githubOwner}/{repoName}".lower()
    repoUrl = f"https://github.com/{githubOwner}/{repoName}.git"

    # 先清理一遍 index.json
    _, indexData = purgeFromIndex(indexData, blockedUsers, blockedRepos)

    # 校验提交者的 GitHub 用户名 (Owner) 或 仓库地址 是否在黑名单中
    if githubOwner.lower() in blockedUsers or fullRepoPath in blockedRepos:
        with open(indexFile, "w", encoding="utf-8") as file:
            json.dump(indexData, file, indent=2, ensure_ascii=False)
        logAndExit(
            f"GitHub 账号 `{githubOwner}` 或仓库 `{fullRepoPath}` 已被列入黑名单，拒绝注册并自动清理现有索引！"
        )

    # 格式校验
    if "_" not in repoName:
        logAndExit(
            f"仓库名称 `{repoName}` 不符合规范！必须为 `作者名_插件名` 格式（如 `IYATT_BatchMergeByColumns`）。"
        )

    # Clone 仓库
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

    entryFileName = f"{repoName}.py"
    entryFilePath = os.path.join(tempDir, entryFileName)
    if not os.path.exists(entryFilePath):
        logAndExit(f"仓库根目录下未找到主入口文件 `{entryFileName}`！")

    try:
        pluginInfo = parsePluginInfoViaAst(entryFilePath)
    except Exception as error:
        logAndExit(f"解析入口文件 `{entryFileName}` 失败：{str(error)}")

    name = pluginInfo.get("name")
    author = pluginInfo.get("author")
    description = pluginInfo.get("description", "")
    version = pluginInfo.get("version", "0.0.1")

    if not name or not author:
        logAndExit("`pluginInfo` 字典中必须包含 `name` 与 `author` 字段！")

    # 校验代码里的 author 字段是否在黑名单中
    if author.lower() in blockedUsers:
        _, indexData = purgeFromIndex(indexData, blockedUsers, blockedRepos)
        with open(indexFile, "w", encoding="utf-8") as file:
            json.dump(indexData, file, indent=2, ensure_ascii=False)
        logAndExit(
            f"插件作者 `{author}` 已被列入黑名单，拒绝注册并自动清理现有索引！"
        )

    # 正常写入 index.json，增加 owner 标识
    if "plugins" not in indexData:
        indexData["plugins"] = {}

    currentTime = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    indexData["plugins"][repoName] = {
        "owner": githubOwner,  # 显式记录 GitHub 用户名
        "author": author,  # 代码中声明的作者名
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