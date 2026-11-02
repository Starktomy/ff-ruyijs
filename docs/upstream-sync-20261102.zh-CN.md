# 2026-11-02 上游同步与验证

fork 的 `main` 已 rebase 到上游 0.3.1：
`bcdcf7272551b66ca71f474b1b5515449a688761`。
上游新增的共享 `Engine`、macOS Necko／代理、TLS 修复、DOMException 与
CSS.supports 等变化均保留。

## 提交保留情况

同步前 fork/main 是 `db12f81`，与新上游的共同祖先是 `d32dd74`。
先将此前未提交的工作保存为三个独立提交：XHR Blob、WindowProxy／文档生命周期、
测试记录，再对完整序列执行 rebase。

原有 46 个 fork 提交和这 3 个新保存的提交，共 49 个，均已重放，没有丢弃提交。
上游没有与这些提交补丁完全相同的提交；涉及同一文件的变化按行为合并。
`git range-diff` 确认原序列与新序列一一对应，差异来自冲突处理和上游上下文变化。

| 保留内容 | 主要范围 |
| --- | --- |
| Cloudflare 兼容与求解 API | Trusted Types 默认策略及原生 sinks、currentScript 微任务时序、通用 URL／sitekey API、重试与 challenge 生命周期 |
| CSS 与布局性能 | cascade／selector／声明／stylesheet 缓存、shadow scope 复用、computed style 与规则索引、grid 和点查询 |
| Linux 字体和编码性能 | Fontconfig 匹配缓存、跨 realm 共享映射字体数据、Base64 解码和短字符串分配优化 |
| 其他浏览器兼容 | audio buffer sources、媒体 Promise 错误、WebGPU 暴露、非 Windows 数学默认值、配置继承、host 输入和检查 |
| 网络响应与 DOM | 未声明大小的 zstd、原生 XHR Blob、可替换的 customElements、document.title、稳定 WindowProxy 和旧文档任务取消 |
| Python 与资料 | Linux／Windows profile 生成器、示例、原生回归、历史性能和多站点验证证据 |
| CI | push／PR 轻量检查；手动或版本 tag 完整编译；每个平台一个 VM |

同步前的历史保存在 `backup/main-before-upstream-20261102`。
包含三个待提交修复的完整快照保存在
`backup/main-with-pending-fixes-20261102`，其末端是 `96bc93c`。
后者也包含同步前的 fork/main 历史。

## Engine 集成修复

共享 Engine 让多个 Context 同时在不同线程运行。fork 此前新增的 Trusted Types
注册表、前置 CSP 回调和 WindowProxy 类缓存使用了进程级可变状态。
`26769e1` 将这三处改为 `thread_local`，与上游的会话隔离方式一致。
字体合并保留了上游的线程局部语言与像素比例，也保留 fork 的线程局部字体缓存。

新增 `native_tests/test_engine_compatibility.py`：4 个并发会话各进行 4 次离线导航，
验证 eval／Function 的 Trusted Types 检查、各自策略和变量、iframe WindowProxy
身份、文档替换、旧定时器取消以及会话退出后新会话可用。

Base64 合并保留了上游的 `atob("Charleval")` 标记行为。
CI 合并保留了上游新加入的 atob、代理、ClientHello 和 Engine 检查。

## 本次验证

使用 Linux x86_64、Firefox 159 donor，重新编译 `dist/js`、C ABI client、
NSS／Necko helper 和 Neqo HTTP/3 bridge。

| 检查 | 结果 |
| --- | --- |
| 完整 native_tests | 127/127，通过，无跳过 |
| 快速 CI 的 Python／profile／workflow 检查 | 15/15，通过 |
| Python 编译与 pyflakes | 通过 |
| ci/smoke_test.py、ci/atob_check.py | 通过，包括 Worker 的 atob |
| ci/network_smoke.py、ci/proxy_smoke.py | 直连与本地 CONNECT 代理均通过 |
| ci/hello_check.py | ClientHello 匹配 Firefox 159 |
| ci/engine_check.py --network | 会话隔离、递归深度、并行、超时和独立代理均通过 |

本轮构建的 runtime SHA256：
`dc45c3ed9165f962eeb3a4cac046459fd90ed9c73a8f2f95ab44b5218679ac54`。

真实站点均使用直连，未修改站点的验证脚本：

| 路径 | 结果 |
| --- | --- |
| CapSkip 原始完整页面 | 12.203 秒，645 字符非 dummy token，1 次验证 POST，后端 Success=true、Hostname=capskip.com，0 个捕获到的 JSError |
| 通用 solve_turnstile_details + 共享 Engine | 2.657 秒，首次返回 624 字符 token；随后原站后端 HTTP 200、verified=true、server=true、success=true、hostname=capskip.com |
| DataDome 受保护页面 | 初始 403，Device Check POST 200；携 cookie 获取 canonical guide HTTP 200，209105 字符正文，0 个捕获到的 JSError，诊断耗时 3.430 秒 |

CapSkip 完整页面还记录了 4 条透明样式的 console.error 诊断输出及一个 PAT HTTP 401；
该次 token 仍由站点后端验证通过。这里没有将 console 输出等同于未捕获的 JS 异常。
单次实测用于验证 rebase 后的功能，不构成性能对比或成功率保证。
DataDome 结果仅覆盖本次 Device Check 和正文访问；Arkose 的既有拒绝问题未在本轮复测。
本轮没有运行 Windows／macOS 原生编译，也没有发布 wheel／tag。

完整日志与无 token 值的结果位于忽略目录 `artifacts/upstream-sync-20261102/`：
`build.log`、`necko-build.log`、`native-tests.log`、`engine.log`、`clienthello.log`、
`cloudflare.json`、`engine-turnstile.json`、`datadome.json` 和 `range-diff.txt`。
