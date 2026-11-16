# Linux x86_64

从 0.3.0 起，PyPI 上有 `manylinux_2_39_x86_64` wheel。它需要 glibc 2.39 及以上（Ubuntu 24.04、Debian 13、Fedora 40
及更新版本）。Linux 移植来自 [@Starktomy](https://github.com/Starktomy) 的 #5，接在 macOS 共用的 POSIX 进程、管道和 socket 层上。

本 fork 的新发版 CI 将所有原生组件和内置 Python 3.14 都放在
`python:3.14-bookworm`（Debian 12，glibc 2.36）中编译。通过验证的新产物标记为
`manylinux_2_36_x86_64`，同一份 wheel 会安装到干净的 Debian 12 和 Ubuntu 26.04
容器中测试。这不会改变已有 wheel 或上游 PyPI 产物的兼容要求。

同一份事实的英文版在 [linux.md](linux.md)。

## 平台后端

| 组件 | Linux 后端 |
| --- | --- |
| JavaScript、Intl、Wasm | 来自 Firefox 160.0 源码（`firefox/` 子模块）的 SpiderMonkey |
| DOM、iframe realm、事件、Worker | ruyijs 共用源码，跑在 POSIX 进程和 Unix socket 上 |
| Canvas | Firefox 160 自己的 Skia，从子模块编译 |
| 字体 | fontconfig、FreeType 和 HarfBuzz，使用机器上已安装的字体 |
| WebCrypto | OpenSSL 3 |
| 图片 | libwebp、LittleCMS2 和 stb_image；AVIF 用随仓库提供的 libavif、dav1d 和 libyuv |
| HTTP(S)、HTTP/3 | 基于子模块编出的 NSS 3.131 / NSPR 4.40 的 Necko helper，HTTP/3 用 Neqo。它运行在 wheel 自带的 Python 3.14 上 |
| C ABI | `libruyijs_client.so` |

文字用机器上已安装的字体绘制，所以除非装了同样的字体，canvas 文字和字体度量会和 Windows 不同。wheel 自带除 glibc 以外链接到的库；字体和 fontconfig 配置来自系统。

## 构建

本 fork 的 `.github/workflows/build-linux.yml` 使用 Ubuntu runner 上的 Debian 12
构建容器。本地构建时，在带 `firefox/` 子模块的检出目录里按顺序运行
`ci/linux/build.sh` 的各个步骤：

```sh
ci/linux/build.sh deps     # apt 软件包、clang 21（apt.llvm.org）、cbindgen
ci/linux/build.sh donor    # SpiderMonkey objdir -> obj/js-linux
ci/linux/build.sh shell    # dist/js 和 dist/libruyijs_client.so
ci/linux/build.sh necko    # NSS/NSPR、libnecko_core、Neqo 和 Necko helper（Python 3.14）
ci/linux/build.sh wheel    # 新 fork CI：wheelhouse/ruyijs-*-manylinux_2_36_x86_64.whl
ci/linux/build.sh test     # 在全新 venv 里安装 wheel 并运行冒烟测试
```

donor 步骤用发行版自带的 Python（`/usr/bin/python3`，Debian 12 为 3.11）运行 configure，necko 步骤需要 `python3` 是 Python 3.14。完整构建约占 11 GB 磁盘。Necko 适配层及其限制见
[native/necko_posix/README.md](../native/necko_posix/README.md)。一次实测构建、冒烟测试和速度基线写在
[linux-baseline.md](linux-baseline.md)。

本地编译仍使用本机实际的 glibc 基线。要得到 CI 目标兼容性，需要在 bookworm 内
完成所有步骤，包括 helper 使用的 Python；不能只给 Ubuntu 编译的旧 wheel 改标签。
上传前，`ci/linux/check_wheel_abi.py` 会逐个检查 ELF 的 glibc 符号需求、依赖是否
随包提供、架构及动态库搜索路径，并核对平台标签和 2.36 上限。donor、NSS/Neqo、
cbindgen 缓存使用独立的 bookworm/glibc236 键。两项发行版安装测试也是 Linux
工作流成功的必要条件。

Bookworm 自带 HarfBuzz 6，字体实现需要 HarfBuzz 7 起提供的
[`hb_font_set_synthetic_bold`](https://harfbuzz.github.io/harfbuzz-hb-font.html#hb-font-set-synthetic-bold)。
deps 步骤会在需要时，从固定 SHA-256 的源码包编译 HarfBuzz 8.3.0 及 subset 库，
保持 glibc 基线，并把该源码版本的许可证随包收集。Brotli 始终使用冻结的 vendor
头文件，不依赖系统 Brotli 头文件。

按 [Python 平台标签规范](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)，
`manylinux_2_36_x86_64` 表示 x86_64 上的 glibc 2.36 及更新版本。完整 Firefox 160
构建及同一份 0.4.1 wheel 在两个发行版上的安装测试均已通过
[远端 CI](https://github.com/Starktomy/ff-ruyijs/actions/runs/43922863710)。

产物哈希、101 个 ELF 的 ABI 检查及安装结果见
[远端验证记录](linux-ci-validation-20261117.md)。较早的
[本地验证记录](linux-ci-validation-20261116.md) 保留源码及 C 夹具的检查结果。
