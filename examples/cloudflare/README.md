# CapSkip Turnstile

使用当前仓库的原生 ruyijs 引擎运行真实页面
`https://capskip.com/captcha-demo/cloudflare-turnstile/`，记录挑战事件、
错误码及 CapSkip 后台验证结果。每次导航获取页面当前的配置和 nonce。

2026-10-31，`dev/linux-next` 的原生 Linux 运行时使用 `--profile linux`
连续两次验证成功：分别耗时 17.284 秒、16.737 秒，均获得 624 字符的非 dummy
响应 token，并由原页面后台返回 `Success=true`、`Hostname=capskip.com`，
各发送一次后台验证请求，退出码均为 0。

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
