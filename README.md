# 米哈游日历导出工具

## 项目简介
这是一个用于导出米哈游游戏活动日历的工具，支持将游戏内活动转换为标准的iCalendar格式，方便玩家将活动日程同步到自己的日历应用中。

## 功能特点
- 支持导出米哈游游戏活动为.ics格式
- 自动同步活动开始和结束时间
- 支持活动提醒功能
- 兼容所有支持iCalendar格式的日历应用

## 支持的游戏
- 绝区零

## 安装说明
1. 确保已安装Python 3.11或更高版本
2. 克隆本仓库到本地：
   ```bash
   git clone https://github.com/HolmesZ/mihoyo-ics.git
   cd mihoyo-ics
   ```
3. 创建并激活虚拟环境：
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   source .venv/bin/activate  # Linux/macOS
   ```
4. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法
1. 激活虚拟环境（如果尚未激活）
2. 运行主程序：
   ```bash
   python main.py
   ```
3. 生成的日历文件将保存为`zzz_events.ics`
4. 将生成的.ics文件导入到你的日历应用中

## 注意事项
- 请确保运行程序时保持网络连接
- 建议定期更新日历文件以获取最新的活动信息

## 许可证
本项目采用MIT许可证