#!/usr/bin/python3

from PyQt6 import QtGui, QtCore
import PyQt6.QtWidgets as QtWidgets
from PyQt6.QtWidgets import QApplication

import threading
import sys
import os
import socket
import platform
import argparse
import shlex
try:
    import paramiko
except ImportError:
    print("Warning: paramiko is not installed. Password-based SSH will not be available. Run 'pip install paramiko'")
    paramiko = None
import getpass
from subprocess import Popen, PIPE
import traceback

is_running = False

THEME_LIGHT = {
    "bg": "#f0f5f9", "text": "#333333", "sub_text": "#666666", "title_text": "#000000",
    "border": "#f0f5f9", "progress_bg": "#c9d6df", "progress_chunk": "#0078d4",
    "progress_text": "#555555"
}

THEME_DARK = {
    "bg": "#191919", "text": "#e0e0e0", "sub_text": "#a0a0a0", "title_text": "#ffffff",
    "border": "#191919", "progress_bg": "#3c3c3c", "progress_chunk": "#0078d4",
    "progress_text": "#e0e0e0"
}

def res(res_name):
    _script_path = os.path.dirname(os.path.realpath(__file__))
    _resource_folder = os.path.join(_script_path, "resources")
    return os.path.join(_resource_folder, res_name)


class GPUInfoPanel(QtWidgets.QWidget):
    signal_update = QtCore.pyqtSignal(dict)

    def __init__(self, *args, dark_mode=False, **kwargs):
        super(GPUInfoPanel, self).__init__(*args, **kwargs)
        self.setObjectName("GPU_PNL")
        self.theme = THEME_DARK if dark_mode else THEME_LIGHT
        self._init_widgets()
        self._init_layout()
        self._apply_styles()
        self.signal_update.connect(self.update_info)

    def _init_widgets(self):
        self.lbl_gpumodel = QtWidgets.QLabel("Graphics Device")
        self.lbl_gpuid = QtWidgets.QLabel("#0")
        self.lbl_pcibusid = QtWidgets.QLabel("bus: 00:00.0")
        self.lbl_temp = QtWidgets.QLabel("N/A")
        self.lbl_fan = QtWidgets.QLabel("N/A")
        self.lbl_utilization = QtWidgets.QLabel("N/A")
        self.lbl_clock = QtWidgets.QLabel("N/A")
        self.lbl_mem_used = QtWidgets.QLabel("N/A")
        self.sep_mem = QtWidgets.QFrame()
        self.lbl_mem_total = QtWidgets.QLabel("N/A")
        self.lbl_power_draw = QtWidgets.QLabel("N/A")
        self.sep_power = QtWidgets.QFrame()
        self.lbl_power_limit = QtWidgets.QLabel("N/A")
        self.progress_mem = QtWidgets.QProgressBar()
        self.progress_power = QtWidgets.QProgressBar()
        self.icon_temp = QtWidgets.QPushButton("")
        self.icon_fan = QtWidgets.QPushButton("")
        self.icon_utilization = QtWidgets.QPushButton("")
        self.icon_clock = QtWidgets.QPushButton("")
        self.icon_mem = QtWidgets.QPushButton("")
        self.icon_power = QtWidgets.QPushButton("")

        # 明确设置进度条显示格式
        self.progress_mem.setFormat('%p%')
        self.progress_power.setFormat('%p%')


    def _init_layout(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(10, 5, 10, 10)
        main_layout.setSpacing(10)

        main_layout.addWidget(self.lbl_gpumodel)
        id_layout = QtWidgets.QHBoxLayout()
        id_layout.addWidget(self.lbl_gpuid)
        id_layout.addWidget(self.lbl_pcibusid)
        id_layout.addStretch()
        main_layout.addLayout(id_layout)
        
        stats_layout = QtWidgets.QHBoxLayout()
        for icon, label in [(self.icon_utilization, self.lbl_utilization), (self.icon_temp, self.lbl_temp), (self.icon_fan, self.lbl_fan), (self.icon_clock, self.lbl_clock)]:
            stats_layout.addWidget(icon)
            stats_layout.addWidget(label)
            if label is not self.lbl_clock: stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

        bars_layout = QtWidgets.QGridLayout()
        bars_layout.setColumnStretch(2, 1) # 让进度条占据所有剩余空间
        
        # 内存条布局
        bars_layout.addWidget(self.icon_mem, 0, 0)
        bars_layout.addLayout(self._create_value_total_layout(self.lbl_mem_used, self.sep_mem, self.lbl_mem_total), 0, 1)
        bars_layout.addWidget(self.progress_mem, 0, 2)
        
        # 功耗条布局
        bars_layout.addWidget(self.icon_power, 1, 0)
        bars_layout.addLayout(self._create_value_total_layout(self.lbl_power_draw, self.sep_power, self.lbl_power_limit), 1, 1)
        bars_layout.addWidget(self.progress_power, 1, 2)
        
        main_layout.addLayout(bars_layout)
    
    def _apply_styles(self):
        theme = self.theme
        self.setStyleSheet(f"""
            QWidget#GPU_PNL {{ background-color: {theme['bg']}; border-bottom: 1px solid {theme['border']}; }}
            QLabel {{ color: {theme['text']}; background-color: transparent; }}
            QLabel#lbl_gpumodel {{ font-size: 22px; font-weight: bold; color: {theme['title_text']}; }}
            QLabel#lbl_gpuid, QLabel#lbl_pcibusid {{ font-size: 11px; color: {theme['sub_text']}; }}
            QLabel[class="value_total_label"] {{ font-size: 10px; qproperty-alignment: 'AlignCenter'; }}
            QPushButton {{ border: none; background-color: transparent; }}
            QFrame {{ background-color: {theme['border']}; }}
            QProgressBar {{
                color: {theme['progress_text']};
                border: 1px solid {theme['border']};
                padding: 1px;
                border-radius: 8px;
                background-color: {theme['progress_bg']};
                text-align: center;
                height: 20px;
            }}
            QProgressBar::chunk {{ background-color: {theme['progress_chunk']}; border-radius: 7px; }}
        """)
        self.lbl_gpumodel.setObjectName("lbl_gpumodel")
        self.lbl_gpumodel.setWordWrap(True)
        self.lbl_gpuid.setObjectName("lbl_gpuid")
        self.lbl_pcibusid.setObjectName("lbl_pcibusid")
        
        icon_size = 24
        icons_map = {
            self.icon_utilization: "gear.svg", self.icon_mem: "ram.svg", self.icon_fan: "fan.svg",
            self.icon_temp: "thermometer.svg", self.icon_clock: "wave.svg", self.icon_power: "gauge.svg"
        }
        for icon_widget, icon_file in icons_map.items():
            icon_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            icon_widget.setFixedSize(icon_size, icon_size)
            icon_path = res(icon_file)
            if os.path.exists(icon_path):
                icon_widget.setIcon(QtGui.QIcon(icon_path))
                icon_widget.setIconSize(icon_widget.size())
            else:
                print(f"Warning: Icon file not found at {icon_path}")

    def _create_value_total_layout(self, value_label, separator, total_label):
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0,0,0,0)
        value_label.setProperty("class", "value_total_label")
        total_label.setProperty("class", "value_total_label")
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        layout.addWidget(value_label)
        layout.addWidget(separator)
        layout.addWidget(total_label)
        return layout

    @QtCore.pyqtSlot(dict)
    def update_info(self, smi_data):
        self.lbl_gpuid.setText(f'#{smi_data.get("index", "?")}')
        self.lbl_pcibusid.setText(f'pci: {smi_data.get("pci.bus_id", "N/A")}')
        self.lbl_gpumodel.setText(smi_data.get("name", "Unknown GPU"))
        self.lbl_utilization.setText(f'{smi_data.get("utilization.gpu", "0")}%')
        self.lbl_clock.setText(f'{smi_data.get("clocks.current.graphics", "0")}MHz')
        self.lbl_mem_used.setText(f'{smi_data.get("memory.used", "0")}M')
        self.lbl_mem_total.setText(f'{smi_data.get("memory.total", "0")}M')
        temp = smi_data.get("temperature.gpu", "N/A")
        self.lbl_temp.setText(f"{temp}\u2103" if temp != "N/A" else "N/A")
        fan_speed = smi_data.get("fan.speed", "N/A")
        self.lbl_fan.setText("N/A" if "Not Supported" in fan_speed or "N/A" in fan_speed else f"{fan_speed}%")
        self.lbl_power_draw.setText(f'{smi_data.get("power.draw", "0")}W')
        self.lbl_power_limit.setText(f'{smi_data.get("enforced.power.limit", "0")}W')
        
        mem_used = float(smi_data.get("memory.used", 0)); mem_total = float(smi_data.get("memory.total", 1))
        mem_percentage = int(mem_used * 100 / mem_total) if mem_total > 0 else 0
        self.progress_mem.setValue(mem_percentage)
        
        power_draw = float(smi_data.get("power.draw", 0)); power_limit = float(smi_data.get("enforced.power.limit", 1))
        power_percentage = int(power_draw * 100 / power_limit) if power_limit > 0 else 0
        self.progress_power.setValue(power_percentage)

class MainWindow(QtWidgets.QWidget):
    signal_addnew = QtCore.pyqtSignal()
    
    def __init__(self, *args, window_name, dark_mode=False):
        super(MainWindow, self).__init__(*args)
        self.window_name = window_name
        self.dark_mode = dark_mode
        self.panel_list = []
        self.cond_pnl = threading.Condition()
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.init_ui()
        self.signal_addnew.connect(self.add_new_panel)
        
    def init_ui(self):
        self.setWindowTitle(self.window_name)
        self.setObjectName("MainWindow")
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        bg_color = THEME_DARK["bg"] if self.dark_mode else THEME_LIGHT["bg"]
        self.setStyleSheet(f"QWidget#MainWindow {{ background-color: {bg_color}; }}")
        self.setMinimumWidth(480)
        icon_path = res("graphic-card.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

    @QtCore.pyqtSlot()
    def add_new_panel(self):
        with self.cond_pnl:
            pnl = GPUInfoPanel(parent=self, dark_mode=self.dark_mode)
            self.main_layout.addWidget(pnl)
            self.panel_list.append(pnl)
            if len(self.panel_list) == 1: self.adjustSize(); self.move_to_center()
            self.cond_pnl.notify_all()

    def add_new_panel_async(self):
        with self.cond_pnl:
            self.signal_addnew.emit()
            self.cond_pnl.wait()
        return self.panel_list[-1]

    def move_to_center(self):
        if screen := QApplication.primaryScreen():
            self.move(screen.availableGeometry().center() - self.rect().center())

def get_iostream(commandline):
    if platform.system() == "Windows":
        proc = Popen(commandline, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, encoding='utf-8', creationflags=0x08000000)
        return proc, proc.stdout, proc.stderr
    else:
        import pty
        m_stdout, s_stdout = pty.openpty()
        m_stderr, s_stderr = pty.openpty()
        proc = Popen(commandline, stdin=PIPE, stdout=s_stdout, stderr=s_stderr, close_fds=True)
        return proc, os.fdopen(m_stdout), os.fdopen(m_stderr)

def proc_smireader(fields, main_window, smi_stdout, proc):
    global is_running
    is_running = True
    
    # Paramiko's stdout is a ChannelFile which can be iterated directly
    # and needs decoding.
    def get_lines(stream):
        if hasattr(stream, 'channel'): # Likely a paramiko stream
            try:
                for line in stream:
                    yield line
            except Exception as e:
                print(f"Paramiko stream reading error: {e}")
                return
        else: # Subprocess stream
            while is_running:
                line = stream.readline()
                if not line:
                    break
                yield line

    for smi_line in get_lines(smi_stdout):
        if not is_running: break
        try:
            if not smi_line.strip(): continue
            smi_data = {k.strip(): v.strip() for k, v in zip(fields, smi_line.strip().split(","))}
            idx = int(smi_data["index"])
            if idx >= len(main_window.panel_list):
                main_window.add_new_panel_async().signal_update.emit(smi_data)
            else:
                main_window.panel_list[idx].signal_update.emit(smi_data)
        except Exception as e:
            print(f"Stopping data reader due to an error: {e}");
            is_running = False
            break
            
    print("SMI reader thread finished.")
    if proc:
        proc.kill()

def parse_args():
    par = argparse.ArgumentParser(description="A cross-platform GPU status monitor.")
    par.add_argument("-H", "--host", help="Remote host to connect to via SSH")
    par.add_argument("-p", "--port", type=int, default=22, help="SSH port")
    par.add_argument("-u", "--user", help="SSH username")
    par.add_argument("-P", "--password", help="SSH password")
    par.add_argument("--ssh-args", help="Extra ssh args (string) inserted before the host, e.g. '-i C:/path/id_rsa -o StrictHostKeyChecking=no'", default="")
    par.add_argument("--dark", action="store_true", help="Enable dark mode")
    return par.parse_args()

def get_iostream_paramiko(hostname, port, username, password, command):
    if not paramiko:
        raise NotImplementedError("Paramiko library is not installed.")
    
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    print(f"Connecting to {username or 'default user'}@{hostname}:{port} using password...")
    client.connect(hostname, port=port, username=username, password=password, timeout=10)
    
    # Execute the command
    stdin, stdout, stderr = client.exec_command(" ".join(command), get_pty=True)
    
    # We need to keep the client object alive to keep the streams open
    # Return a dummy proc object that holds a reference to the client
    class DummyProc:
        def __init__(self, client):
            self.client = client
        def kill(self):
            self.client.close()

    return DummyProc(client), stdout, stderr

def main():
    global is_running
    fields = ["index", "count", "pci.bus_id", "name", "uuid", "memory.used", "memory.total", "temperature.gpu", "power.draw", "enforced.power.limit", "clocks.current.graphics", "fan.speed", "utilization.gpu"]
    args = parse_args()
    # If host is provided but no password given, prompt interactively when possible
    if args.host and not args.password:
        # only prompt if running in an interactive terminal
        try:
            if sys.stdin.isatty():
                prompt_user = None
                # If user included username in -H like user@host, do not override
                if '@' in args.host and not args.user:
                    prompt_user = args.host.split('@', 1)[0]
                if args.user:
                    prompt_user = args.user
                user_prompt = f"Password for {prompt_user or 'remote user'}: "
                pwd = getpass.getpass(user_prompt)
                if pwd:
                    args.password = pwd
        except Exception:
            # non-interactive environment or other issue; fall through
            pass
    cmd_gpu_stat = ["nvidia-smi", "--query-gpu=" + ",".join(fields), "--format=csv,noheader,nounits", "-lms", "300"]
    hostname = socket.gethostname()
    ssh_hostname = None
    ssh_username = args.user

    if args.host:
        if '@' in args.host and not ssh_username:
            try:
                user, host = args.host.rsplit('@', 1)
                ssh_username = user
                ssh_hostname = host
            except ValueError:
                ssh_hostname = args.host # Not a valid user@host format
        else:
            ssh_hostname = args.host
        
        hostname = ssh_hostname # for window title

    try:
        if ssh_hostname and args.password and paramiko:
            # Use paramiko for password-based auth
            proc_gpu_stat, gpu_stat, gpu_err = get_iostream_paramiko(
                hostname=ssh_hostname,
                port=args.port,
                username=ssh_username,
                password=args.password,
                command=cmd_gpu_stat
            )
        elif ssh_hostname:
            # Use subprocess for key-based auth
            ssh_connect_str = f"{ssh_username}@{ssh_hostname}" if ssh_username else ssh_hostname
            ssh_cmd = ["ssh", "-p", str(args.port)]
            default_ssh_opts = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
            ssh_cmd += default_ssh_opts
            if args.ssh_args:
                try:
                    extra_args = shlex.split(args.ssh_args)
                    ssh_cmd += extra_args
                except Exception:
                    print("Warning: failed to parse --ssh-args; passing raw string")
                    ssh_cmd.append(args.ssh_args)
            ssh_cmd.append(ssh_connect_str)
            cmd_gpu_stat = ssh_cmd + cmd_gpu_stat
            
            try:
                print("Executing:", " ".join(shlex.quote(x) for x in cmd_gpu_stat))
            except Exception:
                print("Executing (raw):", cmd_gpu_stat)
            proc_gpu_stat, gpu_stat, gpu_err = get_iostream(cmd_gpu_stat)
        else:
            # Local execution
            try:
                try:
                    print("Executing local:", " ".join(shlex.quote(x) for x in cmd_gpu_stat))
                except Exception:
                    print("Executing local (raw):", cmd_gpu_stat)
                proc_gpu_stat, gpu_stat, gpu_err = get_iostream(cmd_gpu_stat)
            except Exception as e:
                print("Failed to start local nvidia-smi:", e)
                traceback.print_exc()
                return

    except (FileNotFoundError, NotImplementedError) as e:
        print(f"Error: {e}. Make sure 'nvidia-smi' or 'ssh' is in your system's PATH, or paramiko is installed."); return
    except Exception as e:
        print(f"Failed to start monitoring process: {e}")
        traceback.print_exc()
        return

    app = QApplication(sys.argv)
    mw = MainWindow(window_name="GPU Status on " + hostname, dark_mode=args.dark)
    th = threading.Thread(target=proc_smireader, name="SMI-StdoutReader", args=(fields, mw, gpu_stat, proc_gpu_stat), daemon=True)
    th.start()
    
    def _stderr_printer(err_stream, proc):
        try:
            # For paramiko, the stream is a ChannelStderrFile which can be iterated
            if hasattr(err_stream, '__iter__'):
                 for line in err_stream:
                    print("SSH/SMI stderr:", line.strip())
            else: # For subprocess, it's a file-like object
                while True:
                    line = err_stream.readline()
                    if not line:
                        break
                    print("SSH/SMI stderr:", line.strip())
        except Exception as e:
            print("stderr reader stopped due to:", e)

    try:
        if gpu_err is not None:
            thr_err = threading.Thread(target=_stderr_printer, args=(gpu_err, proc_gpu_stat), daemon=True)
            thr_err.start()
    except Exception:
        pass
        
    mw.show()
    app.exec()
    is_running = False
    print("Main window closed. Waiting for reader thread to exit...")
    th.join(timeout=2.0)
    print("Application finished.")

if __name__ == "__main__":
    main()
