# FFmpeg 集成指南

## 概述

本项目已升级为使用 FFmpeg 进行 TS 视频合并，这将完全解决之前的音画不同步和跳转卡顿问题。

## 工作原理

### 自动检测流程

程序启动时会按以下顺序自动查找 FFmpeg：

1. **项目内置 FFmpeg**（优先级最高）
   - 路径：`./ffmpeg/ffmpeg.exe`
   - 最推荐的方式，便于打包和分发

2. **系统 PATH 中的 FFmpeg**
   - 如果系统已安装 FFmpeg 并添加到环境变量

3. **常见安装路径**
   - `C:\ffmpeg\bin\ffmpeg.exe`
   - `C:\Program Files\ffmpeg\bin\ffmpeg.exe`
   - `C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe`

### 备用方案

如果找不到 FFmpeg，程序会自动使用改进的备用合并方案：
- 智能跳过冗余的 PAT/PMT 包
- 虽然不如 FFmpeg 完美，但比原来的方式好很多

## 安装方式

### 方式 1：项目内置 FFmpeg（推荐）

这是最简单的方式，适合打包和分发。

#### 步骤：

1. **下载 FFmpeg**
   - 访问 https://ffmpeg.org/download.html
   - 选择 Windows 版本（推荐 Full 版本）
   - 或使用 https://www.gyan.dev/ffmpeg/builds/ 下载预编译版本

2. **解压到项目目录**
   ```
   项目根目录/
   ├── ffmpeg/
   │   ├── ffmpeg.exe
   │   ├── ffprobe.exe
   │   └── ffplay.exe
   ├── m3u8_downloader.py
   ├── main.py
   └── ...
   ```

3. **验证安装**
   - 运行程序，查看日志输出
   - 应该看到：`[DEBUG] 找到项目内置FFmpeg: ./ffmpeg/ffmpeg.exe`

### 方式 2：系统全局安装

如果你想在系统中全局使用 FFmpeg：

1. **下载并安装**
   - 从 https://ffmpeg.org/download.html 下载
   - 或使用包管理器：`choco install ffmpeg`（Windows）

2. **添加到 PATH**
   - Windows：将 FFmpeg 的 bin 目录添加到系统环境变量 PATH
   - 重启电脑使配置生效

3. **验证安装**
   ```bash
   ffmpeg -version
   ```

## 打包应用

### 使用 PyInstaller 打包（包含 FFmpeg）

```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 打包应用（包含 ffmpeg 文件夹）
pyinstaller --onefile ^
    --add-data "ffmpeg;ffmpeg" ^
    --add-data "assets;assets" ^
    --icon=assets/favicon.ico ^
    main.py

# 3. 打包后的结构
dist/
└── main.exe
```

### 手动打包

1. 使用 PyInstaller 生成 exe
2. 将 `ffmpeg` 文件夹复制到 exe 同级目录
3. 将 `assets` 文件夹复制到 exe 同级目录
4. 分发整个文件夹

## 性能对比

| 指标 | 原方式 | 新方式（FFmpeg） | 新方式（备用） |
|------|-------|-----------------|--------------|
| 音画同步 | ❌ 差 | ✅ 完美 | ⚠️ 中等 |
| 跳转延迟 | ❌ 有 | ✅ 无 | ⚠️ 少 |
| 文件大小 | ⚠️ 大 | ✅ 优 | ✅ 优 |
| 合并速度 | ✅ 快 | ⚠️ 中等 | ✅ 快 |
| 依赖 | 无 | FFmpeg | 无 |

## 故障排除

### 问题 1：找不到 FFmpeg

**症状**：日志显示 `[WARNING] 未找到FFmpeg，将使用备用合并方案`

**解决方案**：
1. 检查 `ffmpeg/ffmpeg.exe` 是否存在
2. 或安装系统 FFmpeg 并添加到 PATH
3. 或使用备用方案（虽然效果不如 FFmpeg）

### 问题 2：FFmpeg 执行失败

**症状**：日志显示 `[ERROR] FFmpeg合并失败`

**解决方案**：
1. 检查 FFmpeg 版本是否过旧
2. 尝试手动运行 FFmpeg 测试
3. 检查输出路径是否有权限问题

### 问题 3：合并速度慢

**症状**：合并大文件时耗时很长

**解决方案**：
- 这是正常的，FFmpeg 需要处理 TS 流的重新组织
- 可以在后台运行，不影响其他操作

## 技术细节

### FFmpeg 合并命令

程序使用以下命令进行合并：

```bash
ffmpeg -f concat -safe 0 -i concat.txt -c copy -y output.mp4
```

**参数说明**：
- `-f concat`：使用 concat demuxer
- `-safe 0`：允许绝对路径
- `-i concat.txt`：输入文件列表
- `-c copy`：直接复制，不重新编码（快速）
- `-y`：覆盖输出文件

### 备用方案原理

- 跳过每个片段前 10 个 TS 包（1880 字节）
- 这些包通常包含冗余的 PAT/PMT 信息
- 保留第一个片段的完整 PAT/PMT 用于播放器初始化

## 常见问题

**Q: 为什么需要 FFmpeg？**
A: FFmpeg 能正确处理 TS 流的时间戳和元数据，确保音画同步和无缝跳转。

**Q: 没有 FFmpeg 可以用吗？**
A: 可以，程序会自动使用备用方案，效果会好一些但不如 FFmpeg。

**Q: 打包时必须包含 FFmpeg 吗？**
A: 不必须，但强烈推荐。这样用户不需要额外安装依赖。

**Q: FFmpeg 会增加多少文件大小？**
A: 约 50-100MB（取决于版本）。

## 更新日志

### v1.1（当前版本）
- ✅ 集成 FFmpeg 合并
- ✅ 自动检测 FFmpeg
- ✅ 改进的备用方案
- ✅ 完全解决音画不同步问题

