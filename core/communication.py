"""
通信管理器
负责与飞控的串口/TCP连接、数据收发、MSP协议封装
"""

import socket
import serial
import serial.tools.list_ports
from threading import Thread, Lock
from queue import Queue
from typing import Optional, Callable
import time


class SerialCommunication:
    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.is_connected = False
        self.receive_thread: Optional[Thread] = None
        self.data_queue = Queue()
        self.lock = Lock()
        self._running = False
        self._last_port = ""
        self._last_baudrate = 115200
        self._user_disconnect = False

        # 回调函数
        self.on_data_received: Optional[Callable] = None
        self.on_connection_changed: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    def get_available_ports(self) -> list:
        """获取所有可用的串口列表"""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                'device': port.device,
                'description': port.description,
                'hwid': port.hwid
            })
        return ports

    def connect(self, port: str, baudrate: int = 115200, timeout: float = 0.1) -> bool:
        """连接到指定串口"""
        try:
            if self.is_connected:
                self.disconnect()

            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )

            self._last_port = port
            self._last_baudrate = baudrate
            self._user_disconnect = False
            self.is_connected = True
            self._running = True

            # 启动接收线程
            self.receive_thread = Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()

            if self.on_connection_changed:
                self.on_connection_changed(True)

            return True

        except Exception as e:
            if self.on_error:
                self.on_error(f"连接失败: {str(e)}")
            return False

    def disconnect(self):
        """断开串口连接"""
        self._user_disconnect = True
        self._running = False
        self.is_connected = False

        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

        if self.on_connection_changed:
            self.on_connection_changed(False)

    def send_data(self, data: bytes) -> bool:
        """发送数据到飞控"""
        if not self.is_connected or not self.serial_port:
            return False

        try:
            with self.lock:
                self.serial_port.write(data)
                self.serial_port.flush()
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(f"发送失败: {str(e)}")
            return False

    def _receive_loop(self):
        """接收数据循环（后台线程）"""
        while self._running and self.is_connected:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.read(self.serial_port.in_waiting)
                    if data:
                        self.data_queue.put(data)
                        if self.on_data_received:
                            self.on_data_received(data)
                time.sleep(0.001)
            except Exception as e:
                if self._running and not self._user_disconnect and self.on_error:
                    self.on_error(f"接收错误: {str(e)}")
                break

        # ★ 非用户主动断开 → 通知主线程
        if not self._user_disconnect and self.on_connection_changed:
            self.is_connected = False
            self.on_connection_changed(False)

    def read_data(self) -> Optional[bytes]:
        """从队列读取数据"""
        if not self.data_queue.empty():
            return self.data_queue.get_nowait()
        return None

    @property
    def connection_info(self) -> str:
        """获取连接信息字符串"""
        if not self.is_connected:
            return "Not Connected"
        return f"Serial:{self.serial_port.port}@{self.serial_port.baudrate}"


class TCPCommunication:
    """TCP客户端通信（用于WiFi连接飞控热点）"""

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.is_connected = False
        self.receive_thread: Optional[Thread] = None
        self.data_queue = Queue()
        self.lock = Lock()
        self._running = False
        self._host = ""
        self._port = 0
        self._user_disconnect = False

        # 回调函数
        self.on_data_received: Optional[Callable] = None
        self.on_connection_changed: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    def connect(self, host: str, port: int = 8888, timeout: float = 5.0) -> bool:
        """连接到飞控WiFi热点的TCP服务器"""
        try:
            if self.is_connected:
                self.disconnect()

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect((host, port))
            self.socket.settimeout(0.1)

            self._host = host
            self._port = port
            self._user_disconnect = False
            self.is_connected = True
            self._running = True

            # 启动接收线程
            self.receive_thread = Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()

            if self.on_connection_changed:
                self.on_connection_changed(True)

            return True

        except Exception as e:
            if self.on_error:
                self.on_error(f"TCP连接失败: {str(e)}")
            return False

    def disconnect(self):
        """断开TCP连接"""
        self._user_disconnect = True
        self._running = False
        self.is_connected = False

        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)

        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        if self.on_connection_changed:
            self.on_connection_changed(False)

    def send_data(self, data: bytes) -> bool:
        """通过TCP发送数据到飞控"""
        if not self.is_connected or not self.socket:
            return False

        try:
            with self.lock:
                self.socket.sendall(data)
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(f"TCP发送失败: {str(e)}")
            self.disconnect()
            return False

    def _receive_loop(self):
        """TCP接收数据循环（后台线程）"""
        buffer = b""
        while self._running and self.is_connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    # 连接被远端关闭
                    if self.on_error:
                        self.on_error("TCP连接断开（远端关闭）")
                    break
                buffer += data
                self.data_queue.put(data)
                if self.on_data_received:
                    self.on_data_received(data)
            except socket.timeout:
                continue
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                if self._running and self.on_error:
                    self.on_error(f"TCP接收错误: {str(e)}")
                break
            except Exception as e:
                if self._running and self.on_error:
                    self.on_error(f"TCP异常: {str(e)}")
                break

        self.is_connected = False
        if self.on_connection_changed:
            self.on_connection_changed(False)

    def read_data(self) -> Optional[bytes]:
        """从队列读取数据"""
        if not self.data_queue.empty():
            return self.data_queue.get_nowait()
        return None

    @property
    def connection_info(self) -> str:
        """获取连接信息字符串"""
        if not self.is_connected:
            return "Not Connected"
        return f"TCP:{self._host}:{self._port}"


# 全局单例实例
comm_serial = SerialCommunication()
comm_tcp = TCPCommunication()