# 上游、来源与许可

## 原始发行物

- 原始归档：`pyncm_async-1.8.2.tar.gz`
- 固定来源：<https://files.pythonhosted.org/packages/52/14/8892c8bef54293eaf13c3ff95685a097d8a48272ce07b8600138f5c24d3e/pyncm_async-1.8.2.tar.gz>
- SHA256：`3ea9914f3fbcd4a76ef1d34a4681cff3733507b54caa9aa79f1d04f0e8cd27a7`
- 归档 `PKG-INFO` 将发行物标为 Apache License，作者为 greats3an，项目页为 <https://github.com/greats3an/pyncm/tree/async>；该仓库目前无法访问。
- 归档内的 Apache-2.0 `LICENSE` 将版权人留为 `Copyright [yyyy] [name of copyright owner]` 模板占位符。因此发行元数据的许可声明不能单独证明所有嵌入代码的权利人或再许可链。
- 本副本用于本地验证，尚未发行；上游 `name` / `version` 保留仅为本地验证。

## 已识别与未闭合的组件来源

- `pyncm_async/utils/aes.py` 包含来自 pyaes 的 AES 实现。其完整 MIT 许可及 Richard Moore 2014 版权归属见 `LICENSES/pyaes-MIT.txt`。许可文本来自 pyaes v1.6.1 上游固定提交：<https://github.com/ricmoo/pyaes/blob/23a1b4c0488bd38e03a48120dfda98913f4c87d2/LICENSE.txt>。
- FeelUOwn Netease 插件的 <https://github.com/feeluown/feeluown-netease/commit/917cba84864398ee5720ce1b2e6a2a8b2f3888ba> 在 2022-03-01 新增 NOS 上传及 abroad security 代码，并注明核心代码借鉴自 <https://github.com/greats3an/pyncm>。其实现与此 SDK 对应代码高度相似；该旁证支持共同上游来源，但不授予许可。FeelUOwn 仓库未提供可验证的许可证文件。
- `pyncm_async/apis/__init__.py` 的注释将 EAPI wrapper 归于 Binaryify 的 NeteaseCloudMusicApi。该注释所指的历史源码当前无法从该仓库路径核验，不能据此确认其许可。
- `pyncm_async/utils/security.py` 包含 WEAPI abroad 密钥/解密实现及 `cloudmusic.dll` 相关算法；确切来源和授权尚未确认。`utils/constant.py` 中的 `known_good_deviceIds` 注明由 fuzzer 生成，SDK 内没有找到对该列表的引用，但生成方法和再分发授权仍未核实。

目前除 pyaes 外，不能确认所有组件的权利人及再许可依据；这里记录的是来源证据，不是法律结论。权属闭合前，不应公开发行、发布到 PyPI，或将该 SDK 打包进公开插件/媒体服务。后续需要权利人授权证据，或经单独确认后移除/clean-room 替代来源未闭合的组件。

## 云盘上传安全限制

`pyncm_async/apis/cloud.py` 的 `SetUploadObject` 原实现把云盘 token 放入 `x-nos-token`，并通过固定明文 HTTP IP 上传文件。没有确认受信 HTTPS endpoint 或可验证的服务契约；当前实现已保留原函数签名并 fail closed，调用时抛出 `NotImplementedError`，不会发送 token 或文件。其余云盘 API 仍保留；这不代表已验证它们的线上行为，也没有以猜测地址替换原 endpoint。

本说明不构成 Apache-only、全部许可合规、安全审计通过或生产可用的声明，也不证明对所有 Python `>=3.8` 版本兼容。
