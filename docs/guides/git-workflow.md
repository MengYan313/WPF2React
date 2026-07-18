# Git 工作流程指南

本文档说明如何将本地代码更改同步到 GitHub 远程仓库。

## 一、命令行操作方法

### 1. 日常提交流程

#### 步骤 1: 查看修改状态
```bash
cd /Users/sophon/Codex/WPF2React
git status
```
这会显示哪些文件被修改、新增或删除。

#### 步骤 2: 添加要提交的文件

**添加所有修改的文件：**
```bash
git add .
```

**或者添加特定文件：**
```bash
git add src/parser/xaml_parser.py
git add README.md
```

**添加某个目录下的所有文件：**
```bash
git add src/parser/
```

#### 步骤 3: 提交到本地仓库
```bash
git commit -m "修改说明：简短描述本次修改的内容"
```

**示例：**
```bash
git commit -m "优化：移除子元素的 xmlns 命名空间声明"
git commit -m "新增：添加页面依赖分析功能"
git commit -m "修复：解决 XAML 解析时的编码问题"
```

#### 步骤 4: 推送到 GitHub
```bash
git push origin master
```

**如果推送失败（网络问题），可以稍后重试。**

---

### 2. 完整的一次性命令（快捷方式）

```bash
cd /Users/sophon/Codex/WPF2React
git add .
git commit -m "描述你的修改"
git push origin master
```

---

### 3. 查看历史记录

**查看提交历史：**
```bash
git log --oneline
```

**查看最近 5 条提交：**
```bash
git log --oneline -5
```

**查看某个文件的修改历史：**
```bash
git log --oneline src/parser/xaml_parser.py
```

---

### 4. 撤销操作

**撤销工作区的修改（还未 add）：**
```bash
git checkout -- 文件名
```

**撤销已 add 但未 commit 的文件：**
```bash
git reset HEAD 文件名
```

**修改上一次的 commit 信息：**
```bash
git commit --amend -m "新的提交信息"
```

---

### 5. 从 GitHub 拉取最新代码

如果在其他地方修改了代码，或者有协作者提交了代码：

```bash
git pull origin master
```

---

### 6. 分支操作（可选）

**创建并切换到新分支：**
```bash
git checkout -b feature-新功能名称
```

**查看所有分支：**
```bash
git branch -a
```

**切换分支：**
```bash
git checkout master
```

**合并分支到 master：**
```bash
git checkout master
git merge feature-新功能名称
```

---

## 二、图形化界面操作方法

### 方法 1：使用 Cursor/VSCode 内置 Git

#### 1. 查看修改
- 点击左侧边栏的 **Source Control**（源代码管理）图标
- 或按快捷键 `Ctrl+Shift+G`（Linux/Windows）/ `Cmd+Shift+G`（Mac）

#### 2. 暂存文件（相当于 git add）
- 在"Changes"（更改）列表中，鼠标悬停在文件上
- 点击文件右侧的 **+** 号，将文件暂存到"Staged Changes"（暂存的更改）
- 或点击"Changes"标题右侧的 **+** 号暂存所有文件

#### 3. 提交（相当于 git commit）
- 在顶部的"Message"输入框中输入提交信息
- 点击 **✓ Commit** 按钮（或按 `Ctrl+Enter`）

#### 4. 推送到 GitHub（相当于 git push）
- 点击"More Actions"（三个点的菜单）
- 选择 **Push** 或 **Push to...**
- 或点击底部状态栏的 **↑** 图标（如果有）

#### 5. 拉取更新（相当于 git pull）
- 点击"More Actions"菜单
- 选择 **Pull** 或 **Pull from...**
- 或点击底部状态栏的 **↓** 图标

---

### 方法 2：使用 GitHub Desktop（如果已安装）

#### 1. 打开仓库
- 启动 GitHub Desktop
- File → Add Local Repository → 选择 `/Users/sophon/Codex/WPF2React`

#### 2. 查看和提交更改
- 左侧会显示所有修改的文件
- 默认所有文件都会被勾选（相当于 git add）
- 在左下角输入"Summary"（必填）和"Description"（可选）
- 点击 **Commit to master** 按钮

#### 3. 推送到 GitHub
- 点击顶部的 **Push origin** 按钮

#### 4. 拉取更新
- 点击顶部的 **Fetch origin** 查看是否有更新
- 如果有更新，会显示 **Pull origin** 按钮，点击即可

---

### 方法 3：使用 GitKraken 或 Sourcetree（第三方图形工具）

这些是专业的 Git 图形化工具，提供更丰富的功能：
- **GitKraken**: https://www.gitkraken.com/
- **Sourcetree**: https://www.sourcetreeapp.com/

操作流程类似，都是：查看更改 → 暂存 → 提交 → 推送

---

## 三、常见问题

### Q1: 推送时提示"Permission denied"或"Authentication failed"
**解决方案：**
- 使用 HTTPS 方式时，需要输入 GitHub 用户名和密码（或 Personal Access Token）
- 如果使用 SSH 方式，需要配置 SSH 密钥

### Q2: 推送时提示"Connection timed out"
**解决方案：**
- 检查网络连接
- 配置代理（如果需要）：
  ```bash
  git config --global http.proxy http://代理地址:端口
  git config --global https.proxy https://代理地址:端口
  ```
- 或稍后重试

### Q3: 如何忽略某些文件不提交？
**解决方案：**
- 编辑 `.gitignore` 文件
- 添加要忽略的文件或目录名称
- 例如：`outputs/`、`*.pyc`、`__pycache__/`

### Q4: 提交后发现 commit 信息写错了
**解决方案：**
```bash
git commit --amend -m "新的正确的提交信息"
git push -f origin master  # 注意：如果已经推送，需要强制推送
```

### Q5: 本地和远程有冲突
**解决方案：**
```bash
git pull origin master  # 先拉取远程更新
# 解决冲突（手动编辑冲突文件）
git add .
git commit -m "解决冲突"
git push origin master
```

---

## 四、推荐的提交规范

### 提交信息格式
```
类型：简短描述（不超过 50 字）

详细说明（可选，如果需要）
```

### 常用类型
- **新增**：添加新功能
- **修复**：修复 bug
- **优化**：改进性能或代码质量
- **重构**：重构代码但不改变功能
- **文档**：更新文档
- **测试**：添加或修改测试
- **构建**：修改构建配置或依赖

### 示例
```bash
git commit -m "新增：添加页面依赖分析功能"
git commit -m "修复：解决 XAML 解析时命名空间重复问题"
git commit -m "优化：提升大文件解析性能"
git commit -m "文档：更新 README 使用说明"
```

---

## 五、快速参考

| 操作 | 命令行 | Cursor/VSCode |
|------|--------|---------------|
| 查看状态 | `git status` | 点击源代码管理图标 |
| 暂存文件 | `git add .` | 点击文件旁的 + 号 |
| 提交 | `git commit -m "说明"` | 输入信息后点击 ✓ Commit |
| 推送 | `git push origin master` | 点击 Push 或 ↑ 图标 |
| 拉取 | `git pull origin master` | 点击 Pull 或 ↓ 图标 |
| 查看历史 | `git log --oneline` | 查看 COMMITS 面板 |

---

## 六、首次推送检查清单

由于首次推送时遇到了网络问题，等网络恢复后：

1. ✅ 本地仓库已初始化
2. ✅ 代码已提交到本地
3. ✅ 远程仓库地址已配置
4. ⏳ **待完成：首次推送到 GitHub**

**执行首次推送：**
```bash
cd /Users/sophon/Codex/WPF2React
git push -u origin master
```

推送成功后，后续只需执行：
```bash
git push
```

---

## 七、每日工作流程示例

```bash
# 早上开始工作前
cd /Users/sophon/Codex/WPF2React
git pull origin master  # 拉取最新代码

# 修改代码...

# 提交更改
git status  # 查看修改了什么
git add .   # 暂存所有修改
git commit -m "今天的修改说明"

# 推送到 GitHub
git push origin master

# 或者使用快捷方式
git add . && git commit -m "修改说明" && git push origin master
```

---

**祝你使用愉快！** 🎉
