# 多类验证码公开页面实测

2026-11-01，使用当前 Linux x86_64 运行时测试 reCAPTCHA v3、GeeTest、Arkose
Labs、DataDome 和 PerimeterX/HUMAN。初始实测没有修改引擎源码及 `dist/js`；
后续 Arkose、DataDome 的修复与仍未解决的问题在对应章节单独记录。

- 源码版本：`db12f81`。
- 运行时 SHA256：`0062842a6f4279daa35f3b74409c75442b6bd8d08ceef764bf35f49fb93d9a11`。
- 配置：包内 Linux Firefox 159 profile，system clock，直接连接，每次新建 Context。
- SDK 执行和正常验证交互使用当前 `Context`；GeeTest 另建了可观察 SDK 回调的
  最小测试页面。滑块测试增加了图片定位和原生鼠标拖动逻辑，没有封装为包内 API。

## 结果

| 服务与场景 | 测试页面 | 结果 | 成功判定与限制 |
| --- | --- | --- | --- |
| reCAPTCHA v3，官方评分 demo | [Google Request scores](https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php) | **3/3 通过，评分均为 0.9** | demo 后端 `success=true`，hostname/action 匹配，无错误码 |
| reCAPTCHA v3，第二个站点 | [CapSkip v3](https://capskip.com/captcha-demo/recaptcha-v3/) | **3/3 通过，评分均为 0.9** | 原页面后台 `Success=true`、`Hostname=capskip.com`、`Action=demo` |
| GeeTest v4，无感/AI | [官方 invisible bind demo](https://gt4.geetest.com/demov4/invisible-bind-en.html) | **3/3 通过后台验收** | 测试页面使用相同 captchaId 与官方 SDK，正常取得验证数据并提交官方 `demo/login`；返回 `result=success`、`used_type=ai` |
| GeeTest v4，滑块 | [官方 slide popup demo](https://gt4.geetest.com/demov4/slide-popup-en.html) | **图片辅助定位 1 次通过；自动定位原型另 1 次未通过** | 成功样本由原生鼠标事件完成拖动，官方后台返回 `result=success`、`used_type=slide`；自动定位样本请求 verify 后刷新题目，没有成功回调 |
| Arkose Labs | [官方公开 demo](https://demo.arkoselabs.com/?key=DF9C4D87-CB7B-4062-9FEB-BADB6ADA61E6) | **尚未通过** | 原页加载和独立 SDK 测试均遇到会话接口 HTTP 400；两次 SDK 回调为 `API_REQUEST_ERROR`，未得到完成 token |
| DataDome Device Check | [DataDome 官网产品地址](https://datadome.co/products/captcha/) | **3/3 取得 cookie 后放行 HTTP 请求；后续完整导航也成功** | 初始 403 后取得正常 HTTP 200 HTML；修复后最新原页加载标题正确、readyState=complete、未捕获 JS 异常。未测试 DataDome 滑块/音频模式 |
| PerimeterX/HUMAN 长按挑战 | [NopeCHA 公开 demo](https://nopecha.com/captcha/perimeterx) | **未确认通过** | demo 内嵌 Walmart 的 blocked 页面。sensor 能运行并生成 `_px` cookie，但没有观察到长按挑战成功回调，未完成长按交互 |

GeeTest v3 的[官方 fullpage demo](https://demos.geetest.com/fullpage.html)也加载了 SDK
和验证控件，但本轮没有取得它的后端验收结果，不能从 v4 的结果推导 v3 已支持。

## reCAPTCHA v3 的证据

Google 官方 demo 的三次后台响应均为：

```json
{
  "success": true,
  "hostname": "recaptcha-demo.appspot.com",
  "score": 0.9,
  "action": "examples/v3scores",
  "error-codes": []
}
```

Google 三次总耗时为 6.702、6.627、6.644 秒；CapSkip 三次为 16.475、17.276、
13.592 秒。这些都是含页面加载和后台验收的单次记录，测试期间存在其他 demo
实验，不作为性能基准。

两个站点各提交一次无效 token，后台均拒绝，包含 `invalid-input-response`。
这排除了仅把生成响应字符串或静态成功页面当作验证通过的情况。

Google 官方 demo 本身注明，示例评分不代表 Google 账号或生产流量的评分。
本轮两个 demo 的 0.9 不能作为其他站点或生产场景的评分保证。

## GeeTest 的证据与自动化范围

v4 无感测试使用官方页面的公开 captchaId `99b142aaece96330d0f3ffb565ffb3ef`，
运行官方 `gt4.js`，调用正常 SDK 方法。三次取得的验证数据包含 `lot_number`、
`pass_token`、`gen_time` 和 `captcha_output`；报告只保存字段长度。提交官方
`https://gt4.geetest.com/demov4/demo/login` 后，三次均返回：

```json
{
  "result": "success",
  "captcha_args": {"used_type": "ai", "fail_count": 0},
  "status": "success"
}
```

滑块采用官方公开 captchaId `54088bb07d2df3c46b79f80300b0abbe` 和 `riskType=slide`。
第一例先读取公开背景图及滑块图，通过图片检查和相关性候选确认缺口位置，再用
`Context.dispatch_input()` 发送鼠标按下、移动、抬起事件。SDK 正常发出 verify，
随后取得的票据由官方 demo 后端接受，`used_type=slide`、`fail_count=0`。
该记录的 183.612 秒包含等待位置确认的时间，不能用作原生求解速度。

第二例采用自动图片相关性定位，没有操作方确认位置，未取得成功结果。SDK 在
verify 请求后加载了另一道题。因此目前只能确认引擎具备完成该滑块样例的输入
和 SDK 执行能力，尚未验证一个稳定、通用的自动图片定位与求解流程。

无感和滑块两种配置分别向 demo 后端提交无效票据，均返回
`result=fail`、`reason=pass_token error`。注意失败响应的外层仍有
`status=success`；本报告检查的是内层 `result`，并核对真实验证类型。

## DataDome：界面状态与请求放行不同

没有找到可直接独立验收的 DataDome 公开 demo：本轮访问的候选
`demo.datadome.com`、`demo.datadome.co` 无法抓取，2Captcha 的 `/demo/datadome`
返回 404。改用 DataDome 自己的公开产品地址验证真实保护流程，明确区分它与
独立 CAPTCHA demo。

三次新 Context 都观察到以下过程：

1. 初始文档请求为 HTTP 403。
2. 官方脚本创建 Device Check iframe，运行当前 interstitial 脚本。
3. 向 `/interstitial/` POST，返回 HTTP 200，获得 `datadome` cookie。
4. 同一 Context 携 cookie 再请求原地址，正常跟随产品地址的重定向，取得
   `What Is a CAPTCHA? Definition, Types & How It Works` 页面，HTTP 200，
   HTML 长度 209170 字符。

三次 payload 长度为 6810、6807、6800，plv3 长度为 514、512、510；总耗时为
3.876、3.225、3.255 秒。没有把“POST 返回 200”或“存在 cookie”单独当作放行依据。

初始实验中存在 `A is undefined` / 读取 `length` 的 TypeError、`let imageLoaded`
重复声明，以及正常页面中删除 `customElements` 的异常，现已修复。根因分别
涉及 iframe 导航后旧全局环境和定时器残留，以及错误的 Window 属性描述符。
导航现创建新的内部环境并保留稳定的 `contentWindow` 引用，正确取消旧文档任务。
同时修复了窗口代理相关接口、普通标签名的 customElements 查询和标题读取。

最新不修改原页脚本的完整导航实测从初始 403 到规范地址的正常 HTTP 200 文档，
标题为 `What Is a CAPTCHA? Definition, Types & How It Works`，
`readyState=complete`，未捕获 JS 异常。另一组三个新 Context 取得正常正文为
3/3，校验阶段也没有 JS 异常。完整 126 项原生测试、smoke 和 Cloudflare 原页面
后端验收均通过。这仍不能推导 DataDome 滑块/音频模式或所有受保护网站均可通过。
实现和证据见
[DataDome 诊断记录](../native_tests/DATADOME.md)。

## Arkose 与 PerimeterX 的未完成部分

Arkose demo 地址来自 [GitHub 官方连通性排查文档所引用的测试页](https://github.com/github/docs/blob/main/content/get-started/using-github/troubleshooting-connectivity-problems.md)。
`api.js` 和 `settings` 均加载成功，但
`POST /fc/gt2/public_key/DF9C4D87-CB7B-4062-9FEB-BADB6ADA61E6`
返回 HTTP 400。两次最小 SDK 测试都收到不可恢复的 `API_REQUEST_ERROR`。
目前未拿到 `onCompleted` 结果，也没有证据把原因归于某个具体引擎接口、IP
信誉或 demo 配置，不能宣称 Arkose 已适配。

后续排查已读取原始响应正文，为 `{"error":"DENIED ACCESS"}`。修复了引擎
`XMLHttpRequest.responseType="blob"` 返回 null 的兼容问题，但修复后会话接口
仍为 HTTP 400。相同网络上的干净 Firefox 159 原始页面对照也收到相同的 400
和错误正文，`navigator.webdriver=false`。因此目前不能把该拒绝归为 ruyijs
专属故障，仍需能正常加载的 demo/key/网络组合做下一步对照。详见
[Arkose 诊断记录](../native_tests/ARKOSE.md)。

DataDome 与 iframe 修复后的再次实测仍是相同拒绝，ruyijs 没有抛 JS 异常。
新增干净 Chrome 155 对照也从未修改的官方 demo 收到同一 HTTP 400 错误正文，
`navigator.webdriver=false`；官方建议的 reset/run 有界重试三次也未取得 token。
另一个历史 demo 公钥返回 HTTP 200，但正文仍为 `DENIED ACCESS`，同样不能算成功。

NopeCHA 的 PerimeterX demo 内嵌 `https://www.walmart.com/blocked`。当前引擎
加载了 HUMAN challenge 与 sensor 脚本，并生成 `_pxvid`、`_px3`、`_pxde`。
检查窗口中没有观察到 `_pxOnCaptchaSuccess(true)`，也没有找到可执行长按的
按钮控件；内层 challenge iframe 仍待进一步排查。

额外的首页对照中，Walmart 首页在没有运行 sensor 的新 Context 中已经返回
HTTP 200；运行 sensor 后也返回 200。因此首页可访问不能用来证明本轮绕过了
PerimeterX，更不能代替长按挑战完成的证据。

## 复核与实现状态

本轮只确认这些样本中的能力边界。包内 `solve_turnstile` 仍然是 Turnstile 专用
接口；reCAPTCHA、GeeTest、Arkose 和其他流程目前是实验程序，未新增通用生产
求解器 API。

本地证据位于忽略目录 `artifacts/multi-captcha-demo/`：

- `summary.json`：选定有效实验的汇总、版本与运行时 SHA256。
- `recaptcha-*-probe.json`、`recaptcha-negative-controls.json`：两站 v3 验收与无效 token 对照。
- `geetest-invisible-sdk-{2,3,4}.json`：三次无感验证。
- `geetest-slide-assisted-result.json`、`geetest-slide-result.json`：辅助定位成功与自动定位未成功的独立记录。
- `geetest-*-negative.html`：无效票据被拒绝的 JSON 响应。
- `arkose-sdk*.json`：SDK 回调及会话接口状态。
- `datadome-access-results.json`：403、Device Check、cookie 与实际 HTTP 200 文档的三次记录。
- `perimeterx-flow*.json`、`protection-access.json`：HUMAN sensor/cookie、挑战回调和首页对照。
- `fetch_pages.py`、`probe_pages.py`、`sdk_flows.py` 等：手动测试程序；Pillow 仅安装在实验目录。

初版观察脚本在时间预算边缘仍推进完整时间步，产生了传输超时报错，相关早期
记录不作为引擎阻塞的证据。上述判断采用修正后的脚本、明确的 SDK 回调和真实
后台结果。未在本轮重建或修改原生运行时。
