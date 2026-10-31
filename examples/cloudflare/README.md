# CapSkip Turnstile

使用当前仓库的原生 ruyijs 引擎运行真实页面
`https://capskip.com/captcha-demo/cloudflare-turnstile/`，记录挑战事件、
错误码及 CapSkip 后台验证结果。每次导航获取页面当前的配置和 nonce。

2026-10-31，`dev/linux-next` 的原生 Linux 运行时使用 `--profile linux`
连续两次验证成功：分别耗时 17.284 秒、16.737 秒，均获得 624 字符的非 dummy
响应 token，并由原页面后台返回 `Success=true`、`Hostname=capskip.com`，
各发送一次后台验证请求，退出码均为 0。

同日性能优化后，在同一机器、相同配置下交替运行新旧原生运行时（每次新建
Context，不复用页面、token 或网络缓存），结果如下，单位为秒：

| 阶段 | 优化前两次 | 优化后两次 | 平均耗时降低 |
| --- | --- | --- | --- |
| 首次观察到非 dummy token | 15.398 / 15.778 | 12.826 / 12.833 | 17.7% |
| 原页面后台验证成功 | 16.383 / 17.912 | 14.520 / 14.117 | 16.5% |

优化前为 `1e475a0`，优化后为 `6336639`：缓存 Linux 字体族/字重/样式匹配，
以及复用 CSS 缓存中已有的选择器依赖。四次均后台验证成功，各一次验证 POST，
无 surfaced script errors。计时从创建 Context 前开始，到报告采集结束为止，
不包含进程关闭；token 时间是轮询首次观察值。后台响应存在网络和服务端波动，
这两组小样本不代表固定时延。完整 native 74 项及 smoke 再次通过。

2026-11-01 继续优化 CSS 计算：在一次读取期间复用节点关系，缓存规则的物理
属性展开，并避免创建未使用的临时计算上下文。以已有字体优化的 `a227ab5`
为基线，与 `3830ee3` 交替各测三次，全部通过原页面后台验证：

| 阶段（中位数） | 本轮优化前 | 本轮优化后 | 耗时降低 |
| --- | --- | --- | --- |
| 首次观察到 token | 13.310 秒 | 11.322 秒 | 14.9% |
| 后台验证成功 | 15.312 秒 | 12.362 秒 | 19.3% |

新增回归覆盖节点移动/删除/插入、跨文档采用、默认样式、CSSOM 规则编辑、
每个元素的 CSS 变量及 `!important` 顺序；完整 77 项 native 测试和 smoke 通过。
后续候选为跨 Shadow DOM 的增量布局、CSS 规则校验值缓存，具体收益尚未实测。
详细分析及样本见 [CLOUDFLARE.md](../../native_tests/CLOUDFLARE.md#second-performance-pass)。

在仓库根目录复现：

```sh
PYTHONPATH=python python3 -B -m ruyijs.examples cloudflare --direct \
  --profile linux --timeout 120 --output artifacts/capskip-verified.json
```

也可以在已安装的包中运行 `python -m ruyijs.examples cloudflare`。
默认复用 DataDome 示例的环境配置；`--profile akamai` 复用 Akamai 示例的配置，
并使 User-Agent 与 Firefox 159 TLS 配置一致；`--profile default` 保留引擎默认配置。
`--profile linux` 读取随例子提供的 `linux_firefox159_llvmpipe.json`，包含本机
Firefox 159 实测的屏幕、视口、Mesa/llvmpipe WebGL 标识、扩展和数值限制；
CPU 数使用当前主机的值。上述成功结果使用该 Linux 配置。

支持 `--proxy http://127.0.0.1:7890`。当前 Linux 代理路由仍依赖 donor xpcshell，
只有共享 NSS helper 的安装应使用 `--direct`。

只有拿到非 dummy token，且原页面的后台结果同时显示 `Success=true` 和
`Hostname=capskip.com`，才返回退出码 0。挑战失败、网络错误和超时均返回 1。
JSON 记录 token 长度，省略响应 token、请求正文和 Cookie 值。

修复覆盖未知大小的 Zstandard 响应、宿主 closed shadow root 检查、iframe
输入坐标、布局与 computed style、媒体 Promise、Linux 字体、WebGPU 暴露、
离线音频、数学默认值、模块配置继承、CSS 属性枚举及 Trusted Types 默认策略。
最新 74 项 native 测试、smoke checks 和 Akamai、DataDome、CreepJS
三个在线示例均通过。Windows/macOS 原生构建未在本机运行。
实现范围和历史诊断见 [CLOUDFLARE.md](../../native_tests/CLOUDFLARE.md)。
