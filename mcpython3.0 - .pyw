import sys
import os
import random
import time
import webbrowser
import multiprocessing
import threading
import socket
import json
import urllib.request
import tkinter as tk
from tkinter import messagebox, ttk
from queue import Queue

# 延迟导入 Ursina 相关的库，避免在更新阶段就初始化 3D 引擎导致卡顿或报错
def import_ursina():
    global Ursina, FirstPersonController, color, scene, DirectionalLight, AmbientLight, Button, camera, Entity, Text, mouse, destroy, invoke, Vec3, held_keys
    from ursina import Ursina, color, scene, DirectionalLight, AmbientLight, Button, camera, Entity, Text, mouse, destroy, invoke, Vec3, held_keys
    from ursina.prefabs.first_person_controller import FirstPersonController

# ==========================================
# --- 0. 全局配置 ---
# ==========================================
CURRENT_VERSION = 2.0
VERSION_URL = "https://raw.githubusercontent.com/duyizhou2017/mc-c-Repository/main/version.txt"
CODE_URL = "https://raw.githubusercontent.com/duyizhou2017/mc-c-Repository/main/mcpython2.0.pyw"
SAVE_FILE = "map_save.json"

# ==========================================
# --- 1. 独立启动更新界面（异步不卡顿版） ---
# ==========================================
class SplashUpdater:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Minecraft Python 启动检查")
        self.root.geometry("360x180")
        self.root.resizable(False, False)
        
        # 屏幕居中
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"+{int((screen_width-360)/2)}+{int((screen_height-180)/2)}")
        
        self.lbl_title = tk.Label(self.root, text="正在初始化游戏配置...", font=("Microsoft YaHei", 12, "bold"))
        self.lbl_title.pack(pady=15)
        
        self.lbl_status = tk.Label(self.root, text="正在准备本地资源...", font=("Microsoft YaHei", 9), fg="gray")
        self.lbl_status.pack(pady=5)
        
        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=280)
        self.progress.pack(pady=10)
        self.progress.start(15)
        
        # 先让窗口完全显示，再在后台进行联网检查，彻底杜绝双击卡死
        self.root.after(200, self.start_async_check)
        self.root.mainloop()

    def start_async_check(self):
        self.lbl_status.config(text="正在连接云端检查更新...")
        threading.Thread(target=self.check_update_logic, daemon=True).start()

    def check_update_logic(self):
        try:
            req = urllib.request.Request(VERSION_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=3) as response:
                latest_version = float(response.read().decode('utf-8').strip())
            
            if latest_version > CURRENT_VERSION:
                self.root.after(0, lambda: self.prompt_update(latest_version))
            else:
                self.root.after(0, self.finish_and_launch)
        except Exception:
            # 联网失败直接跳过更新，进入游戏，1秒后自动切换
            self.root.after(0, lambda: self.skip_update("无法连接到更新服务器，即将直接进入游戏..."))

    def prompt_update(self, latest_version):
        self.progress.stop()
        self.progress.config(mode="determinate", value=0)
        self.lbl_title.config(text="发现新版本！", fg="#4CAF50")
        self.lbl_status.config(text=f"当前版本: V{CURRENT_VERSION}  ->  最新版本: V{latest_version}", fg="black")
        
        ans = messagebox.askyesno("发现新版本！", f"检测到有新版本 V{latest_version} 可用。\n是否立即自动下载更新？", parent=self.root)
        if ans:
            self.lbl_title.config(text="正在更新核心文件...")
            self.progress.config(mode="indeterminate")
            self.progress.start(10)
            threading.Thread(target=self.download_logic, daemon=True).start()
        else:
            self.finish_and_launch()

    def download_logic(self):
        try:
            current_file = sys.argv[0]
            temp_file = current_file + ".tmp"
            
            if os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass
                
            urllib.request.urlretrieve(CODE_URL, temp_file)
            
            if os.path.exists(current_file): 
                try: os.remove(current_file)
                except: os.rename(current_file, current_file + f".v{CURRENT_VERSION}.old")
            os.rename(temp_file, current_file)
            
            messagebox.showinfo("更新成功", "游戏已成功更新！即将自动重启。", parent=self.root)
            self.root.destroy()
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            messagebox.showerror("更新失败", f"下载更新时出错: {e}", parent=self.root)
            self.finish_and_launch()

    def skip_update(self, reason):
        self.progress.stop()
        self.lbl_status.config(text=reason, fg="orange")
        self.root.after(800, self.finish_and_launch)

    def finish_and_launch(self):
        self.root.destroy()
        create_main_launcher()


# ==========================================
# --- 2. 优化后的联机服务端进程 ---
# ==========================================
def run_dedicated_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind(("0.0.0.0", 25565))
        server_socket.listen()
    except Exception:
        return

    clients = {}
    player_data = {}
    client_id_counter = 1
    lock = threading.Lock()

    def handle_client(client_conn, client_id):
        nonlocal client_id_counter
        r, g, b = random.uniform(0.2, 1.0), random.uniform(0.2, 1.0), random.uniform(0.2, 1.0)
        player_name = f"Player_{client_id}"
        
        with lock:
            player_data[client_id] = {"x": 0, "y": 7, "z": 0, "color": [r, g, b], "name": player_name}
        
        broadcast(json.dumps({"type": "player_joined", "id": client_id, "color": [r, g, b], "name": player_name}))
        
        with lock:
            for existing_id, info in player_data.items():
                if existing_id != client_id:
                    try: client_conn.sendall((json.dumps({"type": "player_joined", "id": existing_id, "color": info["color"], "name": info["name"]}) + "\n").encode())
                    except: pass

        buffer = ""
        while True:
            try:
                data = client_conn.recv(2048).decode('utf-8')
                if not data: break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line: continue
                    msg = json.loads(line)
                    if msg["type"] == "my_position":
                        with lock:
                            if client_id in player_data:
                                player_data[client_id].update({"x": msg["x"], "y": msg["y"], "z": msg["z"]})
                    elif msg["type"] in ["place_block", "break_block"]:
                        broadcast(json.dumps(msg))
            except: 
                break

        with lock:
            if client_id in player_data: del player_data[client_id]
            if client_id in clients: del clients[client_id]
        broadcast(json.dumps({"type": "player_left", "id": client_id}))
        client_conn.close()

    def broadcast(message_str):
        payload = (message_str + "\n").encode('utf-8')
        with lock:
            for conn in list(clients.values()):
                try: conn.sendall(payload)
                except: pass

    def position_sync_loop():
        while True:
            with lock:
                if player_data: 
                    broadcast(json.dumps({"type": "update_positions", "data": player_data}))
            time.sleep(0.03)

    threading.Thread(target=position_sync_loop, daemon=True).start()

    while True:
        try:
            conn, addr = server_socket.accept()
            with lock:
                cid = client_id_counter
                client_id_counter += 1
                clients[cid] = conn
            threading.Thread(target=handle_client, args=(conn, cid), daemon=True).start()
        except: 
            break


# ==========================================
# --- 3. 核心 3D 游戏进程 ---
# ==========================================
def run_ursina_game(multiplayer_mode=False):
    import_ursina()  
    
    net_status = {"socket": None, "connected": False}
    other_players = {}
    msg_queue = Queue() 

    app = Ursina()
    app.hotkeys = {'toggle_fullscreen': 'f11'} 

    BLOCK_TYPES = [
        {"name": "草方块", "color": color.rgb(108, 179, 71)},     
        {"name": "泥土块", "color": color.rgb(134, 96, 67)},      
        {"name": "石头块", "color": color.rgb(125, 125, 125)},    
        {"name": "木头块", "color": color.rgb(197, 150, 93)},     
        {"name": "红砖块", "color": color.rgb(163, 71, 55)}       
    ]
    current_block_index = 0  

    def connect_to_server(ip, port):
        if net_status["socket"]:
            try: net_status["socket"].close()
            except: pass
            net_status["socket"] = None
            net_status["connected"] = False
            
        for p_id in list(other_players.keys()):
            destroy(other_players[p_id])
            del other_players[p_id]
            
        while not msg_queue.empty(): msg_queue.get()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, port))
            net_status["socket"] = s
            net_status["connected"] = True
            
            def receive_loop():
                buffer = ""
                while net_status["connected"]:
                    try:
                        data = s.recv(2048).decode('utf-8')
                        if not data: break
                        buffer += data
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if line: msg_queue.put(json.loads(line))
                    except: break
                net_status["connected"] = False

            threading.Thread(target=receive_loop, daemon=True).start()
            server_info_text.text = f"当前连接: {ip}:{port}"
            server_info_text.color = color.green
        except Exception:
            server_info_text.text = f"连接失败: {ip}:{port}"
            server_info_text.color = color.red
            net_status["socket"] = None
            net_status["connected"] = False

    sun_light = DirectionalLight(parent=scene, y=2, z=3, rotation=(45, -45, 0))
    ambient_light = AmbientLight(parent=scene, color=color.rgba(140, 140, 140, 255))

    class Voxel(Button):
        def __init__(self, position=(0,0,0), custom_color=None):
            chosen_color = custom_color if custom_color else BLOCK_TYPES[current_block_index]["color"]
            super().__init__(
                parent=scene, position=position, model='cube', texture='white_cube',            
                color=color.tint(chosen_color, random.uniform(-0.03, 0.03)), 
                highlight_color=color.white,       
            )
            
        def input(self, key):
            if self.hovered and not lobby_panel.enabled: 
                if key == 'right mouse down':
                    pos = self.position + mouse.normal
                    if multiplayer_mode and net_status["connected"]: 
                        c = BLOCK_TYPES[current_block_index]["color"]
                        try: net_status["socket"].sendall((json.dumps({
                            "type": "place_block", "x": pos.x, "y": pos.y, "z": pos.z,
                            "r": c.r, "g": c.g, "b": c.b
                        }) + "\n").encode('utf-8'))
                        except: pass
                    else: 
                        Voxel(position=pos)
                if key == 'left mouse down':
                    if multiplayer_mode and net_status["connected"]: 
                        try: net_status["socket"].sendall((json.dumps({"type": "break_block", "x": self.position.x, "y": self.position.y, "z": self.position.z}) + "\n").encode('utf-8'))
                        except: pass
                    else: 
                        destroy(self)

    # 地图存档加载机制与安全地面生成机制
    saved_blocks = []
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                saved_blocks = json.load(f)
        except: pass

    if isinstance(saved_blocks, list) and saved_blocks:
        for b in saved_blocks:
            try: Voxel(position=(b['x'], b['y'], b['z']), custom_color=color.rgb(b['c'][0], b['c'][1], b['c'][2]))
            except: pass
    else:
        # 如果没有存档，生成一个位于 Y=5 高度的安全起始大平台，防止掉虚空
        for z in range(16):
            for x in range(16): 
                Voxel(position=(x, 5, z), custom_color=color.rgb(108, 179, 71))

    # 初始化第一人称人物（安全出生点高度 Y=7）
    player = FirstPersonController()
    player.position = (8, 7, 8)  
    player.is_dead = False

    def respawn():
        player.position = (8, 7, 8)  
        player.is_dead = False
        death_text.disable()

    death_text = Text(text="你死了！正在复活...", scale=3, origin=(0, 0), color=color.red, enabled=False)
    hotbar_panel = Entity(parent=camera.ui, model='quad', scale=(0.5, 0.06), position=(0, -0.44), color=color.black33)
    hotbar_text = Text(parent=hotbar_panel, text="", scale=1.4, position=(-0.45, 0), color=color.white)

    def update_hotbar_ui():
        hotbar_text.text = f"当前选块: {BLOCK_TYPES[current_block_index]['name']}"

    update_hotbar_ui()

    lobby_panel = Entity(parent=camera.ui, model='quad', scale=(0.6, 0.7), color=color.black66, enabled=False)
    Text(parent=lobby_panel, text="=== 服务器大厅 ===", scale=2, origin=(0, -3), color=color.gold)
    server_info_text = Text(parent=lobby_panel, text="未连接到任何服务器", scale=1.2, origin=(0, -2.2), color=color.white)

    def make_connect_callback(ip, port):
        return lambda: connect_to_server(ip, port)

    server_list = [
        {"name": "本地测试服", "ip": "127.0.0.1", "port": 25565},
    ]

    for idx, s_info in enumerate(server_list):
        btn = Button(
            parent=lobby_panel, 
            text=f"{s_info['name']} ({s_info['ip']}:{s_info['port']})",
            scale=(0.8, 0.08), y=0.1 - (idx * 0.12), color=color.azure
        )
        btn.on_click = make_connect_callback(s_info["ip"], s_info["port"])

    Text(parent=lobby_panel, text="提示: [Ctrl+5] 大厅 | [1-5] 物品切换 | 快速连按 10 次 [空格] 存档退出", scale=1, y=-0.4, origin=(0, 0), color=color.light_gray)

    if multiplayer_mode:
        connect_to_server("127.0.0.1", 25565)

    last_toggle_time = 0
    space_click_count = 0
    last_space_time = 0

    def save_and_exit_game():
        current_map_data = []
        for e in scene.entities:
            if isinstance(e, Voxel):
                current_map_data.append({
                    'x': int(e.position.x), 'y': int(e.position.y), 'z': int(e.position.z),
                    'c': [e.color.r, e.color.g, e.color.b]
                })
        try:
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(current_map_data, f)
        except: pass
            
        if net_status["socket"]:
            try: net_status["socket"].close()
            except: pass
        os._exit(0)

    def input(key):
        nonlocal space_click_count, last_space_time, current_block_index
        
        if key == 'space':
            current_time = time.time()
            if current_time - last_space_time > 1.2:
                space_click_count = 1
            else:
                space_click_count += 1
            last_space_time = current_time
            if space_click_count >= 10:
                save_and_exit_game()

        if not lobby_panel.enabled:
            if key in ['1', '2', '3', '4', '5']:
                current_block_index = int(key) - 1
                update_hotbar_ui()

    def update():
        nonlocal last_toggle_time
        
        if (held_keys['control'] and held_keys['5']) and (time.time() - last_toggle_time > 0.3):
            last_toggle_time = time.time()
            lobby_panel.enabled = not lobby_panel.enabled
            if lobby_panel.enabled:
                mouse.locked, mouse.visible, player.enabled = False, True, False
                hotbar_panel.disable() 
            else:
                mouse.locked, mouse.visible, player.enabled = True, False, True
                hotbar_panel.enable()

        if player.y < -10 and not player.is_dead:
            player.is_dead = True
            death_text.enable()  
            invoke(respawn, delay=1.5)

        if multiplayer_mode and net_status["connected"]:
            try: net_status["socket"].sendall((json.dumps({"type": "my_position", "x": player.x, "y": player.y, "z": player.z}) + "\n").encode('utf-8'))
            except: net_status["connected"] = False

        while not msg_queue.empty():
            msg = msg_queue.get()
            m_type = msg.get("type")
            if m_type == "player_joined":
                idx = msg["id"]
                if idx not in other_players:
                    c = msg["color"]
                    p_model = Entity(model='cube', color=color.rgb(c[0], c[1], c[2]), scale=(1, 2, 1))
                    name_tag = Text(text=msg["name"], parent=p_model, position=(0, 0.8, 0), scale=5, origin=(0, 0), color=color.white)
                    name_tag.billboard = True 
                    other_players[idx] = p_model
            elif m_type == "player_left":
                idx = msg["id"]
                if idx in other_players:
                    destroy(other_players[idx])
                    del other_players[idx]
            elif m_type == "update_positions":
                for idx, info in msg["data"].items():
                    if int(idx) in other_players: other_players[int(idx)].position = Vec3(info["x"], info["y"], info["z"])
            elif m_type == "place_block":
                target_pos = Vec3(msg["x"], msg["y"], msg["z"])
                block_color = color.rgb(msg.get("r", 1), msg.get("g", 1), msg.get("b", 1))
                if not any(isinstance(e, Voxel) and e.position == target_pos for e in scene.entities): 
                    Voxel(position=target_pos, custom_color=block_color)
            elif m_type == "break_block":
                target_pos = Vec3(msg["x"], msg["y"], msg["z"])
                to_destroy = [e for e in scene.entities if isinstance(e, Voxel) and e.position == target_pos]
                for block in to_destroy: destroy(block)

    app.run()


# ==========================================
# --- 4. 启动器主控制界面 ---
# ==========================================
def create_main_launcher():
    root = tk.Tk()
    root.title(f"Minecraft Python 启动器 V{CURRENT_VERSION}")
    root.geometry("340x360")  
    root.resizable(False, False)

    # 居中
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"+{int((sw-340)/2)}+{int((sh-360)/2)}")

    def start_game():
        root.withdraw()
        mode_selected = game_mode_var.get()
        if mode_selected == 1:
            game_process = multiprocessing.Process(target=run_ursina_game, args=(False,))
            game_process.start()
        else:
            server_process = multiprocessing.Process(target=run_dedicated_server)
            server_process.daemon = True 
            server_process.start()
            time.sleep(0.5)  
            game_process = multiprocessing.Process(target=run_ursina_game, args=(True,))
            game_process.start()

        def monitor_game_process():
            game_process.join()  
            root.after(0, root.deiconify)

        threading.Thread(target=monitor_game_process, daemon=True).start()

    title_label = tk.Label(root, text="MINECRAFT PYTHON", font=("Arial Black", 15, "bold"), fg="#2C3E50")
    title_label.pack(pady=12)

    ver_label = tk.Label(root, text=f"Gold Master Edition - Version {CURRENT_VERSION}", font=("Arial", 8, "italic"), fg="#7F8C8D")
    ver_label.pack()

    mode_frame = tk.LabelFrame(root, text=" 模式选择 ", font=("Microsoft YaHei", 10, "bold"), padx=10, pady=8)
    mode_frame.pack(fill="x", padx=20, pady=8)

    game_mode_var = tk.IntVar(value=1) 

    r1 = tk.Radiobutton(mode_frame, text="本地单人游戏", variable=game_mode_var, value=1, font=("Microsoft YaHei", 10))
    r1.pack(anchor="w", side="left", padx=15)

    r2 = tk.Radiobutton(mode_frame, text="局域网多人联机", variable=game_mode_var, value=2, font=("Microsoft YaHei", 10))
    r2.pack(anchor="w", side="left", padx=15)

    btn1 = tk.Button(root, text=" 进 入 游 戏 ", command=start_game, bg="#2ECC71", fg="white", font=("Microsoft YaHei", 12, "bold"), relief="flat", bd=0)
    btn1.pack(fill="x", padx=20, pady=12, ipady=4)  

    tk.Button(root, text="制作人员信息", command=lambda: messagebox.showinfo("开发者名单", "本程序由杜奕洲制作\n感谢您的游玩与支持！"), font=("Microsoft YaHei", 9)).pack(fill="x", padx=20, pady=2)
    tk.Button(root, text="访问官方网站", command=lambda: webbrowser.open("http://minecraft.net"), font=("Microsoft YaHei", 9)).pack(fill="x", padx=20, pady=2)   
    tk.Button(root, text="扩展与未来规划", command=lambda: messagebox.showinfo("版本规划", f"当前版本: 2.0 稳定版\n后续计划：增加聊天室、动态光影、无限地形生成。"), font=("Microsoft YaHei", 9)).pack(fill="x", padx=20, pady=2)   

    root.mainloop()


# ==========================================
# --- 5. 程序主入口 ---
# ==========================================
if __name__ == '__main__':
    # 必须首先调用多进程冻结支持，解决双击及打包后的秒退问题
    multiprocessing.freeze_support()

    # 安全地启动第一个生命周期：展示更新加载框
    SplashUpdater()