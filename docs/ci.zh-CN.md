# Fork CI 与按需构建

普通提交使用快速检查，完整原生编译通过手动工作流运行。

| 操作 | 分配 VM | 内容 |
| --- | --- | --- |
| push 到 main／PR，涉及代码或工作流 | 1 台 Ubuntu | Python 编译、pyflakes、Python API 与工作流回归 |
| 仅修改文档／assets／site／示例 | 0 | 跳过自动 CI |
| 手动 Wheels：linux／windows／macos | 1 台对应平台 | 依赖、原生引擎、wheel、安装后 smoke／网络检查 |
| 手动 Wheels：windows-macos | 2 台 | Windows、macOS 各一台 |
| 手动 Wheels：all | 3 台 | 三个平台各一台 |

自动 CI 不再安装 PyPI 旧版本执行 Windows 双版本 smoke；每个平台完整构建时，
会继续测试本次源码生成的 wheel。自动检查不代替原生回归测试，修改 C++ 后仍需
按 AGENTS.md 在本地构建并运行完整 native 测试。

## 手动构建

在 Actions → Wheels → Run workflow 中选择平台，默认仅 Linux。
各平台自己的 Build 工作流也保留手动入口。

```sh
# 只构建 Linux。
gh workflow run wheels.yml --repo Starktomy/ff-ruyijs --ref main -f platform=linux

# 复验 Windows 和 macOS，每个平台各一个 VM。
gh workflow run wheels.yml --repo Starktomy/ff-ruyijs --ref main -f platform=windows-macos

# 仅发布准备等需要时运行三平台。
gh workflow run wheels.yml --repo Starktomy/ff-ruyijs --ref main -f platform=all

# 单独触发快速检查。
gh workflow run ci.yml --repo Starktomy/ff-ruyijs --ref main
```

完整构建没有 push、PR 或定时触发器。同一分支的同平台新构建会取消仍在运行的
旧构建；不同平台使用不同并发组。快速 CI 也会取消被同一分支／PR 后续提交替代的运行。

## 一个 VM 内的步骤

Windows／macOS 原先分别使用两个 Firefox matrix job 和一个 ruyijs job。
现在每个平台保留一个 job，在该 VM 内按顺序完成：

1. 检出仓库、下载一次 Firefox 源码。
2. 恢复 SpiderMonkey 与 Skia／NSS 缓存。
3. 只编译缺失的依赖，并立即保存成功的依赖缓存。
4. 删除无需保留的 browser 中间产物，给后续编译留磁盘空间。
5. 编译 ruyijs，构建 wheel，创建隔离环境安装并执行 smoke／网络检查。
6. 上传 wheel 和诊断资料。

原有 donor 缓存键保持一致，已有缓存可以复用。依赖成功构建后立即保存，因此
后续 ruyijs 编译失败不会丢失 donor 缓存。Linux 原本已使用一个 VM，保留原有
SpiderMonkey、NSS／Neqo 缓存。首次无缓存构建仍需编译对应依赖；本轮未引入
跨运行复用项目 C++ 对象的缓存。

单 VM 将原先并行的两类依赖构建改为顺序执行，因此首次冷构建的总时长可能更长，
收益是减少 runner 数量、重复源码下载和跨 VM 的缓存传输。

## Fork 的 Actions 被停用时

工作流配置先提交到默认分支，再恢复 Actions，避免旧的 push 配置启动三平台构建。
GitHub 若显示 “Workflows on this fork have been disabled”，可在仓库 Actions 页面
恢复运行。若 API 仍返回 HTTP 422 “Actions has been disabled for this repository”，
需先在该页面完成恢复，再使用上面的命令；更新 YAML 本身不会解除平台停用状态。

工作流结构由 `ci/test_workflows.py` 检查，覆盖平台选择、单 VM 数量和缓存命中组合。
也可在本地使用 actionlint 检查 GitHub Actions 语法。
