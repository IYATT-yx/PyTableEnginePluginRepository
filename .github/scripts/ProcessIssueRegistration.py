import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime

# 允许提交的白名单文件扩展名（严格限制文本及配置文件）
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
    "",  # 针对无后缀文件（如 LICENSE, NOTICE）
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


def isBinaryFile(filePath):
    """读取文件前 1024 字节，检测是否存在空字符（Null Byte）判断是否为二进制文件"""
    try:
        with open(filePath, "rb") as file:
            chunk = file.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return True
    return False


def validateRepositoryFiles(repoPath):
    """递归遍历仓库，严格校验禁止包含二进制文件及非法扩展名"""
    invalidFiles = []

    for root, dirs, files in os.walk(repoPath):
        # 忽略 .git 目录下的内部文件
        if ".git" in root.split(os.sep):
            continue

        for fileName in files:
            fullPath = os.path.join(root, fileName)
            relativePath = os.path.relpath(fullPath, repoPath)

            # 1. 检查扩展名是否在黑名单中
            _, extension = os.path.splitext(fileName)
            extensionLower = extension.lower()

            if extensionLower in FORBIDDEN_EXTENSIONS:
                invalidFiles.append(
                    f"`{relativePath}` (属于禁止提交的二进制/可执行文件格式: {extensionLower})"
                )
                continue

            # 2. 检查扩展名是否在允许的白名单内
            if extensionLower not in ALLOWED_EXTENSIONS:
                invalidFiles.append(
                    f"`{relativePath}` (不支持的扩展名: `{extensionLower}`)"
                )
                continue

            # 3. 深度文件内容检测：判断是否包含二进制 Null Byte
            if isBinaryFile(fullPath):
                invalidFiles.append(
                    f"`{relativePath}` (内容被判定为二进制文件)"
                )

    if invalidFiles:
        errorListStr = "\n".join([f"- {item}" for item in invalidFiles])
        logAndExit(
            f"仓库中包含不受支持或安全的二进制/非文本文件，拒绝注册：\n{errorListStr}"
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
                            "`pluginInfo` 格式不规范，必须为可静态解析的标准 dict 字面量。"
                        )

    if not isinstance(pluginInfo, dict):
        raise ValueError("文件中缺少 `pluginInfo` 字典定义，或格式有误！")

    return pluginInfo


def main():
    issueBody = os.getenv("ISSUE_BODY", "")
    issueNumber = os.getenv("ISSUE_NUMBER", "")

    # 1. 从 Issue 内容提取 GitHub 仓库 URL
    urlPattern = r"https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)"
    match = re.search(urlPattern, issueBody)
    if not match:
        logAndExit("未在 Issue 中找到有效的 GitHub 仓库链接！")

    owner, repoName = match.group(1), match.group(2).replace(".git", "")
    repoUrl = f"https://github.com/{owner}/{repoName}.git"

    # 2. 校验项目名称格式：必须为 "作者名_插件名"
    if "_" not in repoName:
        logAndExit(
            f"仓库名称 `{repoName}` 不符合规范！必须为 `作者名_插件名` 格式（例如 `IYATT_BatchMergeByColumns`）。"
        )

    expectedAuthor, expectedPluginName = repoName.split("_", 1)

    # 3. Clone 目标插件仓库到临时路径
    tempDir = f"/tmp/pluginCheck_{repoName}"
    subprocess.run(["rm", "-rf", tempDir], check=False)
    cloneResult = subprocess.run(
        ["git", "clone", "--depth", "1", repoUrl, tempDir],
        capture_output=True,
        text=True,
    )
    if cloneResult.returncode != 0:
        logAndExit(
            f"无法 Clone 目标仓库，请确认仓库是否为公开仓库：\n```\n{cloneResult.stderr}\n```"
        )

    # 4. 执行严格的文件与二进制安全校验
    validateRepositoryFiles(tempDir)

    # 5. 获取最新 Commit 哈希
    commitHash = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tempDir)
        .decode()
        .strip()
    )

    # 6. 校验入口文件：必须存在 "作者名_插件名.py"
    entryFileName = f"{repoName}.py"
    entryFilePath = os.path.join(tempDir, entryFileName)
    if not os.path.exists(entryFilePath):
        logAndExit(
            f"仓库根目录下未找到入口文件 `{entryFileName}`！项目文件名与主入口文件名必须保持一致。"
        )

    # 7. AST 安全解析 pluginInfo 字典
    try:
        pluginInfo = parsePluginInfoViaAst(entryFilePath)
    except Exception as error:
        logAndExit(f"解析入口文件 `{entryFileName}` 失败：{str(error)}")

    # 校验 pluginInfo 中的必要字段
    name = pluginInfo.get("name")
    author = pluginInfo.get("author")
    description = pluginInfo.get("description", "")
    version = pluginInfo.get("version", "0.0.1")

    if not name or not author:
        logAndExit("`pluginInfo` 字典中必须包含 `name` 与 `author` 字段！")

    # 8. 读取与更新 index.json
    indexFile = "index.json"
    indexData = {}
    if os.path.exists(indexFile):
        with open(indexFile, "r", encoding="utf-8") as file:
            try:
                indexData = json.load(file)
            except Exception:
                indexData = {}

    if "plugins" not in indexData:
        indexData["plugins"] = {}

    currentTime = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # 组装索引数据
    indexData["plugins"][repoName] = {
        "author": author,
        "pluginName": name,
        "description": description,
        "repoUrl": f"https://github.com/{owner}/{repoName}",
        "entryFile": entryFileName,
        "version": version,
        "commitHash": commitHash,
        "updatedAt": currentTime,
    }

    with open(indexFile, "w", encoding="utf-8") as file:
        json.dump(indexData, file, indent=2, ensure_ascii=False)

    # 9. 组装结果 Markdown 格式回复 Issue
    successReply = f"""### ✅ 插件注册/更新成功！

    索引已成功更新并写入中心仓库，详细元数据如下：

    * **作者**：`{author}`
    * **插件名**：`{name}`
    * **描述**：`{description}`
    * **版本号**：`{version}`
    * **最新 Commit 哈希**：`{commitHash}`
    * **提交成功时间**：`{currentTime}`

    > 该 Issue 已处理完成并自动关闭。若后续更新插件，重新发帖或编辑该 Issue 均可再次触发自动更新。
    """

    logAndExit(successReply, isSuccess=True)


if __name__ == "__main__":
    main()