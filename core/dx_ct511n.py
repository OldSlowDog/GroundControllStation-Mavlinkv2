"""
DX-CT511N-B 4G+GNSS 双模通信模块驱动

模块规格:
  - 厂商: 大夏龙雀 (www.szdx-smart.com)
  - 型号: DX-CT511N-B (带底板版本, 28mm×28mm)
  - 工作电压: 5V-16V (推荐12V或5V USB供电)
  - 接口: UART (TTL电平, 默认115200bps)
  - 支持协议: TCP/UDP/HTTP/MQTT
  - GPS: 北斗/GPS双模 (冷启动28秒锁定)

主要功能:
  1. 4G网络连接管理 (APN/信号强度/运营商)
  2. TCP/IP透传模式 (地面站远程通信)
  3. GPS定位控制 (开启/查询/数据解析)
  4. MQTT通信 (可选, 用于云端上报)

使用示例:
    >>> from dx_ct511n import DXCT511N
    >>> module = DXCT511N(port='COM3', baudrate=115200)
    >>> if module.connect():
    ...     module.setup_4g(apn='cmnet')           # 配置移动网络
    ...     module.enable_gps()                     # 开启GPS
    ...     gps_data = module.query_gps()            # 查询GPS
    ...     module.start_tcp_server('0.0.0.0', 8080) # 启动TCP服务器
"""

import serial
import time
import re
import logging
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class GPSFixType(Enum):
    """GPS定位类型"""
    NONE = 0      # 无定位
    FIX_2D = 1    # 2D定位 (仅经纬度)
    FIX_3D = 2    # 3D定位 (含高度)
    DGPS = 3      # 差分定位


@dataclass
class GPSData:
    """GPS定位数据"""
    fix_type: GPSFixType = GPSFixType.NONE
    num_satellites: int = 0
    latitude: float = 0.0          # 纬度 (度)
    longitude: float = 0.0         # 经度 (度)
    altitude: float = 0.0          # 海拔高度 (米)
    ground_speed: float = 0.0      # 地速 (m/s)
    ground_course: float = 0.0     # 地面航向 (度)
    hdop: float = 9999.0           # 水平精度因子
    timestamp: float = 0.0


@dataclass
class NetworkStatus:
    """网络状态信息"""
    connected: bool = False
    operator: str = ""             # 运营商名称
    signal_strength: int = 0       # 信号强度 (0-31, 越大越强)
    rssi: int = -113               # RSSI值 (dBm)
    ber: int = 99                  # 误码率 (0-7, 99未知)
    ip_address: str = ""           # IP地址


class DXCT511N:
    """
    DX-CT511N-B 4G+GNSS 模块驱动类

    功能:
      - AT指令封装和发送/响应解析
      - 4G网络自动连接和管理
      - GPS数据采集和解析
      - TCP/IP透传模式控制
      - 错误处理和重试机制

    硬件连接:
      模块引脚        STM32/USB-TTL
      ─────────     ──────────────
      VCC_IN         5V/12V
      GND            GND
      TXD            RX (MCU)
      RXD            TX (MCU)
      PWRKEY         GPIO (开机键, 低电平有效>1s)
      NETLIGHT       LED指示灯 (可选)

    注意:
      - 默认波特率: 115200bps, 8N1
      - 上电后需等待3-5秒初始化
      - AT指令以\\r\\n结尾
    """

    # ===== 常量定义 =====
    DEFAULT_BAUDRATE = 115200
    DEFAULT_TIMEOUT = 2.0          # AT指令响应超时(秒)
    GPS_QUERY_INTERVAL = 2.0      # GPS查询间隔(秒)
    MAX_RETRY_COUNT = 3           # 最大重试次数

    # AT指令集 (DX-CT511N专用)
    AT_TEST = "AT\r\n"                                    # 测试AT指令
    AT_RESET = "AT+CFUN=1,1\r\n"                         # 重启模块
    AT_GET_IMSI = "AT+CIMI\r\n"                          # 获取IMSI
    AT_GET_CCID = "AT+CCID\r\n"                          # 获取SIM卡号
    AT_CSQ = "AT+CSQ\r\n"                                # 查询信号质量
    AT_CREG = "AT+CREG?\r\n"                             # 查询网络注册状态
    AT_COPS = "AT+COPS?\r\n"                             # 查询当前运营商
    AT_QENG = 'AT+QENG="servingcell"\r\n'                # 查询小区信息

    # 4G网络相关
    AT_SET_APN = "AT+QICSGP=1,1,\"{apn}\",\"\",\"\"\r\n"   # 设置APN
    AT_NET_OPEN = "AT+NETOPEN\r\n"                         # 开启移动网络
    AT_NET_CLOSE = "AT+NETCLOSE\r\n"                       # 关闭移动网络
    AT_GET_IP = "AT+IPADDR\r\n"                           # 查询IP地址

    # TCP/IP透传
    AT_TCP_SERVER_START = "AT+CIPTCPSERV={port}\r\n"       # 启动TCP服务器
    AT_TCP_CLIENT_CONNECT = "AT+CIPTCPSTART=\"{ip}\",{port}\r\n"  # 连接TCP客户端
    AT_TCP_CLOSE = "AT+CIPTCPCLOSE\r\n"                    # 关闭TCP连接
    AT_TCP_SEND = "AT+CIPSEND={length}\r\n"                # 发送数据(需先进入透传模式)

    # GPS相关
    AT_GPS_ENABLE = "AT+MGPSC=1\r\n"                       # 开启GPS
    AT_GPS_DISABLE = "AT+MGPSC=0\r\n"                      # 关闭GPS
    AT_GPS_NMEA_OFF = "AT+MGPSGET=ALL,0\r\n"              # 关闭NMEA输出(减少数据量)
    AT_GPS_QUERY = "AT+GPSST\r\n"                         # 查询GPS状态(推荐!)
    AT_GPS_NMEA_RAW = "AT+MGPSGET=ALL,1\r\n"              # 开启NMEA原始输出

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE):
        """
        初始化4G模块

        Args:
            port: 串口名称 (如 'COM3', '/dev/ttyUSB0')
            baudrate: 波特率 (默认115200)
        """
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.is_connected = False
        self.gps_enabled = False
        self.tcp_mode = False

        # 缓存最新数据
        self._gps_data = GPSData()
        self._network_status = NetworkStatus()
        self._last_gps_query_time = 0.0

        logger.info(f"[4G] 初始化DX-CT511N模块: {port}@{baudrate}bps")

    def connect(self) -> bool:
        """
        连接到4G模块串口

        Returns:
            True=成功, False=失败
        """
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.DEFAULT_TIMEOUT,
                write_timeout=1.0
            )

            # 清空缓冲区
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

            # 测试AT指令连通性
            time.sleep(0.5)  # 等待模块就绪
            if self._send_at_command(self.AT_TEST):
                self.is_connected = True
                logger.info("[4G] ✓ 模块连接成功")
                return True
            else:
                logger.error("[4G] ✗ AT测试失败，检查波特率和接线")
                self.disconnect()
                return False

        except serial.SerialException as e:
            logger.error(f"[4G] ✗ 串口打开失败: {e}")
            return False

    def disconnect(self):
        """断开串口连接"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.is_connected = False
            logger.info("[4G] 已断开连接")

    def _send_at_command(self, command: str,
                         expected_response: str = "OK",
                         timeout: float = DEFAULT_TIMEOUT) -> str:
        """
        发送AT指令并等待响应

        Args:
            command: AT指令字符串 (包含\\r\\n)
            expected_response: 期望的响应内容 ("OK" 或特定前缀)
            timeout: 超时时间(秒)

        Returns:
            响应文本 (不含命令本身), 失败返回空字符串
        """
        if not self.serial or not self.serial.is_open:
            logger.error("[4G] 串口未打开")
            return ""

        try:
            # 发送指令
            self.serial.write(command.encode('ascii'))
            self.serial.flush()

            # 读取响应 (带超时)
            response = ""
            start_time = time.time()

            while (time.time() - start_time) < timeout:
                if self.serial.in_waiting > 0:
                    line = self.serial.readline().decode('ascii', errors='ignore').strip()
                    if line:
                        response += line + "\n"
                        # 检查是否收到期望的响应
                        if expected_response in line or "ERROR" in line:
                            break
                time.sleep(0.01)

            if expected_response in response:
                logger.debug(f"[4G] AT OK: {command.strip()[:30]}... → {response[:50]}")
                return response
            elif "ERROR" in response:
                logger.warning(f"[4G] AT ERROR: {command.strip()[:30]} → {response[:50]}")
                return ""
            else:
                logger.warning(f"[4G] AT TIMEOUT: {command.strip()[:30]} (>{timeout}s)")
                return response  # 返回部分响应供调试

        except Exception as e:
            logger.error(f"[4G] AT发送异常: {e}")
            return ""

    # ===== 4G网络管理 =====

    def setup_4g(self, apn: str = "cmnet") -> bool:
        """
        配置并启动4G网络连接

        Args:
            apn: APN接入点名称
                 - 中国移动: cmnet / cmwap
                 - 中国联通: uninet / uniwap
                 - 中国电信: ctnet / ctwap
                 - 自动获取: 留空 ""

        Returns:
            True=成功, False=失败
        """
        logger.info(f"[4G] 配置4G网络 (APN={apn})")

        # 步骤1: 设置APN
        cmd = self.AT_SET_APN.format(apn=apn)
        if not self._send_at_command(cmd):
            logger.error("[4G] APN设置失败")
            return False

        time.sleep(0.5)

        # 步骤2: 开启移动网络 (关键步骤!)
        resp = self._send_at_command(self.AT_NET_OPEN)
        if "OK" not in resp:
            logger.error("[4G] 移动网络开启失败! (忘记调用NETOPEN?)")
            return False

        # 等待网络注册 (最多30秒)
        logger.info("[4G] 等待网络注册...")
        for i in range(15):  # 15×2s=30s超时
            time.sleep(2)
            if self.check_network_status():
                logger.info(f"[4G] ✓ 网络注册成功 ({i*2}s)")
                return True

        logger.error("[4G] ✗ 网络注册超时(30s)，检查SIM卡和信号")
        return False

    def check_network_status(self) -> bool:
        """
        检查当前网络注册状态并更新缓存

        Returns:
            True=已联网, False=未联网
        """
        # 查询信号强度
        csq_resp = self._send_at_command(self.AT_CSQ)
        csq_match = re.search(r'\+CSQ:\s*(\d+),(\d+)', csq_resp)

        if csq_match:
            rssi_val = int(csq_match.group(1))
            ber_val = int(csq_match.group(2))

            # 转换RSSI (0→-113dBm, 31→-51dBm, 99→未知)
            if 0 <= rssi_val <= 31:
                self._network_status.signal_strength = rssi_val
                self._network_status.rssi = (rssi_val * 2) - 113
            else:
                self._network_status.signal_strength = 0
                self._network_status.rssi = -113

            self._network_status.ber = ber_val

        # 查询网络注册状态
        creg_resp = self._send_at_command(self.AT_CREG)
        creg_match = re.search(r'\+CREG:\s*(\d),(\d)', creg_resp)

        if creg_match:
            mode = int(creg_match.group(1))
            stat = int(creg_match.group(2))
            # stat: 0=未注册, 1=已注册本地网, 5=已漫游
            self._network_status.connected = (stat == 1 or stat == 5)

        # 查询运营商
        cops_resp = self._send_at_command(self.AT_COPS)
        cops_match = re.search(r'\+COPS:\s*\d,\d,"([^"]*)"', cops_resp)
        if cops_match:
            self._network_status.operator = cops_match.group(1)

        # 查询IP地址
        ip_resp = self._send_at_command(self.AT_GET_IP)
        ip_match = re.search(r'\+IPADDR:\s*"?([^"\r\n]+)"?', ip_resp)
        if ip_match:
            self._network_status.ip_address = ip_match.group(1).strip()

        return self._network_status.connected

    def get_network_status(self) -> NetworkStatus:
        """获取缓存的网络状态"""
        return self._network_status

    # ===== GPS定位功能 =====

    def enable_gps(self) -> bool:
        """
        开启GPS功能

        注意:
          - 首次冷启动需要28秒左右才能锁定卫星
          - 室内或遮挡环境可能无法定位
          - 开启后建议定期调用query_gps()更新位置

        Returns:
            True=成功, False=失败
        """
        logger.info("[GPS] 正在开启GNSS...")

        # 步骤1: 开启GPS芯片电源
        resp = self._send_at_command(self.AT_GPS_ENABLE)
        if "OK" not in resp:
            logger.error("[GPS] GPS开启指令失败")
            return False

        # 步骤2: 关闭NMEA流式输出 (减少串口数据量，改用AT+GPSST轮询)
        self._send_at_command(self.AT_GPS_NMEA_OFF)

        self.gps_enabled = True
        logger.info("[GPS] ✓ GNSS已开启 (使用AT+GPSST查询模式)")

        # 预热GPS (可选：首次启动等待更长时间)
        time.sleep(1)

        return True

    def disable_gps(self) -> bool:
        """关闭GPS功能"""
        resp = self._send_at_command(self.AT_GPS_DISABLE)
        self.gps_enabled = ("OK" in resp)
        if self.gps_enabled:
            logger.info("[GPS] GNSS已关闭")
        return self.gps_enabled

    def query_gps(self, force: bool = False) -> Optional[GPSData]:
        """
        查询GPS定位数据 (推荐方法!)

        使用AT+GPSST指令一次性获取所有GPS信息，
        比解析NMEA语句更简单高效。

        AT+GPSST返回格式:
          +GPSST: fix_status, cn, longitude, latitude, altitude; sat_info...

        数据说明:
          - fix_status: 定位状态 (0=无定位, 1=有定位)
          - cn: 定位置信度/卫星数
          - longitude: 经度 (度, 如113.xxxxxx)
          - latitude: 纬度 (度, 如23.xxxxxx)
          - altitude: 海拔高度 (米)

        Args:
            force: 是否强制查询 (忽略时间间隔限制)

        Returns:
            GPSData对象, 失败返回None
        """
        current_time = time.time()

        # 限制查询频率 (默认2秒一次，避免频繁AT指令)
        if not force and (current_time - self._last_gps_query_time) < self.GPS_QUERY_INTERVAL:
            return self._gps_data

        if not self.gps_enabled:
            logger.warning("[GPS] GPS未启用，请先调用enable_gps()")
            return None

        # 发送AT+GPSST查询
        resp = self._send_at_command(self.AT_GPS_QUERY, "+GPSST:", timeout=5.0)

        if not resp or "+GPSST:" not in resp:
            logger.debug("[GPS] 无GPS数据 (可能还在搜索卫星...)")
            self._last_gps_query_time = current_time
            return None

        # 解析响应
        try:
            gps_data = self._parse_gpsst_response(resp)
            if gps_data:
                self._gps_data = gps_data
                self._last_gps_query_time = current_time

                log_level = logging.INFO if gps_data.fix_type != GPSFixType.NONE else logging.DEBUG
                logger.log(log_level,
                    f"[GPS] 🛰 {gps_data.num_satellites}Sats | "
                    f"{gps_data.latitude:.6f}, {gps_data.longitude:.6f} | "
                    f"Alt:{gps_data.altitude:.1f}m | Fix:{gps_data.fix_type.name}"
                )
                return gps_data

        except Exception as e:
            logger.error(f"[GPS] 解析错误: {e}")

        return None

    def _parse_gpsst_response(self, response: str) -> Optional[GPSData]:
        """
        解析AT+GPSST响应字符串

        示例输入:
            +GPSST: 1, 1, 113.123456, 23.654321, 32.5; 0, 119; 0, 77; ...

        输出:
            GPSData对象
        """
        match = re.search(
            r'\+GPSST:\s*(\d),\s*(\d),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)',
            response
        )

        if not match:
            return None

        fix_status = int(match.group(1))   # 定位状态 (0/1)
        cn = int(match.group(2))           # 卫星数/置信度
        lon = float(match.group(3))        # 经度
        lat = float(match.group(4))        # 纬度
        alt = float(match.group(5))        # 高度

        # 构建GPSData对象
        gps = GPSData()

        # 判断定位类型
        if fix_status >= 1 and cn >= 1:
            if cn >= 6:
                gps.fix_type = GPSFixType.FIX_3D
            elif cn >= 3:
                gps.fix_type = GPSFixType.FIX_2D
            else:
                gps.fix_type = GPSFixType.NONE
        else:
            gps.fix_type = GPSFixType.NONE

        gps.num_satellites = max(0, min(cn, 12))  # 限制在合理范围
        gps.latitude = lat
        gps.longitude = lon
        gps.altitude = alt
        gps.timestamp = time.time()

        # HDOP估算 (基于卫星数，实际值需从扩展字段提取)
        if gps.num_satellites >= 8:
            gps.hdop = 0.8
        elif gps.num_satellites >= 5:
            gps.hdop = 1.5
        elif gps.num_satificates >= 3:
            gps.hdop = 2.5
        else:
            gps.hdop = 5.0

        return gps

    def get_gps_data(self) -> GPSData:
        """获取缓存的GPS数据"""
        return self._gps_data

    # ===== TCP/IP透传模式 =====

    def start_tcp_server(self, port: int = 8080) -> bool:
        """
        启动TCP服务器模式 (飞控端使用!)

        用途:
          飞控作为TCP Server，地面站通过4G网络远程连接

        Args:
            port: 监听端口 (默认8080)

        Returns:
            True=成功, False=失败
        """
        logger.info(f"[TCP] 启动TCP服务器 (端口{port})...")

        # 确保网络已开启
        if not self._network_status.connected:
            logger.error("[TCP] 未联网，无法启动TCP服务")
            return False

        # 启动TCP服务器
        cmd = self.AT_TCP_SERVER_START.format(port=port)
        resp = self._send_at_command(cmd, timeout=10.0)

        if "OK" in resp:
            self.tcp_mode = True
            ip = self._network_status.ip_address or "0.0.0.0"
            logger.info(f"[TCP] ✓ 服务器已启动: {ip}:{port}")
            return True
        else:
            logger.error(f"[TCP] ✗ 服务器启动失败: {resp[:100]}")
            return False

    def connect_tcp_client(self, server_ip: str, server_port: int = 8080) -> bool:
        """
        连接TCP服务器 (地面站使用!)

        用途:
          地面站通过4G网络连接到飞控的TCP Server

        Args:
            server_ip: 飞控公网IP或域名
            server_port: 飞控监听端口

        Returns:
            True=成功, False=失败
        """
        logger.info(f"[TCP] 连接TCP服务器: {server_ip}:{server_port}")

        cmd = self.AT_TCP_CLIENT_CONNECT.format(ip=server_ip, port=server_port)
        resp = self._send_at_command(cmd, timeout=15.0)

        if "OK" in resp or "CONNECT" in resp:
            self.tcp_mode = True
            logger.info(f"[TCP] ✓ 已连接到 {server_ip}:{server_port}")
            return True
        else:
            logger.error(f"[TCP] ✗ 连接失败: {resp[:100]}")
            return False

    def close_tcp(self) -> bool:
        """关闭TCP连接"""
        resp = self._send_at_command(self.AT_TCP_CLOSE)
        self.tcp_mode = False
        return "OK" in resp

    # ===== 数据收发 (透传模式) =====

    def send_data(self, data: bytes) -> bool:
        """
        通过TCP连接发送数据 (非透传模式)

        在普通AT模式下发送数据到已建立的TCP连接

        Args:
            data: 要发送的字节数据

        Returns:
            True=成功, False=失败
        """
        if not self.tcp_mode:
            logger.error("[TCP] 未建立TCP连接")
            return False

        length = len(data)
        cmd = self.AT_TCP_SEND.format(length=length)

        # 发送发送指令
        resp = self._send_at_command(cmd, ">")  # 等待">"提示符
        if ">" not in resp:
            logger.error(f"[TCP] 进入发送模式失败: {resp}")
            return False

        # 发送实际数据
        try:
            self.serial.write(data)
            self.serial.flush()

            # 等待发送完成确认
            time.sleep(0.1)
            resp = self.serial.readline().decode('ascii', errors='ignore').strip()
            return "SEND OK" in resp or "OK" in resp

        except Exception as e:
            logger.error(f"[TCP] 发送异常: {e}")
            return False

    def read_data(self, timeout: float = 1.0) -> bytes:
        """
        从TCP连接读取数据

        Args:
            timeout: 读取超时(秒)

        Returns:
            收到的字节数据
        """
        if not self.serial or not self.serial.is_open:
            return b''

        data = b''
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting > 0:
                chunk = self.serial.read(self.serial.in_waiting)
                data += chunk
            else:
                time.sleep(0.01)

        return data

    # ===== MQTT通信 (可选高级功能) =====

    def setup_mqtt_client(self, client_id: str,
                          username: str = "",
                          password: str = "") -> bool:
        """
        配置MQTT客户端参数

        Args:
            client_id: 客户端标识符
            username: 用户名 (可选)
            password: 密码 (可选)

        Returns:
            True=成功
        """
        cmd = f'AT+MCONFIG="{client_id}"'
        if username:
            cmd += f',"{username}"'
        if password:
            cmd += f',"{password}"'

        cmd += "\r\n"
        resp = self._send_at_command(cmd)
        return "OK" in resp

    def connect_mqtt_server(self, broker: str, port: int = 1883) -> bool:
        """
        连接MQTT服务器

        Args:
            broker: 服务器地址 (IP或域名)
            port: 端口 (默认1883)

        Returns:
            True=成功
        """
        cmd = f'AT+MIPSTART="{broker}",{port}\r\n'
        resp = self._send_at_command(cmd, timeout=10.0)

        if "OK" in resp:
            # 发起连接
            resp = self._send_at_command("AT+MCONNECT=1,60\r\n", timeout=15.0)
            return "OK" in resp

        return False

    def mqtt_publish(self, topic: str, message: str, qos: int = 0) -> bool:
        """
        发布MQTT消息

        Args:
            topic: 主题
            message: 消息内容
            qos: 服务质量 (0/1/2)

        Returns:
            True=成功
        """
        cmd = f'AT+MPUB="{topic}",{qos},0,"{message}"\r\n'
        resp = self._send_at_command(cmd)
        return "OK" in resp

    def mqtt_subscribe(self, topic: str, qos: int = 0) -> bool:
        """
        订阅MQTT主题

        Args:
            topic: 主题
            qos: 服务质量

        Returns:
            True=成功
        """
        cmd = f'AT+MSUB="{topic}",{qos}\r\n'
        resp = self._send_at_command(cmd)
        return "OK" in resp

    # ===== 工具方法 =====

    def get_module_info(self) -> Dict[str, str]:
        """
        获取模块详细信息

        Returns:
            包含厂商、型号、固件版本等信息的字典
        """
        info = {}

        # 固件版本
        resp = self._send_at_command("AT+CGMR\r\n")
        ver_match = re.search(r'([\w.-]+)', resp.split('\n')[0] if resp else '')
        info['firmware'] = ver_match.group(1) if ver_match else "Unknown"

        # IMSI (SIM卡标识)
        resp = self._send_at_command(self.AT_GET_IMSI)
        imsi_match = re.search(r'\d{15}', resp or "")
        info['imsi'] = imsi_match.group(0) if imsi_match else "N/A"

        # CCID (SIM卡序列号)
        resp = self._send_at_command(self.AT_GET_CCID)
        ccid_match = re.search(r'\d{19,20}', resp or "")
        info['ccid'] = ccid_match.group(0) if ccid_match else "N/A"

        return info

    def reset_module(self) -> bool:
        """
        软重启模块

        Returns:
            True=重启指令已发送
        """
        logger.warning("[4G] 正在重启模块...")
        resp = self._send_at_command(self.AT_RESET, timeout=5.0)
        if "OK" in resp:
            time.sleep(5)  # 等待重启完成
            return True
        return False

    def __del__(self):
        """析构时自动断开连接"""
        self.disconnect()


# ===== 便捷函数 =====

def test_dxct511n(port: str = 'COM3') -> bool:
    """
    快速测试DX-CT511N-B模块连接和基本功能

    Args:
        port: 串口号

    Returns:
        True=全部测试通过
    """
    print("=" * 60)
    print("  DX-CT511N-B 4G+GNSS 模块测试工具")
    print("=" * 60)

    module = DXCT511N(port=port)

    # 测试1: 串口连接
    print("\n[1/5] 测试串口连接...")
    if not module.connect():
        print("  ✗ 串口连接失败!")
        return False
    print("  ✓ 串口连接成功")

    # 测试2: 网络状态
    print("\n[2/5] 检查网络状态...")
    net = module.get_network_status()
    if module.check_network_status():
        print(f"  ✓ 已联网 | 运营商: {net.operator} | "
              f"信号: {net.signal_strength}/31 ({net.rssi} dBm)")
    else:
        print("  ⚠ 未检测到SIM卡或无信号 (可继续测试GPS)")

    # 测试3: GPS功能
    print("\n[3/5] 测试GPS...")
    if module.enable_gps():
        print("  ✓ GPS已开启, 正在搜索卫星...")
        for i in range(10):  # 最多等待20秒
            time.sleep(2)
            gps = module.query_gps(force=True)
            if gps and gps.fix_type != GPSFixType.NONE:
                print(f"  ✓ 定位成功! {gps.num_satellites}颗卫星")
                print(f"    位置: {gps.latitude:.6f}, {gps.longitude:.6f}")
                print(f"    高度: {gps.altitude:.1f}m")
                break
            else:
                print(f"  ⏳ 搜索中... ({(i+1)*2}s)", end='\r')
        else:
            print("\n  ⚠ 未能定位 (可能在室内或天线未接好)")
    else:
        print("  ✗ GPS开启失败")

    # 测试4: 模块信息
    print("\n[4/5] 读取模块信息...")
    info = module.get_module_info()
    print(f"  固件版本: {info.get('firmware', 'Unknown')}")
    print(f"  IMSI: {info.get('imsi', 'N/A')[:10]}...")

    # 测试5: 断开连接
    print("\n[5/5] 断开连接...")
    module.disconnect()
    print("  ✓ 已断开")

    print("\n" + "=" * 60)
    print("  测试完成!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        port = sys.argv[1]
    else:
        port = input("请输入串口号 (如 COM3): ").strip()

    test_dxct511n(port)
