#!/usr/bin/env python3
"""PixelForge 启动入口"""
import sys
import os

# 确保从源码根目录导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pixelforge.main import main

if __name__ == "__main__":
    sys.exit(main())
