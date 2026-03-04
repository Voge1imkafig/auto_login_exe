from tkinter import Tk, StringVar, BooleanVar, Text, END, SUNKEN, filedialog
from tkinter import ttk, messagebox
from threading import Thread
from time import sleep
from socket import socket, AF_INET, SOCK_STREAM, setdefaulttimeout
from sys import executable, exit, argv
from os import path, _exit, listdir
from json import load, dump
from datetime import datetime
from winreg import OpenKey, SetValueEx, DeleteValue, CloseKey, HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE, KEY_SET_VALUE, KEY_READ, REG_SZ
from queue import Queue, Empty
from psutil import net_if_addrs
from urllib.request import urlopen
from PIL import Image, ImageDraw

# 依赖检查 - Playwright
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# 依赖检查 - Pystray
try:
    from pystray import Icon, Menu, MenuItem
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

class CampusNetworkAutoLogin:
    def __init__(self, start_minimized=False):
        self.config_file = path.join(path.expanduser('~'), '.campus_network_config.json')
        self.running = True
        self.is_logging_in = False
        self.log_queue = Queue()
        self.tray_icon = None
        self.last_public_ip = "未知"
        
        # 校园网固定网关信息
        self.base_url = "http://172.16.54.18"
        self.query_string = "wlanuserip=10.9.236.142&wlanacname=logic&nasip=10.253.0.17&wlanparameter=8c-32-23-38-0c-45&url=http://202.114.117.246/&userlocation=ethtrunk/3:3840.1104"
        self.login_page_url = f"{self.base_url}/eportal/index.jsp?{self.query_string}"
        
        self.load_config()
        self.found_browsers = self.find_browsers() # 自动查找浏览器
        self.check_initial_browser() # 初始提示
        
        self.create_main_window()
        
        if start_minimized or self.config.get('start_minimized', True):
            self.window.withdraw()
            self.log("💡 程序已启动并最小化至托盘")

        self.process_log_queue()
        if TRAY_AVAILABLE:
            Thread(target=self.setup_tray, daemon=True).start()
        
        Thread(target=self.monitor_loop, daemon=True).start()
        self.window.mainloop()

    def find_browsers(self):
        """自动在系统中寻找主流浏览器安装路径"""
        browsers = {"使用内置内核 (Chromium)": ""}
        paths = [
            (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Google Chrome"),
            (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Google Chrome"),
            (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
            (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge")
        ]
        for p, name in paths:
            if path.exists(p):
                browsers[name] = p
        return browsers

    def check_initial_browser(self):
        """第一次运行时提示发现的浏览器"""
        if not self.config.get('browser_path_selected'):
            found_names = [k for k, v in self.found_browsers.items() if v != ""]
            if found_names:
                msg = f"检测到系统中已安装以下浏览器：\n{', '.join(found_names)}\n\n是否使用检测到的默认浏览器？"
                # 这里不弹窗以免打扰静默启动，只在日志记录
                self.log(f"🔍 自动检测浏览器: 找到 {len(found_names)} 个可用程序")
            self.config['browser_path_selected'] = True
            self.update_config('browser_path', self.config.get('browser_path', ''), log_change=False)

    def load_config(self):
        defaults = {
            'username': '', 'password': '', 'service_name': '校园网',
            'auto_start': True, 'check_interval': 15, 'auto_login': True, 
            'headless_mode': True, 'start_minimized': False,
            'check_public_ip': True, 'browser_path': '', 'browser_path_selected': False
        }
        try:
            if path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = {**defaults, **load(f)}
            else:
                self.config = defaults
        except:
            self.config = defaults

    def update_config(self, key, value, log_change=True):
        if self.config.get(key) != value:
            self.config[key] = value
            if log_change:
                self.log(f"⚙️ 设置变更: {key} -> {value}")
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    dump(self.config, f, indent=4, ensure_ascii=False)
                if self.tray_icon:
                    self.tray_icon.menu = self.create_tray_menu()
            except: pass

    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{ts}] {message}\n")

    def process_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if hasattr(self, 'log_text'):
                    self.log_text.insert(END, msg)
                    self.log_text.see(END)
        except Empty: pass
        self.window.after(200, self.process_log_queue)

    def get_public_ip(self):
        if not self.config.get('check_public_ip', True):
            return "已禁用检测"
        try:
            ip = urlopen('http://api.ipify.org', timeout=3).read().decode('utf8')
            if ip != self.last_public_ip:
                self.log(f"🌐 公网IP变更: {ip}")
                self.last_public_ip = ip
            return ip
        except:
            return "获取失败"

    def get_network_status(self):
        has_adapter = False
        for interface, addrs in net_if_addrs().items():
            if 'Loopback' in interface or 'vEthernet' in interface: continue
            for addr in addrs:
                if addr.family == AF_INET and not addr.address.startswith("169.254"):
                    has_adapter = True; break
            if has_adapter: break
        
        if not has_adapter: return 0
        
        try:
            setdefaulttimeout(2)
            socket(AF_INET, SOCK_STREAM).connect(("114.114.114.114", 53))
            return 2
        except:
            return 1

    def monitor_loop(self):
        while self.running:
            if not self.is_logging_in:
                status = self.get_network_status()
                pub_ip_str = ""
                if status == 2:
                    current_ip = self.get_public_ip()
                    pub_ip_str = f" | IP: {current_ip}"

                self.update_tray_icon(status)
                
                ui_color_map = {0: ("❌网卡未连接", "white"), 1: ("⚠️ 等待登录", "black"), 2: (f"✅ 网络在线{pub_ip_str}", "green")}
                text, color = ui_color_map.get(status, ("未知状态", "gray"))
                
                self.window.after(0, lambda t=text, c=color: self.update_status_ui(t, c))

                if status == 1 and self.config['auto_login'] and self.config['username']:
                    self.log("📡 检测到断网，正在自动尝试登录...")
                    Thread(target=self.perform_login, daemon=True).start()
            
            sleep(self.config.get('check_interval', 15))

    def update_status_ui(self, text, color):
        self.status_var.set(text)
        self.status_label.configure(foreground=color)

    def perform_login(self):
        if self.is_logging_in: return
        self.is_logging_in = True
        self.window.after(0, self.toggle_ui_state, False)

        try:
            if not PLAYWRIGHT_AVAILABLE:
                self.log("❌ 错误: 未安装 Playwright 库")
                return

            with sync_playwright() as p:
                b_path = self.config.get('browser_path', '')
                headless = self.config['headless_mode']
                
                if b_path and path.exists(b_path):
                    self.log(f"🚀 使用外部浏览器: {path.basename(b_path)}")
                    browser = p.chromium.launch(executable_path=b_path, headless=headless)
                else:
                    self.log(f"🚀 使用内置内核 (无头: {headless})...")
                    browser = p.chromium.launch(headless=headless)

                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(20000)

                page.goto(self.login_page_url)
                page.wait_for_selector("#username")
                
                page.fill("#username", self.config['username'])
                page.evaluate(f'document.getElementById("pwd").value = "{self.config["password"]}"')
                
                service = self.config.get('service_name', '校园网')
                if page.is_visible("#xiala"):
                    page.click("#xiala")
                    page.wait_for_timeout(500)
                    service_options = page.locator('[id^="bch_service_"]').all()
                    for element in service_options:
                        right_text = element.locator(".right").text_content()
                        if right_text and right_text.strip() == service:
                            element.click()
                            self.log(f"🏢 已选择运营商: {service}")
                            break
                
                self.log("🖱️ 提交登录表单...")
                page.click("#loginLink")
                
                sleep(3) 
                if self.get_network_status() == 2:
                    self.log("✅ 登录成功")
                else:
                    self.log("⚠️ 登录已提交，但检测仍未联网")
                browser.close()
        except Exception as e:
            self.log(f"❌ 登录异常: {str(e)}")
        finally:
            self.is_logging_in = False
            self.window.after(0, self.toggle_ui_state, True)

    def toggle_ui_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self.login_btn.configure(state=state)

    # --- 托盘系统 ---
    def create_tray_img(self, color):
        image = Image.new('RGB', (64, 64), (240, 240, 240))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill=color)
        return image

    def create_tray_menu(self):
        def get_mark(key): return " (√)" if self.config.get(key) else " ( )"
        headless_mark = " (√)" if not self.config.get('headless_mode') else " ( )"
        
        return Menu(
            MenuItem("打开主界面", self.show_window, default=True),
            Menu.SEPARATOR,
            MenuItem(f"自动尝试登录{get_mark('auto_login')}", 
                    lambda: self.update_config('auto_login', not self.config['auto_login'])),
            MenuItem(f"显示浏览器界面{headless_mark}", 
                    lambda: self.update_config('headless_mode', not self.config['headless_mode'])),
            MenuItem(f"检测公网IP{get_mark('check_public_ip')}", 
                    lambda: self.update_config('check_public_ip', not self.config['check_public_ip'])),
            Menu.SEPARATOR,
            MenuItem("立即登录", lambda: Thread(target=self.perform_login, daemon=True).start()),
            MenuItem("彻底退出", self.quit_app)
        )

    def setup_tray(self):
        self.tray_icon = Icon("campus_net", self.create_tray_img("gray"), "校园网自动连接", self.create_tray_menu())
        self.tray_icon.run()

    def update_tray_icon(self, status):
        if not self.tray_icon: return
        color_map = {0: "white", 1: "black", 2: "green"}
        current_color = color_map.get(status, "gray")
        status_text_map = {0: "网卡未连接", 1: "等待登录", 2: f"网络在线 | IP: {self.last_public_ip}"}
        
        self.tray_icon.icon = self.create_tray_img(current_color)
        self.tray_icon.title = status_text_map.get(status, "校园网自动连接")

    def show_window(self):
        self.window.after(0, self.window.deiconify)
        self.window.after(0, self.window.attributes, "-topmost", True)
        self.window.after(100, self.window.attributes, "-topmost", False)

    def quit_app(self):
        self.running = False
        if self.tray_icon: self.tray_icon.stop()
        _exit(0)

    def select_custom_browser(self):
        file_path = filedialog.askopenfilename(
            title="选择浏览器可执行文件",
            filetypes=[("EXE Files", "*.exe"), ("All Files", "*.*")]
        )
        if file_path:
            self.update_config('browser_path', file_path)
            self.browser_var.set(file_path)

    # --- UI 构造 ---
    def create_main_window(self):
        self.window = Tk()
        self.window.title("校园网自动登录助手")
        self.window.geometry("580x700")
        
        tab_control = ttk.Notebook(self.window)
        acc_tab = ttk.Frame(tab_control)
        set_tab = ttk.Frame(tab_control)
        tab_control.add(acc_tab, text="账号登录")
        tab_control.add(set_tab, text="高级设置")
        tab_control.pack(expand=1, fill="both")

        # --- 账号页 ---
        input_f = ttk.LabelFrame(acc_tab, text="身份认证信息", padding=10)
        input_f.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(input_f, text="账号:").grid(row=0, column=0, sticky="w", pady=2)
        u_v = StringVar(value=self.config['username'])
        u_v.trace_add("write", lambda *a: self.update_config('username', u_v.get(), log_change=False))
        ttk.Entry(input_f, textvariable=u_v).grid(row=0, column=1, sticky="ew")

        ttk.Label(input_f, text="密码:").grid(row=1, column=0, sticky="w", pady=2)
        p_v = StringVar(value=self.config['password'])
        p_v.trace_add("write", lambda *a: self.update_config('password', p_v.get(), log_change=False))
        ttk.Entry(input_f, textvariable=p_v, show="*").grid(row=1, column=1, sticky="ew")

        ttk.Label(input_f, text="运营商:").grid(row=2, column=0, sticky="w", pady=2)
        s_v = StringVar(value=self.config['service_name'])
        s_v.trace_add("write", lambda *a: self.update_config('service_name', s_v.get()))
        service_box = ttk.Combobox(input_f, textvariable=s_v, values=('校园网', '移动', '联通', '电信'), state="readonly")
        service_box.grid(row=2, column=1, sticky="ew")
        input_f.columnconfigure(1, weight=1)

        self.login_btn = ttk.Button(acc_tab, text="🚀 立即手动登录", command=lambda: Thread(target=self.perform_login, daemon=True).start())
        self.login_btn.pack(pady=10)

        log_f = ttk.LabelFrame(acc_tab, text="实时运行日志", padding=5)
        log_f.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = Text(log_f, height=12, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

        # --- 设置页 ---
        set_container = ttk.Frame(set_tab, padding=20)
        set_container.pack(fill="both", expand=True)

        # 常规复选框
        ttk.Checkbutton(set_container, text="开机自动启动 (写入注册表)", 
                        variable=BooleanVar(value=self.config['auto_start']), 
                        command=self.toggle_auto_start).pack(anchor="w", pady=3)
        
        sm_v = BooleanVar(value=self.config['start_minimized'])
        ttk.Checkbutton(set_container, text="程序启动时直接最小化到托盘", variable=sm_v, 
                        command=lambda: self.update_config('start_minimized', sm_v.get())).pack(anchor="w", pady=3)

        al_v = BooleanVar(value=self.config['auto_login'])
        ttk.Checkbutton(set_container, text="发现断网时自动执行静默登录", variable=al_v, 
                        command=lambda: self.update_config('auto_login', al_v.get())).pack(anchor="w", pady=3)

        hl_v = BooleanVar(value=not self.config['headless_mode'])
        ttk.Checkbutton(set_container, text="调试模式：登录时显示浏览器窗口", variable=hl_v, 
                        command=lambda: self.update_config('headless_mode', not hl_v.get())).pack(anchor="w", pady=3)

        ip_v = BooleanVar(value=self.config['check_public_ip'])
        ttk.Checkbutton(set_container, text="在状态栏显示公网 IP 地址", variable=ip_v, 
                        command=lambda: self.update_config('check_public_ip', ip_v.get())).pack(anchor="w", pady=3)

        ttk.Separator(set_container, orient='horizontal').pack(fill='x', pady=10)

        # 浏览器选择区域
        browser_f = ttk.LabelFrame(set_container, text="浏览器内核设置 (支持快捷方式路径)", padding=10)
        browser_f.pack(fill="x", pady=5)
        
        self.browser_var = StringVar(value=self.config['browser_path'])
        
        # 预设浏览器下拉
        combo_values = list(self.found_browsers.keys())
        self.b_combo = ttk.Combobox(browser_f, values=combo_values, state="readonly")
        self.b_combo.pack(fill="x", pady=2)
        
        # 设置初始下拉框文字
        current_path = self.config['browser_path']
        matched = False
        for name, p in self.found_browsers.items():
            if p == current_path:
                self.b_combo.set(name)
                matched = True
                break
        if not matched and current_path: self.b_combo.set("自定义路径")
        elif not matched: self.b_combo.set("使用内置内核 (Chromium)")

        def on_browser_select(event):
            selected = self.b_combo.get()
            target_path = self.found_browsers.get(selected, "")
            self.update_config('browser_path', target_path)
            self.browser_var.set(target_path)

        self.b_combo.bind("<<ComboboxSelected>>", on_browser_select)

        # 自定义路径输入与按钮
        path_edit_f = ttk.Frame(browser_f)
        path_edit_f.pack(fill="x", pady=5)
        ttk.Entry(path_edit_f, textvariable=self.browser_var, state="readonly").pack(side="left", expand=True, fill="x")
        ttk.Button(path_edit_f, text="浏览...", command=self.select_custom_browser).pack(side="right", padx=5)

        ttk.Separator(set_container, orient='horizontal').pack(fill='x', pady=10)
        
        interval_f = ttk.Frame(set_container)
        interval_f.pack(fill="x", pady=5)
        ttk.Label(interval_f, text="网络检测频率 (秒):").pack(side="left")
        
        self.interval_var = StringVar(value=str(self.config.get('check_interval', 15)))
        self.interval_var.trace_add("write", self.on_interval_entry_change)
        
        self.interval_entry = ttk.Entry(interval_f, textvariable=self.interval_var, width=10)
        self.interval_entry.pack(side="left", padx=10)

        # 底部状态栏
        self.status_var = StringVar(value="正在初始化服务...")
        sb = ttk.Frame(self.window, relief=SUNKEN, padding=2)
        sb.pack(side="bottom", fill="x")
        self.status_label = ttk.Label(sb, textvariable=self.status_var, font=("微软雅黑", 9, "bold"))
        self.status_label.pack(side="left", padx=5)

        self.window.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

    def on_interval_entry_change(self, *args):
        raw_val = self.interval_var.get()
        if raw_val.isdigit():
            val = int(raw_val)
            if val > 0:
                self.update_config('check_interval', val, log_change=False)

    def hide_to_tray(self):
        self.window.withdraw()

    def toggle_auto_start(self):
        is_on = not self.config['auto_start']
        self.update_config('auto_start', is_on)
        try:
            key = OpenKey(HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, KEY_SET_VALUE)
            if is_on:
                cmd_path = f'"{executable}" "{path.abspath(__file__)}" --minimized'
                SetValueEx(key, "CampusNetAuto", 0, REG_SZ, cmd_path)
            else:
                try: 
                    DeleteValue(key, "CampusNetAuto")
                except: pass
            CloseKey(key)
        except Exception as e:
            self.log(f"❌ 写入注册表失败: {e}")

if __name__ == "__main__":
    # 单实例锁
    try:
        s = socket(AF_INET, SOCK_STREAM)
        s.bind(("127.0.0.1", 45681))
    except: 
        exit(0)

    is_min = "--minimized" in argv
    app = CampusNetworkAutoLogin(start_minimized=is_min)