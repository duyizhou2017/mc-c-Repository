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
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController

# ==========================================
# --- 0. 自动更新配置中心 ---
# ==========================================
CURRENT_VERSION = 1.0
VERSION_URL = "https://gitee.com/你的用户名/你的项目名/raw/master/version.txt"
CODE_URL = "https://gitee.com/你的用户名/你的项目名/raw/master/1.pyw"

def check_for_updates(launcher_root):
    try:
        with urllib.request.urlopen(VERSION_URL, timeout=3) as response:
            latest_version = float(response.read().decode('utf-8').strip())
        if latest_version > CURRENT_VERSION:
            launcher_root.after(0, lambda: ask_to_update(latest_version))
    except: pass

def ask_to_update(latest_version):
    ans = messagebox.askyesno("发现新版本！", f"检测到有新版本 V{latest_version} 可用。\n是否立即自动下载更新？")
    if ans:
        update_win = tk.Toplevel()
        update_win.title("正在更新...")
        update_win.geometry("260x80")
        update_win.attributes("-topmost", True)
        lbl = tk.Label(update_win, text="正在从云端下载最新核心文件...", font=("Microsoft YaHei", 9))
        lbl.pack(pady=10)
        progress = ttk.Progressbar(update_win, mode="indeterminate", length=200)
        progress.pack()
        progress.start(10)
        threading.Thread(target=download_and_restart, args=(update_win,), daemon=True).start()

def download_and_restart(update_win):
    try:
        current_file = sys.argv[0]
        temp_file = current_file + ".tmp"
        urllib.request.urlretrieve(CODE_URL, temp_file)
        if os.path.exists(current_file): os.remove(current_file)
        os.rename(temp_file, current_file)
        messagebox.showinfo("更新成功", "游戏已成功更新！即将自动重启。")
        update_win.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except Exception as e:
        messagebox.showerror("更新失败", f"更新失败: {e}")
        update_win.destroy()


# ==========================================
# --- 1. 后台联机服务端进程 ---
# ==========================================
def run_dedicated_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind(("127.0.0.1", 25565))
        server_socket.listen()
    except: return

    clients = {}
    player_data = {}
    client_id_counter = 1

    def handle_client(client_conn, client_id):
        nonlocal client_id_counter
        r, g, b = random.uniform(0.2, 1.0), random.uniform(0.2, 1.0), random.uniform(0.2, 1.0)
        player_name = f"Player_{client_id}"
        player_data[client_id] = {"x": 0, "y": 2, "z": 0, "color": [r, g, b], "name": player_name}
        
        broadcast(json.dumps({"type": "player_joined", "id": client_id, "color": [r, g, b], "name": player_name}))
        
        for existing_id, info in player_data.items():
            if existing_id != client_id:
                try: client_conn.sendall((json.dumps({"type": "player_joined", "id": existing_id, "color": info["color"], "name": info["name"]}) + "\n").encode())
                except: pass

        buffer = ""
        while True:
            try:
                data = client_conn.recv(1024).decode()
                if not data: break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line: continue
                    msg = json.loads(line)
                    if msg["type"] == "my_position":
                        if client_id in player_data:
                            player_data[client_id]["x"] = msg["x"]
                            player_data[client_id]["y"] = msg["y"]
                            player_data[client_id]["z"] = msg["z"]
                    elif msg["type"] in ["place_block", "break_block"]:
                        broadcast(json.dumps(msg))
            except: break

        if client_id in player_data: del player_data[client_id]
        if client_id in clients: del clients[client_id]
        broadcast(json.dumps({"type": "player_left", "id": client_id}))
        client_conn.close()

    def broadcast(message_str):
        payload = (message_str + "\n").encode()
        for conn in list(clients.values()):
            try: conn.sendall(payload)
            except: pass

    def position_sync_loop():
        while True:
            if player_data: broadcast(json.dumps({"type": "update_positions", "data": player_data}))
            time.sleep(0.03)

    threading.Thread(target=position_sync_loop, daemon=True).start()

    while True:
        try:
            conn, addr = server_socket.accept()
            cid = client_id_counter
            client_id_counter += 1
            clients[cid] = conn
            threading.Thread(target=handle_client, args=(conn, cid), daemon=True).start()
        except: break


# ==========================================
# --- 2. 核心 3D 游戏进程 ---
# ==========================================
def run_ursina_game(multiplayer_mode=False):
    # 使用字典/列表包装网络变量，方便在内部函数中修改
    net_status = {"socket": None, "connected": False}
    other_players = {}
    msg_queue = []

    app = Ursina()

    # --- 动态连接服务器函数 ---
    def connect_to_server(ip, port):
        # 1. 如果当前已经连接了服务器，先断开并清理现场
        if net_status["socket"]:
            try: net_status["socket"].close()
            except: pass
            net_status["socket"] = None
            net_status["connected"] = False
        
        # 清理屏幕上其他服务器的玩家模型
        for p_id in list(other_players.keys()):
            destroy(other_players[p_id])
            del other_players[p_id]
        
        msg_queue.clear()

        # 2. 尝试建立新连接
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((ip, port))
            net_status["socket"] = s
            net_status["connected"] = True
            
            # 开启新接收线程
            def receive_loop():
                buffer = ""
                while net_status["connected"]:
                    try:
                        data = s.recv(1024).decode()
                        if not data: break
                        buffer += data
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if line: msg_queue.append(json.loads(line))
                    except: break
                net_status["connected"] = False

            threading.Thread(target=receive_loop, daemon=True).start()
            server_info_text.text = f"当前连接: {ip}:{port}"
            server_info_text.color = color.green
        except Exception as e:
            server_info_text.text = f"连接失败: {ip}:{port}"
            server_info_text.color = color.red
            net_status["socket"] = None
            net_status["connected"] = False

    # 基础环境
    sun_light = DirectionalLight(parent=scene, y=2, z=3, rotation=(45, -45, 0))
    ambient_light = AmbientLight(parent=scene, color=color.rgba(150, 150, 150, 255))

    class Voxel(Button):
        def __init__(self, position=(0,0,0)):
            super().__init__(
                parent=scene, position=position, model='cube', texture='white_cube',            
                color=color.tint(color.lime, random.uniform(-0.05, 0.05)), highlight_color=color.yellow,       
            )
        def input(self, key):
            if self.hovered and not lobby_panel.enabled: # 大厅开启时禁止放方块
                if key == 'right mouse down':
                    pos = self.position + mouse.normal
                    if multiplayer_mode and net_status["connected"]: 
                        try: net_status["socket"].sendall((json.dumps({"type": "place_block", "x": pos.x, "y": pos.y, "z": pos.z}) + "\n").encode())
                        except: pass
                    else: Voxel(position=pos)
                if key == 'left mouse down':
                    if multiplayer_mode and net_status["connected"]: 
                        try: net_status["socket"].sendall((json.dumps({"type": "break_block", "x": self.position.x, "y": self.position.y, "z": self.position.z}) + "\n").encode())
                        except: pass
                    else: destroy(self)

    # 生成基础地面
    for z in range(16):
        for x in range(16): Voxel(position=(x, 0, z))

    player = FirstPersonController()
    player.y = 2  
    death_text = Text(text='YOU DIE', origin=(0, 0), scale=5, color=color.red, background=True)
    death_text.disable() 
    player.is_dead = False

    def respawn():
        player.position = (8, 5, 8)  
        player.is_dead = False
        death_text.disable()         

    # --- 📊 游戏内服务器大厅 UI 界面设计 ---
    lobby_panel = Entity(parent=camera.ui, model='quad', scale=(0.6, 0.7), color=color.black66, enabled=False)
    Text(parent=lobby_panel, text="=== 服务器大厅 ===", scale=2, origin=(0, -3), color=color.gold)
    
    # 提示文字
    server_info_text = Text(parent=lobby_panel, text="未连接到任何服务器", scale=1.2, origin=(0, -2.2), color=color.white)

    # 按钮点击回调工厂
    def make_connect_callback(ip, port):
        return lambda: connect_to_server(ip, port)

    # 服务器列表配置 (你可以在这里随意添加更多的公网或局域网服务器)
    server_list = [
        {"name": "主线联机 1 号服", "ip": "127.0.0.1", "port": 25565},
        {"name": "生存冒险 2 号服", "ip": "127.0.0.1", "port": 25566}, # 假设你开了第二个端口
        {"name": "红石科技 3 号服", "ip": "127.0.0.1", "port": 25567},
    ]

    # 循环生成服务器大厅内的按钮
    for idx, s_info in enumerate(server_list):
        btn = Button(
            parent=lobby_panel, 
            text=f"{s_info['name']} ({s_info['ip']}:{s_info['port']})",
            scale=(0.8, 0.08), 
            y=0.1 - (idx * 0.12),
            color=color.azure
        )
        # 绑定点击切换服务器事件
        btn.on_click = make_connect_callback(s_info["ip"], s_info["port"])

    Text(parent=lobby_panel, text="提示: 按 [M] 键可随时关闭大厅界面", scale=1, y=-0.4, origin=(0, 0), color=color.light_gray)

    # 如果是多人模式启动，默认先连1号服
    if multiplayer_mode:
        connect_to_server("127.0.0.1", 25565)

    # --- 按键监听：用于控制大厅显示/隐藏 ---
    def input(key):
        if key == 'm':
            # 切换大厅开关状态
            lobby_panel.enabled = not lobby_panel.enabled
            # 开启大厅时释放鼠标，关闭大厅时锁定鼠标回到游戏
            mouse.locked = not lobby_panel.enabled
            player.enabled = not lobby_panel.enabled

    # 每帧更新
    def update():
        if player.y < -10 and not player.is_dead:
            player.is_dead = True
            death_text.enable()  
            invoke(respawn, delay=1.5)

        # 多人模式下定时发送本地位置
        if multiplayer_mode and net_status["connected"]:
            try: 
                net_status["socket"].sendall((json.dumps({"type": "my_position", "x": player.x, "y": player.y, "z": player.z}) + "\n").encode())
            except: 
                net_status["connected"] = False

        # 消费网络事件队列
        while msg_queue:
            msg = msg_queue.pop(0)
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
                if not any(isinstance(e, Voxel) and e.position == target_pos for e in scene.entities): Voxel(position=target_pos)
            elif m_type == "break_block":
                target_pos = Vec3(msg["x"], msg["y"], msg["z"])
                to_destroy = [e for e in scene.entities if isinstance(e, Voxel) and e.position == target_pos]
                for block in to_destroy: destroy(block)

    app.run()


# ==========================================
# --- 3. 启动器功能函数（Tkinter） ---
# ==========================================
def start_game():
    mode_selected = game_mode_var.get()
    if mode_selected == 1:
        game_process = multiprocessing.Process(target=run_ursina_game, args=(False,))
        game_process.start()
    else:
        # 启动本地默认的 25565 后台独立服务端
        server_process = multiprocessing.Process(target=run_dedicated_server)
        server_process.daemon = True 
        server_process.start()
        time.sleep(0.6)  
        game_process = multiprocessing.Process(target=run_ursina_game, args=(True,))
        game_process.start()
    root.destroy() 

def open_website(): webbrowser.open("http://minecraft.net")
def show_author(): messagebox.showinfo("关于作者", "本程序由 mojang AB·杜奕洲·notch·Gemini共同制作\n感谢您的使用")
def show_more(): messagebox.showinfo("更多", f"当前版本: V{CURRENT_VERSION}\n期待后续更新......")


# ==========================================
# --- 4. 程序主入口 ---
# ==========================================
if __name__ == '__main__':
    multiprocessing.freeze_support()

    if sys.executable.endswith("pythonw.exe") or sys.stderr is None:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = open(os.devnull, "w")

    root = tk.Tk()
    root.title("Minecraft 自动安全退出版")
    root.geometry("320x340")  
    root.resizable(False, False)

    title_label = tk.Label(root, text="MINECRAFT PYTHON", font=("Arial Black", 14, "bold"), fg="#333333")
    title_label.pack(pady=10)

    ver_label = tk.Label(root, text=f"Version {CURRENT_VERSION}", font=("Arial", 8), fg="#999999")
    ver_label.pack()

    mode_frame = tk.LabelFrame(root, text=" 选择游戏模式 ", font=("Microsoft YaHei", 10, "bold"), padx=10, pady=5)
    mode_frame.pack(fill="x", padx=20, pady=5)

    game_mode_var = tk.IntVar()
    game_mode_var.set(1) 

    r1 = tk.Radiobutton(mode_frame, text="本地单人模式", variable=game_mode_var, value=1, font=("Microsoft YaHei", 10))
    r1.pack(anchor="w", side="left", padx=10)

    r2 = tk.Radiobutton(mode_frame, text="局域网多人模式", variable=game_mode_var, value=2, font=("Microsoft YaHei", 10))
    r2.pack(anchor="w", side="left", padx=10)

    btn1 = tk.Button(root, text=" 启 动 游 戏 ", command=start_game, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 12, "bold"))
    btn1.pack(fill="x", padx=20, pady=10)  

    btn2 = tk.Button(root, text="作者信息", command=show_author, font=("Microsoft YaHei", 10))
    btn2.pack(fill="x", padx=20, pady=3)

    btn3 = tk.Button(root, text="访问官网", command=open_website, font=("Microsoft YaHei", 10))
    btn3.pack(fill="x", padx=20, pady=3)   

    btn4 = tk.Button(root, text="更多内容", command=show_more, font=("Microsoft YaHei", 10))
    btn4.pack(fill="x", padx=20, pady=3)   

    threading.Thread(target=check_for_updates, args=(root,), daemon=True).start()

    root.mainloop()