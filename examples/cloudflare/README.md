# CapSkip Turnstile

使用当前仓库的原生 ruyijs 引擎运行真实页面
`https://capskip.com/captcha-demo/cloudflare-turnstile/`，记录挑战事件、
错误码及 CapSkip 后台验证结果。每次导航获取页面当前的配置和 nonce。

当前 fork 的 `main` 已基于上游 `d32dd74`（0.3.0）重新变基，保留 Cloudflare
兼容修复和所有已验证的优化。重建 Linux 运行时及上游网络适配器后，84 项
native 测试、smoke 和 Python 静态检查通过。2026-11-01 连续三次真实后台
验证成功，总耗时分别为 11.430、10.949、11.784 秒；token 观察时间中位数
为 9.830 秒。三次均获得 624 字符的非 dummy token，后台返回
`Success=true`、`Hostname=capskip.com`。这是少量实测样本，不代表固定时延。
详情见 [变基验证记录](../../native_tests/CLOUDFLARE.md#upstream-030-rebase-validation)。

## 通用 Turnstile Solver

包内提供同步 API，只需要目标站点 URL 和对应 sitekey。`site_url` 必须使用
该 sitekey 绑定的 hostname；路径和 query 会保留。每次调用默认新建独立
Context，不复用 cookie、页面或 token。

```python
from ruyijs import solve_turnstile

token = solve_turnstile(
    "https://world.nol.com/en/auth-web/login?returnUrl=%2Fen%2Fmy-info",
    "0x4AAAAAACZ_9sqk3FQppT2B",
    timeout=90,
    attempts=3,
)
```

如需耗时和尝试次数，使用 `solve_turnstile_details()`；它会返回
`TurnstileSolution(token, elapsed, attempts)`。支持 `action`、`cdata`、
`proxy`、自定义 fingerprint，以及 interactive challenge 的 checkbox 点击。
Turnstile token 是一次性且会过期，取得后应立即提交给目标站点，不要缓存。

`action` 和 `cdata` 仅允许 ASCII 字母、数字、下划线和连字符，长度分别为
1–32 和 1–255；不需要时省略或传 `None`。非法参数会在启动 Context 前报错。
`timeout` 是每次尝试的秒数预算，包含启动和页面处理；进程清理另有有限等待。
运行时超时也会按 `attempts` 重试，耗尽后抛出 `TurnstileError`，其 `code`
为 `"timeout"`。挑战刷新后可重新点击 checkbox；已触发过期回调的 token
不会返回给调用方。

命令行接口：

```sh
PYTHONPATH=python python3 -m ruyijs.turnstile \
  --direct --timeout 90 --attempts 3 \
  'https://world.nol.com/en/auth-web/login?returnUrl=%2Fen%2Fmy-info' \
  '0x4AAAAAACZ_9sqk3FQppT2B'
```

默认输出只有 token，便于接入 shell 流程；`--json` 额外输出耗时和尝试次数。
默认使用实测 Linux Firefox 159 指纹；`--profile default` 可改用引擎默认指纹。

可生成不同 Linux／Windows 桌面配置并直接传入求解器：

```python
from ruyijs import generate_profile, solve_turnstile

profile = generate_profile("windows", seed=42, locale="zh-CN")
token = solve_turnstile(site_url, sitekey, profile=profile)
```

也可用 `python -m ruyijs.profile_generator --os linux --seed 42 --output linux.json`
导出，再通过求解器的 `--profile-file linux.json` 加载。
批量生成、字段说明及跨平台渲染边界见
[profile 生成器文档](../../docs/profile-generator.zh-CN.md)。

以下为变基前各阶段的历史验证记录。

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
后续已加入 CSS 规则校验值缓存，以及跨 Shadow DOM 的内联样式增量复用；
相关回归与实测记录见下方文档。
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

支持 `--proxy http://127.0.0.1:7890`。本页记录的实测使用 `--direct`；
变基后的 Linux 版使用上游发布包的网络适配器，代理路由未在本轮验证。

只有拿到非 dummy token，且原页面的后台结果同时显示 `Success=true` 和
`Hostname=capskip.com`，才返回退出码 0。挑战失败、网络错误和超时均返回 1。
JSON 记录 token 长度，省略响应 token、请求正文和 Cookie 值。

修复覆盖未知大小的 Zstandard 响应、宿主 closed shadow root 检查、iframe
输入坐标、布局与 computed style、媒体 Promise、Linux 字体、WebGPU 暴露、
离线音频、数学默认值、模块配置继承、CSS 属性枚举及 Trusted Types 默认策略。
最初成功时的 74 项 native 测试、smoke checks 和 Akamai、DataDome、CreepJS
三个在线示例均通过。Windows/macOS 原生构建未在本机运行。
实现范围和历史诊断见 [CLOUDFLARE.md](../../native_tests/CLOUDFLARE.md)。
