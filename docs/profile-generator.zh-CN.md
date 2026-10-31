# Linux / Windows profile 生成器

生成可直接传给 `Context.configure_fingerprint()` 或通用 Turnstile 求解器的
Firefox 159 配置字典，支持 Linux x86_64 和 Windows x64。

## Python API

```python
from ruyijs import Context, generate_profile, solve_turnstile

linux = generate_profile("linux", seed=42, locale="zh-CN")
windows = generate_profile("windows", seed=43, locale="en-US")

with Context(tls="159") as context:
    context.configure_fingerprint(windows)  # 在执行页面脚本之前配置
    context.load_page("https://example.com/", "<!doctype html>")
    print(context.eval("navigator.platform"))  # Win32

# 将 site_url、sitekey 换成目标页面的配置。
token = solve_turnstile(site_url, sitekey, profile=linux)
```

`seed` 相同、参数相同、生成器版本相同时，输出完全一致；省略 `seed` 时每次
独立随机生成。生成器不修改应用的全局随机数状态，不启动 Context，也不访问网络。
每次返回独立的嵌套字典，可以自行修改。随机组合不保证全局唯一。

显式指定字段：

```python
profile = generate_profile(
    "windows",
    seed=100,
    locale="zh-CN",
    timezone="Asia/Shanghai",
    hardware_concurrency=8,
    screen_size=(1536, 864),
    device_pixel_ratio=1.25,
)
```

| 参数 | 默认值 / 约束 |
| --- | --- |
| `os_name` | `"linux"` 或 `"windows"`，默认 `"linux"` |
| `seed` | 非负整数或 `None` |
| `locale` | 默认 `en-US`；另支持 `en-GB`、`zh-CN`、`zh-TW`、`ja-JP`、`ko-KR`、`de-DE`、`fr-FR` |
| `timezone` | 默认跟随 locale，例如 `zh-CN` → `Asia/Shanghai`、`en-US` → `America/New_York`；可覆盖为 IANA 名称 |
| `hardware_concurrency` | 默认从 4、8、12、16 中选择；可指定 1–64 的整数 |
| `screen_size` | 默认从桌面预设选择；可指定宽 800–7680、高 600–4320 的整数元组 |
| `device_pixel_ratio` | 默认跟随显示预设；可指定 0.5–4 的有限数值 |

屏幕和视口尺寸均为 CSS 像素。例如 1536×864、DPR 1.25 对应约 1920×1080
物理像素。视口从屏幕可用区减去窗口边距与浏览器工具栏高度，保证尺寸关系一致。
`hardware_concurrency` 只是浏览器报告值，不限制实际线程数或 CPU 消耗。
locale 同时设置 `navigator.language/languages` 和 `Intl` 默认 locale；时区不从
IP 或代理位置推断。额外 IANA 时区通过 Python `zoneinfo` 校验，缺少系统时区库时
可安装 `tzdata`；内置语言对应的时区和 UTC 无此依赖。

## JSON 导出

已安装包时可直接运行以下命令；在源码仓库运行时加 `PYTHONPATH=python`。

```sh
python -m ruyijs.profile_generator --os linux --seed 42 --locale zh-CN --output linux.json
python -m ruyijs.profile_generator --os windows --seed 43 --cpu 8 --screen 1536x864 --dpr 1.25 --output windows.json

# 批量生成 20 份，每份单独保存；seed 依次为 100、101、……、119。
python -m ruyijs.profile_generator --os windows --seed 100 --count 20 --output-dir profiles/windows
```

批量文件名为 `windows-0001.json`、`windows-0002.json` 等，目录按需创建。
重复导出到同一路径会覆盖同名文件。目录批量导出逐份生成，不把整批配置保留在内存中。
未指定输出路径时，标准输出为 JSON：一份是对象，多份是数组；日志不混入标准输出。
`--output` 仅接受一份配置，批量文件导出使用 `--output-dir`。

求解器加载生成的单份 JSON：

```sh
python -m ruyijs.turnstile --direct --profile-file windows.json 'SITE_URL' 'SITEKEY'
```

`--profile-file` 与 `--profile` 互斥，文件必须包含 JSON 对象。
Python 中也可用 `json.load()` 读取后传入 `profile=`。生成配置里的 CPU 等字段
按原值使用，不会被当前宿主机 CPU 数覆盖。原有默认 `profile="linux"` 继续使用
`turnstile_linux_profile.json`，其行为不变。

## 模板来源与边界

Linux 模板来自包内 `turnstile_linux_profile.json`（Mesa llvmpipe）；Windows 模板
`firefox_windows_profile.json` 提取自仓库 `profiles/firefox-environment.json` 的
Navigator、Screen、viewport、locale 和 WebGL 组（NVIDIA GTX 980 / ANGLE）。
UA 与 `oscpu`、`platform`、`appVersion` 使用对应平台的一整套值；WebGL renderer、
扩展列表和 limits 保持模板组合。生成器变化的是桌面尺寸、DPR、视口、CPU 数及
指定的语言/时区，不会为每份配置随机编造 GPU 型号。

这两类配置描述浏览器可配置的属性，不能把 Linux 原生引擎变成 Windows 系统。
字体文件、字形与 Canvas 渲染仍受宿主机影响，输出不保证 Windows 像素一致性。
Firefox 版本固定 159，直接使用 Context 时配 `tls="159"`；通用求解器已使用此版本。
生成的组合需要按目标站点实测，不能从原始 Linux 模板的验证结果推断每个组合都能通过。

## 验证记录

2026-11-01：105 项 native 测试、smoke 和 pyflakes 通过。新增测试覆盖可复现性、
嵌套字典隔离、字段校验、单份/批量导出、求解器 JSON 加载，以及两类配置在父页面
与 iframe 中的实际读取结果。Python 包构建输出包含两份 JSON，并在源码目录外
成功调用生成 API；此项未重新构建完整原生 wheel。

在 Linux 原生运行时上，`locale="zh-CN"` 的 Linux seed 42 和 Windows seed 43
各进行一次 CapSkip 测试，均首次取得 666 字符 token 并由 CapSkip 后端验证成功，
求解耗时分别为 2.740 秒、2.612 秒。这里验证的是 Windows 配置在 Linux 引擎上
的行为，没有执行 Windows 主机测试。脱敏结果见工作区
`artifacts/profile-generator/live.json`，不保存 token 值。
