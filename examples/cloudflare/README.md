# CapSkip Turnstile

在真实页面 `https://capskip.com/captcha-demo/cloudflare-turnstile/` 上运行当前
ruyijs 引擎，遍历 closed shadow root 中的 iframe 和复选框，发送原生可信点击，
记录挑战事件、错误码及 CapSkip 后台验证结果。每次导航获取页面当前的配置和 nonce。

```sh
python -m ruyijs.examples cloudflare --direct --output result/cloudflare.json
python -m ruyijs.examples cloudflare --direct --profile akamai --timeout 180
python -m ruyijs.examples cloudflare --direct --profile linux --timeout 180
```

默认复用 DataDome 示例的环境配置；`--profile akamai` 复用 Akamai 示例的配置，
并使 User-Agent 与 Firefox 159 TLS 配置一致；`--profile default` 保留引擎默认配置。
`--profile linux` 复用 DataDome 的屏幕和视口配置，使用 Linux Firefox 159 的
Navigator 和实测 Mesa/llvmpipe WebGL 标识，供本机软件渲染环境的对照诊断使用。
也支持 `--proxy http://127.0.0.1:7890`。当前 Linux 代理路由仍依赖 donor xpcshell，
只有共享 NSS helper 的安装应使用 `--direct`。

只有拿到非 dummy token，且原页面的后台结果同时显示 `Success=true` 和
`Hostname=capskip.com`，才返回退出码 0。挑战失败、网络错误和超时均返回 1。
JSON 记录 token 长度，省略 token、请求正文和 Cookie 值。

这是生产挑战的诊断示例，尚未证明当前引擎可以通过该页面。2026-10-31 实测原页面，
DataDome 和 Akamai 两种配置均能加载真实 widget 并点击复选框，随后返回 `600010`、
空 token，且没有站点后台验证请求。Akamai 配置的命令运行约 90 秒并以退出码 1 结束。
加载成功、显示复选框和 dummy key 通过都不代表真实挑战通过。

复测已修复未知内容大小的 Zstandard 响应解码、closed shadow root 的宿主检查，
以及 iframe 点击误用顶层视口和键盘焦点的问题。布局缓存现会验证每个 shadow
样式作用域，并已修复 computed style 旧快照和尺寸读取、媒体 Promise 拒绝、
Linux `local()` 字体加载、Linux WebGPU 默认暴露、音频缓冲区复制和缓冲音源离线播放。
字体和缓冲音源探测已与成功的独立 Firefox 对照一致。Linux 配置最近一次原页面尝试约 20 秒
返回同样失败。51 项 native 测试、
smoke checks 和三个原有在线示例通过。
详细记录见 [CLOUDFLARE.md](../../native_tests/CLOUDFLARE.md)。
