# shader-cache-cleaner

一个 [DSH](https://github.com/ranxianglei/billion-context)（DeepSeek Harness）技能：扫描、归因并清理 GPU 着色器缓存。

## 它能做什么

- 扫描**多位置**着色器缓存：NVIDIA DXCache/GLCache、Windows D3DSCache、各游戏 Unreal 引擎的 `Saved\PSO` / `Saved\ShaderCache` 目录
- 用**时间戳交叉比对**把共享缓存归因到具体游戏：读 Steam `LastPlayed` ↔ 缓存文件 `LastWriteTime` 做日期聚类
- 输出可读报告或机器可读 JSON，**绝不自动删除**——清理前一定会先给你 keep/delete 清单、经你确认后才动手

## 为什么缓存文件读不出游戏名

NVIDIA 的 `.nvph` 文件名是内容哈希（16 位十六进制），文件体是被压缩的二进制数据——文件名和字节里都**没有**游戏名。所以这个技能不解析文件内容，而是用时间戳比对来归因。

## 着色器缓存地图

| 位置 | 内容 | 能否按游戏识别 |
|---|---|---|
| `%LOCALAPPDATA%\NVIDIA\DXCache` | 驱动级编译着色器（`.nvph`） | 否（哈希命名） |
| `%LOCALAPPDATA%\NVIDIA\GLCache` | OpenGL / Vulkan 驱动缓存 | 否 |
| `%LOCALAPPDATA%\D3DSCache` | Windows DirectX 缓存 | 否 |
| `<游戏>\...\Saved\PSO`（Unreal） | 逐游戏 PSO 缓存 | 是 |
| `<游戏>\...\Saved\ShaderCache` | 逐游戏着色器缓存 | 是 |

## 安装

把本仓库克隆（或复制）到 DSH 的用户技能目录。**目录名必须叫 `shader-cache-cleaner`**（要和 `SKILL.md` frontmatter 里的 `name` 一致）：

```bash
# Windows（PowerShell）
git clone https://github.com/Akiya-Official12/shader-cache-cleaner.git "$env:USERPROFILE\.dsh\skills\shader-cache-cleaner"
```

或手动复制：把 `SKILL.md` 和 `scripts/` 一起放到 `~/.dsh/skills/shader-cache-cleaner/` 下。

## 使用

在 DSH 里直接说「**帮我清理着色器缓存**」即可触发。技能会先跑只读扫描、给出归因报告和 keep/delete 清单，你确认后再清理。

也可以手动运行扫描器：

```bash
python scripts/scan_shader_cache.py                  # 可读报告
python scripts/scan_shader_cache.py --json           # 机器可读 JSON
python scripts/scan_shader_cache.py --roots E:/Program Files   # 追加游戏安装根目录
```

扫描器是纯 Python 标准库，零依赖，只读、不删任何东西。

## 注意事项

- 着色器缓存会自动重建，删除的唯一代价是下次启动对应游戏时短暂重编译 / 轻微卡顿。
- **Unreal 游戏的 `Saved` 不全是缓存**：`Saved\PSO` 是缓存，但 `Saved\Resources\Video\...\Paks` 是过场视频（游戏内容），**不要删**。
- Unity 游戏（含 `*_Data` 的目录）几乎没有独立缓存目录，其着色器缓存基本都在共享的 DXCache / D3DSCache 里。
- Windows PowerShell 5.1 会把 UTF-8 脚本按 GBK 解析，若要写 PowerShell 脚本，用纯 ASCII 或先 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`。

## 许可证

[MIT](LICENSE)
