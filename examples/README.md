# ruyijs examples

通过 pip 安装后可直接运行 `python -m ruyijs.examples <名称>`（见[项目首页](../README.md)）。在仓库目录也可执行：

```powershell
python .\examples\akamai\akamai.py
python .\examples\DataDome\datadome.py
python .\examples\creepjs\creepjs.py
python .\examples\cloudflare\turnstile.py
python .\examples\cloudflare\capskip.py
```

示例均支持 `--help`、`--direct` 和 `--proxy http://127.0.0.1:7890`。
已有本地 `dist/js`（Linux）或 `dist/js.exe`（Windows）的源码目录仍可直接运行；其余场景使用已安装的包。

`python -m ruyijs.examples cloudflare` 使用 Cloudflare 官方公开测试密钥，检查
Turnstile 回调、隐藏表单字段及服务端 Siteverify 校验。支持成功/失败、可见/不可见、
校验拒绝和重复令牌等场景，详见 [cloudflare/README.md](cloudflare/README.md)。
测试响应仅用于开发集成，不代表真实站点的挑战已通过。

`python -m ruyijs.examples cloudflare-live` 加载 CapSkip 的真实 Turnstile
演示页面，通过原生输入点击挑战中的复选框，并等待该站后端的自动验证结果。
只有返回真实令牌且站点验证通过才报告 `ok: true`；挑战失败会保留错误码并返回退出码 1。

安装与 API 示例见 [项目首页](../README.md)。
