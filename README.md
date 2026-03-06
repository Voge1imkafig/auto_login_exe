# 湖北工业大学的自动登录校园网工具

由于不设置DNS才能跳出浏览器登录,但是学校自己的DNS解析太过拉跨.
为了实现快速无感自动登录开发了这个工具.

## Python版本 
3.13.5

## 命令行运行

```bash
pip install playwright pillow pyinstaller pystray

python build_exe.py
```


## 已知bug:
- ip获取失败
- 开机自启逻辑问题
