# Cloudflare Turnstile 改动消融实测

2026-11-01，在当前 Linux 主机对 fork 的兼容改动逐组撤销，并用真实站点后台验收。

本轮结论：**Trusted Types 默认策略的 HTML、Script、ScriptURL 三条输入转换链路
是当前测试中不可省去的部分。其余 14 组兼容行为分别撤销、同时撤销后，CapSkip
均能通过。上游原生源码仅加 Trusted Types 补丁，也能通过原始页面和通用求解器。**

后续资源对照的 58 次调用中，完整版本返回 token 29/29，仅 Trusted Types 版本
返回 27/29，另两次超时。下面的消融结果证明对应样本可以通过，没有证明两版在
其他挑战样本中的稳定性相同。资源对照和失败成本见后文。

这里的“不可省去”是本轮固定环境和挑战样本的结果，不是所有 Cloudflare 挑战的
普遍必要条件；Trusted Types 补丁内部也没有逐行消融。

## 基线与方法

| 项目 | 值 |
| --- | --- |
| fork 源码 | `db12f81` |
| 上游源码 | `6d45317`，相对共同基线 `d32dd74` 只更新了运行时发布清单 |
| 当前运行时 SHA256 | `0062842a6f4279daa35f3b74409c75442b6bd8d08ceef764bf35f49fb93d9a11` |
| 上游源码 + Trusted Types 运行时 SHA256 | `d2d6dfedc8436d209249a5b890989e951eab63cfe418aacd7149d3b35497bf99` |
| 上游源码对照运行时 SHA256 | `74bdf94b6892c91714ca7c6fd2463c7eb9016b0367c2d7619112c525bac352d2` |
| 网络、时钟 | 直接连接、Firefox 159 TLS、system clock |
| 默认测试 profile | 包内 Linux profile，另测引擎默认 profile |
| 重试 | 每个样本使用全新 Context，`attempts=1` |

所有实验二进制、源码覆盖和日志位于忽略目录 `artifacts/cloudflare-ablation/`。
生产源码、构建对象和 `dist/js` 没有被实验覆盖。未撤销功能的重链接对照与当前
`dist/js` 的 SHA256 完全一致。

单组实验通过反向合并对应 C++ 改动或关闭明确的行为入口实现，保留当前头文件以
维持复用对象的 ABI。独立离线探针确认功能确实被撤销。为排除残留实现的影响，
又重建了采用上游头文件和源码的两组对照：上游、上游 + `dcca7b0`。后一组另含
`46a8e84` 的 `jsapi.h` 声明补全。依据 Ninja 的传递依赖重编译受影响对象，并确认
复用的预编译头没有变化输入。

两组源码对照复用相同 Firefox donor、Necko helper 和依赖库；依赖库内已有的
Skia Fontconfig 分配优化也相同。这不是官方发布二进制之间的比较，不能据此
给出未经该优化的官方包性能数据。Python 测试程序相同。

成功判定包含真实后台接受：原始 CapSkip 页面要求 `Success=true`、
`Hostname=capskip.com`；通用求解器获得的 token 立即提交给相应 demo 的后台。
报告保留长度和后台结果，省略 token、Cookie 和验证请求正文。

## 关键结果

以下为成功次数 / 尝试次数；两列分别独立执行，不共用 token。

| 实验 | 通用求解 + CapSkip 后台 | 原始 CapSkip 页面后台 | 观察 |
| --- | --- | --- | --- |
| 当前版本撤销整组 Trusted Types | 0/3 | 0/3 | 均为 `600010`，没有验收成功 |
| 仅停用默认 `createHTML` 转换 | 0/3 | 0/3 | 独立三入口探针由 7 变为 6；均为 `600010` |
| 仅停用默认 `createScript` 转换 | 0/3 | 0/3 | 探针由 7 变为 5；均为 `600010` |
| 仅停用默认 `createScriptURL` 转换 | 0/3 | 0/3 | 探针由 7 变为 3；均为 `600010` |
| 同时撤销下表 14 组其他兼容行为 | 3/3 | 3/3 | 探针确认旧行为同时存在，Trusted Types 仍返回 7 |
| 上游原生源码，仅加入 Trusted Types 补丁 | 3/3 | 3/3 | 原始整页较慢，使用 120 秒预算 |
| 上游原生源码对照 | 0/3 | 未另测 | 通用求解在每次 25 秒预算内没有返回 token |
| 当前版本关闭布局缓存复用 | 3/3 | 3/3 | 原页出现 `overrun`，但最终后台接受 |
| 当前版本使用引擎默认 profile | 3/3 | 3/3 | 未加载 `turnstile_linux_profile.json` |
| 上游 + Trusted Types 使用引擎默认 profile | 3/3 | 未另测 | 通用求解后后台接受 |

这说明本轮不需要先合入完整的兼容补丁集合才能获得成功。相对该上游源码，
Trusted Types 组已经构成一组实测足够的原生兼容补丁。上述结果没有证明该组的
策略名检查、跨 realm 修复或每一个 DOM sink 都是独立必要的。

## 其余兼容行为的单项撤销

| 撤销项 | 离线探针确认的变化 | 通用求解 + 后台 | 原始页面后台 |
| --- | --- | --- | --- |
| CSS 数字索引 | computed style 的数字键从 393 个变为 0 | 3/3 | 3/3 |
| 实时 computed style 和尺寸解析 | 保存的 style 读取旧颜色、旧宽度 | 3/3 | 3/3 |
| Linux `FontFace(local(...))` | 本地字体从加载成功变为 `SyntaxError` | 3/3 | 3/3 |
| Linux WebGPU 默认暴露修复 | `GPU` 和 `navigator.gpu` 恢复为存在 | 3/3 | 3/3 |
| 非 Windows fdlibm 配置 | 数学参考表达式出现末位差异 | 3/3 | 3/3 |
| MediaDevices Promise 错误语义 | 错误 receiver 从异步拒绝变为同步 `TypeError` | 3/3 | 3/3 |
| 音频声道复制修复 | 重叠复制从 `[1,1,2,3,4]` 变为 `[1,1,1,1,1]` | 3/3 | 3/3 |
| 离线 BufferSource 渲染 | 预期 0.5 的输出变为全 0 | 3/3 | 3/3 |
| 点命中查询 | 已知元素命中变为 `null` | 3/3 | 3/3 |
| Grid 兼容 | 数字区域布局恢复错误的位置和换行 | 3/3 | 3/3 |
| 子 realm profile 继承 | 子页面恢复 Windows ANGLE 默认值，顶层仍为 Linux 配置 | 3/3 | 3/3 |
| iframe 输入坐标修复 | 子框点击使用顶层视口中心 | 3/3 | 3/3 |
| 宿主 closed shadow root 检查 | 宿主重新无法读取 closed root | 3/3 | 3/3 |
| `currentScript` 微任务顺序 | 脚本微任务读到 `null` | 3/3 | 3/3 |

这些探针差异没有阻止本轮 CapSkip 验收，不意味着对应实现没有价值。组合撤销和
上游 + Trusted Types 的原始页面成功样本均记录 0 次 checkbox 点击。其他成功
记录中有三次需要一次点击，包括一个完整版本对照。本轮没有将挑战固定为强制
交互，因此不能推导 closed shadow root 检查、输入坐标和焦点处理在需要点击的
样本中也能省去。

Zstd 补丁没有作为 Linux 兼容组单独停用：当前 Linux 采用上游已有的流式解码器，
fork 保留的 `necko_ruyi_init.py` 修复作用于 macOS helper。本轮不能判断 macOS
路径上该修复的必要性。

## NOL 页面依赖

| 配置 | 原始 NOL 页面初始化 Turnstile API | 通用求解器获取 NOL token |
| --- | --- | --- |
| 当前版本 | 3/3 | 3/3 |
| 撤销 `currentScript` 微任务修复 | 0/3 | 3/3 |

撤销后原始页面三次都报告 Next.js 的 `Expected document.currentScript ... Received null`
错误，Turnstile API 没有初始化。通用求解器加载最小页面，因而不依赖 NOL 的
Next.js 启动过程。这里确认了页面初始化和 token 获取，没有提交 NOL 登录。

## 其他真实 demo 的交叉检查

| 场景 | 当前版本对照 | 上游 + Trusted Types | 上游源码对照 |
| --- | --- | --- | --- |
| CapSkip | 多次通过 | 3/3 后台接受 | 0/3，25 秒超时 |
| ZeroCaptcha non-interactive | 1/1 后台接受 | 3/3 后台接受 | 0/1，`600010` |
| ZeroCaptcha action/cData | 1/1 后台接受 | 3/3 后台接受 | 0/1，25 秒超时 |
| Lusostreams managed | 1/1 后台接受 | 3/3 后台接受 | 0/1，25 秒超时 |
| Lusostreams invisible | 1/1 后台接受 | 3/3 后台接受 | 0/1，`600010` |

上游 + Trusted Types 的 action/cData 样本保留 `demo_login` / `demo-session-42`。
该版本的 NOL 通用 token 获取也通过 3/3，后台接受情况未测。
五种 demo 场景分别提交损坏 token，后台全部以 `invalid-input-response` 拒绝；
测试结束后的完整版本对照在两条 CapSkip 路径仍然通过。

## 性能与维护含义

原始 CapSkip 整页记录到的耗时：完整版本通常约 11 秒；关闭布局缓存的三次为
65.439、73.067、79.774 秒；上游源码 + Trusted Types 的三次为 104.004、83.235、
82.830 秒。部分实验与编译或另一组实验并发，因此这些数值用于说明成功预算和
卡顿现象，不作为受控的速度提升百分比。

布局、CSS、字体缓存、映射字体和 Base64 优化应按效率收益评估。上游 + Trusted
Types 实验已撤销这些 fork 原生源码优化，仍然得到成功结果；依赖库的例外见方法
说明。NOL 的 `currentScript` 属于站点脚本兼容；profile 生成器、示例和 CI 属于
使用及维护工具，均不能与验证码本身的必要输入转换混为一组。

当前完整版本的 110 项 native 测试和 smoke 检查通过。实验没有删改生产兼容实现。

## 仅 Trusted Types 与完整版本的资源对照

2026-11-01，再用上述相同的两个运行时，交替按 AB/BA 顺序运行独立批次。每版
先做一次不计入汇总的预热，然后分别测 29 次调用。没有同时编译或运行其他实验。
每次使用新 Context、相同 Linux profile 配置、直接连接、30 秒预算和一次尝试。

CPU 采用隔离 cgroup 的整个进程树统计，包含 Python 调用方、运行时、worker、
网络 helper、启动及清理；不含预先完成的 Python 导入、外部采样器和后台验收。
PSS/RSS 每 50 ms 对整个进程树同时采样。两版仍共享相同 donor 和依赖库。

表内斜杠左右依次为 **完整版本 / 仅 Trusted Types**。内存为批次峰值的中位数，
并发批次的内存是整批总量。耗时列只统计取得 token 的调用；CPU 每成功 token
则包含所有尝试的 CPU 消耗，包括两次失败。

| 场景 | 并发 | 返回 token / 调用次数，完整；仅 TT | CPU 秒 / 成功 token | 峰值 PSS，MiB | 成功调用耗时中位数，秒 |
| --- | --- | --- | --- | --- | --- |
| CapSkip | 1 | 5/5；5/5 | 3.484 / 3.701 | 306 / 425 | 3.285 / 3.150 |
| CapSkip | 2 | 6/6；5/6 | 3.357 / 4.760 | 531 / 730 | 2.709 / 3.270 |
| CapSkip | 4 | 12/12；12/12 | 3.248 / 3.678 | 969 / 1254 | 3.564 / 3.981 |
| NOL | 1 | 3/3；2/3 | 3.387 / 6.803 | 301 / 443 | 2.687 / 3.336 |
| ZeroCaptcha action/cData | 1 | 3/3；3/3 | 3.424 / 3.691 | 294 / 425 | 2.768 / 3.020 |

完整版本合计取得 token 29/29，仅 Trusted Types 为 27/29；后者在 CapSkip 两并发
和 NOL 单次各出现一次 30 秒超时。本轮没有单独追踪这两次失败的浏览器检测原因，
不能将它们归因于某一项被删除的兼容修复。所有批次结束后均无残留进程。

按本轮混合场景的全部 CPU 消耗除以返回的 token 数，完整版本为 3.344 CPU 秒，
仅 Trusted Types 为 4.116 CPU 秒，完整版本低 18.8%。单次 CapSkip 峰值 PSS
中位数低约 28%。完整版本在两个并发场景、NOL 和 metadata 的成功调用中位耗时
更短；单次 CapSkip 则是仅 Trusted Types 快约 0.14 秒。因此不能声称完整版本
在所有场景都更快，也不能从改动更少推导出资源更省。

这些是少量真实挑战样本，包含网络、挑战内容和采样波动，不代表持续负载下的
固定收益。本轮计时仅覆盖通用求解器取得 token；后台验收已在前述实验验证。
字体共享及映射、CSS 缓存、编码等效率优化应与兼容补丁的必要性分开评估。

原始测量程序、34 个批次的采样结果、运行时 SHA256 和汇总保存在
`artifacts/cloudflare-ablation/resource-compare/compare.py`、`results.json`、`run.log`。

## 复核入口

完整本地证据在 `artifacts/cloudflare-ablation/`：

- `summary.json`：各报告的成功数、错误码、耗时、运行时 SHA256。
- `probes.json`：撤销生效的独立离线检查。
- `negative-controls.json`：五种 demo 场景的损坏 token 拒绝结果。
- `variants/*/changes.patch`：单组及组合实验的具体源码变化。
- `variants/upstream*/overlay/`、`target_inputs.json`、`manifest.json`：上游源码对照的输入和构建信息。
- `build_variants.py`、`build_upstream.py`、`run_variant.py`、`probe_variants.py`：本轮手动实验程序。
- `native-tests.log`、`smoke.log`：完整版本的回归结果。

同一 checkout、donor 和现有 CMake 构建下，复测已生成的二进制：

```sh
python3 -B artifacts/cloudflare-ablation/run_variant.py no_trusted_types \
  --targets capskip original --repetitions 3 --label repeat-no-trusted-types
python3 -B artifacts/cloudflare-ablation/run_variant.py upstream_tt \
  --targets capskip original --original-timeout 120 --repetitions 3 --label repeat-upstream-tt
```

再次复测前应更新站点配置和 nonce；删除本地实验的 `capskip_config.json` 可让
程序重新获取配置。首次配置请求采用 urllib 曾被站点拒绝，已改为 Necko 获取；
该启动阶段失败被排除在验证码结果之外，原始记录仍保留。
