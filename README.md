# PixelForge

一款轻量级桌面应用，让普通用户通过自然语言描述，一键调用国内 AI 图像生成模型 API，零代码门槛。

## 功能

- **API Key 管理**：设置页填入 Key，本地 AES 加密存储，不明文显示
- **文本生图**：输入描述，调用硅基流动（SiliconFlow）生成图片
- **图片预览 / 保存**：应用内预览，可右键或按钮保存
- **生成历史**：SQLite 记录每次生成，可回溯
- **多模型**：Kolors / FLUX.1-schnell / FLUX.1-dev 等

## 项目结构

```
PixelForge/
├── run.py                    # 启动入口
├── requirements.txt          # 依赖
├── pixelforge/
│   ├── main.py               # 应用入口
│   ├── config.py             # 配置管理（JSON）
│   ├── models/providers.py   # 厂商/模型定义
│   ├── security/key_manager.py  # API Key 加密
│   ├── core/
│   │   ├── api_client.py     # SiliconFlow API 客户端
│   │   ├── image_service.py  # 图片生成服务（门面）
│   │   └── storage.py        # SQLite 历史记录
│   └── ui/
│       ├── main_window.py    # 主窗口
│       ├── generate_tab.py   # 生成页签
│       ├── history_panel.py  # 历史页签
│       └── settings_dialog.py# 设置对话框
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

1. 打开应用，点击工具栏 [设置]，填入 **硅基流动** 的 API Key（https://siliconflow.cn 注册获取）
2. 选择模型与尺寸，输入图片描述
3. 点击 **生成**（或 `Ctrl+Enter`）
4. 预览结果，可保存图片或查看历史

## 数据安全

- API Key 加密存储在本机，绝不上传
- 生成历史与图片仅保存在本地
- 卸载后可手动删除 `data/` 目录清除全部数据

## 路线图

- [x] 项目骨架
- [ ] 硅基流动 API 对接验证
- [ ] 生成历史记录
- [ ] 提示词模板
- [ ] 更多厂商适配器
- [ ] 图生图 / 视频生成
