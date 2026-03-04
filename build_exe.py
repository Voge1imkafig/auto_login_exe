import os
import subprocess
import sys
import shutil

def build():
    # 配置信息
    app_name = "自动登录校园网"
    main_script = "main.py"
    ico_file = "ico.ico"
    # 自动获取 Playwright 路径以包含必要驱动
    try:
        import playwright
        playwright_path = os.path.dirname(playwright.__file__)
    except ImportError:
        print("错误: 请先安装 playwright 库 (pip install playwright)")
        return

    print(f"--- 正在准备打包: {app_name} ---")

    # 构建命令
    cmd = [
        "pyinstaller",
        "--noconsole",               # 隐藏命令行窗口
        "--onefile",                 # 生成单文件 EXE
        "--upx-dir=.",
        f"--name={app_name}",        # 输出文件名
        f"--icon={ico_file}",        # 应用图标
        "--collect-all=playwright",
        "--clean",                   # 打包前清理临时文件  
        main_script,
    ]

    try:
        # 执行打包
        subprocess.check_call(cmd)
        
        # 清理生成的临时文件夹 (可选)
        if os.path.exists("build"):
            shutil.rmtree("build")
        
        print("\n" + "="*40)
        print(f"✅ 打包成功！")
        print(f"📁 可执行文件位于: {os.path.join(os.getcwd(), 'dist', app_name + '.exe')}")
        print("="*40)
    except Exception as e:
        print(f"❌ 打包过程中出现错误: {e}")

if __name__ == "__main__":
    build()