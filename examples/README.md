# ruyijs examples

通过 pip 安装后可直接运行 `python -m ruyijs.examples <名称>`（见[项目首页](../README.md)）。在仓库目录也可执行：

```powershell
python .\examples\akamai\akamai.py
python .\examples\DataDome\datadome.py
python .\examples\creepjs\creepjs.py
python .\examples\cloudflare\cloudflare.py --direct
```

示例均支持 `--help`、`--direct` 和 `--proxy http://127.0.0.1:7890`。
已有本地 `dist/js.exe` 的源码目录仍可直接运行；其余场景使用已安装的包。

安装与 API 示例见 [项目首页](../README.md)。

[Cloudflare 示例](cloudflare/README.md)用于诊断真实 CapSkip Turnstile；退出码 0
要求非 dummy token 及站点后台验证成功，当前尚未证明生产挑战通过。
