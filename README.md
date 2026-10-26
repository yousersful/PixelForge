# PixelForge

一款轻量级桌面应用，让普通用户通过自然语言描述，一键调用国内 AI 图像生成模型 API，零代码门槛。

## 功能

- **多厂商接入**：内置六家图像生成服务 + 自定义 OpenAI 协议厂商（填 API 地址、模型 ID 即可接入任意兼容网关），切换厂商只需在设置里填对应 Key
  - 硅基流动（SiliconFlow）：Kolors / Qwen-Image / FLUX 等开源模型聚合
  - 千问 / 百炼（DashScope 工作区）：wan2.7 系列等
  - 智谱 BigModel：CogView-4 / CogView-3-Flash（免费）/ GLM-Image
  - 火山方舟（Volcano Ark）：Doubao Seedream 4.0 / 4.5
  - MiniMax：image-01 系列
  - 腾讯混元：Hy-Image 3.0（TokenHub）
- **文本生图**：输入描述即可生成，支持批量生成与并排对比
- **图生图**：上传参考图 + 文本指令，支持千问编辑模型、Seedream、MiniMax、混元 Hy-Image
- **提示词优化**：一键调用轻量 LLM 把简单描述扩写成高质量英文提示词（硅基流动）
- **图片预览 / 保存**：应用内预览，可右键或按钮保存
- **收藏夹**：一键收藏到 `Like/` 目录，与历史独立管理
- **生成历史**：SQLite 记录每次生成，可回溯；支持导出 JSON / CSV（含图片）
- **API Key 管理**：按厂商独立存储，Fernet 加密，不明文显示

## 项目结构

```
PixelForge/
├── run.py                    # 启动入口
├── requirements.txt          # 依赖
├── pixelforge/
│   ├── main.py               # 应用入口
│   ├── config.py             # 配置管理（JSON）
│   ├── models/
│   │   ├── providers.py      # 厂商/模型/尺寸表定义
│   │   └── prompts.py        # 提示词模板
│   ├── security/key_manager.py  # API Key 加密（Fernet）
│   ├── core/
│   │   ├── api_client.py     # 各厂商 API 客户端与工厂
│   │   ├── image_service.py  # 图片生成服务（门面）
│   │   ├── storage.py        # SQLite 历史记录
│   │   └── exporter.py       # 历史导出（JSON/CSV）
│   ├── ui/
│   │   ├── main_window.py         # 主窗口
│   │   ├── generate_tab.py        # 文生图页签
│   │   ├── image_to_image_tab.py  # 图生图页签
│   │   ├── history_panel.py       # 历史面板
│   │   ├── favorites_panel.py     # 收藏夹面板
│   │   ├── settings_dialog.py     # 设置对话框
│   │   ├── compare_dialog.py      # 多图对比
│   │   └── export_dialog.py       # 导出对话框
│   └── utils/helpers.py      # QThread worker、图片工具
└── data/                     # 本地数据（运行时生成）
```

## 安装与运行

```bash
cd PixelForge

# 1. 创建虚拟环境（推荐）
python3 -m venv .venv

# 2. 安装依赖
.venv/bin/pip install -r requirements.txt

# 3. 启动
.venv/bin/python run.py
```

> Windows 下对应：`.venv\Scripts\python run.py`

## 使用流程

1. 打开应用，点击工具栏 [设置]，选择厂商并填入对应 API Key：
   - 硅基流动：https://siliconflow.cn
   - 智谱：https://bigmodel.cn （CogView-3-Flash 免费，适合先体验）
   - 火山方舟：https://console.volcengine.com/ark （需开通 Seedream 模型服务）
   - MiniMax：https://platform.minimaxi.com
   - 腾讯混元：https://console.cloud.tencent.com/hunyuan （TokenHub 平台，sk- 开头的 API Key）
   - 千问/百炼：DashScope 工作区专属 URL + Key
2. 选择模型与尺寸，输入图片描述
3. 点击 **生成**（或 `Ctrl+Enter`）
4. 预览结果，可保存、收藏、对比或查看历史

> 各厂商对尺寸的限制差异较大（如 Seedream 4.5 要求总像素 ≥ 368 万，混元 Hy-Image 面积 ≤ 1024×1024），模型切换后尺寸下拉框会自动适配。

## 数据安全

- API Key 加密存储在本机，绝不上传
- 生成历史与图片仅保存在本地
- 卸载后可手动删除 `data/` 目录清除全部数据

## 路线图

- [x] 项目骨架
- [x] 硅基流动 API 对接验证
- [x] 生成历史记录
- [x] 提示词模板与 LLM 优化
- [x] 图生图
- [x] 收藏夹
- [x] 历史导出（JSON/CSV）
- [x] 多厂商适配器（硅基流动 / 千问 / 智谱 / 火山方舟 / MiniMax / 腾讯混元）
- [x] 自定义 OpenAI 协议厂商 + 设置内【测试连接】连通性校验
- [ ] 打包分发（pyinstaller / 安装包）
- [ ] 单元测试
- [ ] 画布蒙版，重新生成（正在开发，还未提交）
