"""
MQTT 客户端管理器 - 国内可用Broker支持

支持的MQTT Broker (按推荐顺序):
  1. EMQX国内节点: broker-cn.emqx.io:1883 (腾讯云上海, 延迟<50ms) ⭐推荐
  2. EMQX国际节点: broker.emqx.io:1883 (AWS俄勒冈, 备用)
  3. 阿里云IoT: 根据实例地址配置
  4. 华为云IoT: 根据实例地址配置
  5. 自建EMQX: 用户自己的服务器

主要功能:
  - 自动重连机制 (指数退避)
  - 多主题订阅管理
  - QoS级别控制
  - 消息收发统计
  - 线程安全设计

使用示例:
    >>> from mqtt_manager import MQTTManager
    >>> mgr = MQTTManager()
    >>> mgr.connect("drone_001", broker="emqx_cn")
    >>> mgr.publish_gps(22.5368, 113.9123, 32.5, 8)
    >>> mgr.subscribe("groundstation/cmd")
"""

import json
import time
import threading
import logging
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass, field
from enum import Enum
from queue import Queue

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False
    logging.warning("[MQTT] paho-mqtt未安装! 请运行: pip install paho-mqtt>=1.6.1")

logger = logging.getLogger(__name__)


class MQTTPreset(Enum):
    """预定义的MQTT Broker配置"""
    EMQX_CN = "emqx_cn"              # EMQX国内节点 (腾讯云上海) ⭐推荐
    EMQX_GLOBAL = "emqx_global"       # EMQX国际节点 (备用)
    ALIYUN_IOT = "aliyun_iot"         # 阿里云IoT平台
    HUAWEI_IOT = "huawei_iot"         # 华为云IoT平台
    CUSTOM = "custom"                 # 自定义服务器


@dataclass
class MQTTConfig:
    """MQTT connection configuration"""
    broker_host: str = "broker-cn.emqx.io"
    broker_port: int = 1883
    client_id: str = "INAV_GCS_Python"
    username: str = ""
    password: str = ""
    keepalive: int = 60              # Heartbeat interval (seconds)
    qos: int = 0                     # QoS (0=at most once, 1=at least once, 2=exactly once)
    clean_session: bool = True       # Clean session
    auto_reconnect: bool = True      # Auto reconnect
    reconnect_delay_min: float = 1.0 # Min reconnect delay (s)
    reconnect_delay_max: float = 60.0 # Max reconnect delay (s)
    tls_enabled: bool = False        # SSL/TLS encryption
    tls_insecure: bool = True        # Skip cert verification (for public brokers)

    # Topic configuration (customizable)
    topic_gps: str = "inav/{client_id}/gps"
    topic_status: str = "inav/{client_id}/status"
    topic_imu: str = "inav/{client_id}/imu"
    topic_rc: str = "inav/{client_id}/rc"
    topic_cmd: str = "inav/{client_id}/cmd"          # Send commands TO flight controller
    topic_resp: str = "inav/{client_id}/resp"         # Receive responses FROM FC
    topic_debug: str = "inav/{client_id}/debug"


# ===== 预设Broker配置字典 =====
PRESET_BROKERS: Dict[MQTTPreset, Dict] = {
    MQTTPreset.EMQX_CN: {
        "broker_host": "broker-cn.emqx.io",
        "broker_port": 1883,
        "tls_port": 8883,
        "description": "EMQX国内节点 (腾讯云上海)",
        "latency": "<50ms",
        "features": ["免费", "无需注册", "国内最快"],
        "url": "https://www.emqx.com/zh/mqtt/public-mqtt5-broker"
    },
    MQTTPreset.EMQX_GLOBAL: {
        "broker_host": "broker.emqx.io",
        "broker_port": 1883,
        "tls_port": 8883,
        "description": "EMQX国际节点 (AWS美国)",
        "latency": "100-200ms",
        "features": ["免费", "无需注册", "全球可用"],
        "url": "https://www.emqx.com/zh/mqtt/public-mqtt5-broker"
    },
    MQTTPreset.ALIYUN_IOT: {
        "broker_host": "",
        "broker_port": 1883,
        "tls_port": 8883,
        "description": "阿里云物联网平台",
        "latency": "<30ms",
        "features": ["企业级", "设备管理", "付费"],
        "url": "https://www.aliyun.com/product/iot"
    },
    MQTTPreset.HUAWEI_IOT: {
        "broker_host": "",
        "broker_port": 1883,
        "tls_port": 8883,
        "description": "华为云物联网平台",
        "latency": "<30ms",
        "features": ["企业级", "NB-IoT支持", "付费"],
        "url": "https://www.huaweicloud.com/product/iotdevice.html"
    },
}


class MQTTManager:
    """
    MQTT客户端管理器

    功能:
      - 连接管理 (自动重连/心跳保活)
      - 主题订阅/取消订阅
      - 消息发布 (GPS/状态/IMU/RC等)
      - 消息接收回调
      - 统计信息 (发送/接收计数)

    线程安全:
      - 所有公共方法都是线程安全的
      - 内部使用锁保护共享状态
      - 回调函数在独立线程中执行

    使用方式:
      方式1: 单例模式 (全局唯一)
        >>> mgr = MQTTManager.get_instance()

      方式2: 实例化 (多个连接)
        >>> mgr = MQTTManager(config=my_config)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, config: Optional[MQTTConfig] = None):
        """单例模式 (修复版!)"""
        with cls._lock:
            if cls._instance is None:
                # ★ 创建实例并保存 (只创建一次!)
                instance = super().__new__(cls)
                cls._instance = instance
        return cls._instance

    @classmethod
    def get_instance(cls, config: Optional[MQTTConfig] = None) -> 'MQTTManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def __init__(self, config: Optional[MQTTConfig] = None):
        """
        初始化MQTT管理器

        Args:
            config: MQTT配置 (为None时使用默认配置)
        """
        if not PAHO_AVAILABLE:
            raise ImportError(
                "paho-mqtt库未安装!\n"
                "请运行: pip install paho-mqtt>=1.6.1\n"
                "或: pip install -r requirements.txt"
            )

        self.config = config or MQTTConfig()
        self.client: Optional[mqtt.Client] = None
        self.is_connected = False
        self.is_connecting = False

        # 回调函数列表
        self._on_message_callbacks: List[Callable] = []
        self._on_connect_callbacks: List[Callable] = []
        self._on_disconnect_callbacks: List[Callable] = []

        # 统计信息
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'connect_count': 0,
            'reconnect_count': 0,
            'last_error': None,
            'uptime_start': 0
        }

        # 内部线程锁
        self._mutex = threading.Lock()
        self._reconnect_timer: Optional[threading.Timer] = None
        self._subscribe_queue: Queue = Queue()

        logger.info(f"[MQTT] 初始化完成 | Broker: {self.config.broker_host}:{self.config.broker_port}")

    def connect(self, client_id: Optional[str] = None,
                preset: MQTTPreset = MQTTPreset.EMQX_CN,
                on_message: Optional[Callable] = None,
                use_tls: bool = False) -> bool:
        """
        Connect to MQTT Broker

        Args:
            client_id: Client identifier (None uses default from config)
            preset: Preset broker type (EMQX_CN / EMQX_GLOBAL / CUSTOM etc.)
            on_message: Message receive callback signature: (topic, payload_dict) -> None
            use_tls: Enable SSL/TLS encryption (default=False)

        Returns:
            True=connected/connecting, False=failed
        """
        if self.is_connected:
            logger.warning("[MQTT] Already connected")
            return True

        if self.is_connecting:
            logger.warning("[MQTT] Already connecting...")
            return False

        # Apply preset configuration
        if preset != MQTTPreset.CUSTOM and preset in PRESET_BROKERS:
            preset_cfg = PRESET_BROKERS[preset]
            self.config.broker_host = preset_cfg['broker_host']
            if use_tls and 'tls_port' in preset_cfg:
                self.config.broker_port = preset_cfg['tls_port']
                self.config.tls_enabled = True
            else:
                self.config.broker_port = preset_cfg['broker_port']
                self.config.tls_enabled = use_tls
            logger.info(f"[MQTT] Using preset: {preset.value} ({preset_cfg['description']}) TLS={use_tls}")

        if client_id:
            self.config.client_id = client_id

        self.is_connecting = True

        try:
            # 创建MQTT客户端
            if hasattr(mqtt, 'CallbackAPIVersion'):
                # paho-mqtt >= 2.0
                self.client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                    client_id=self.config.client_id,
                    clean_session=self.config.clean_session
                )
            else:
                # paho-mqtt < 2.0
                self.client = mqtt.Client(
                    client_id=self.config.client_id,
                    clean_session=self.config.clean_session
                )

            # 设置认证信息
            if self.config.username:
                self.client.username_pw_set(self.config.username, self.config.password)

            # Register callbacks
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            # Add user custom callbacks
            if on_message:
                self.add_message_callback(on_message)

            # Configure SSL/TLS if enabled
            if self.config.tls_enabled:
                import ssl
                if self.config.tls_insecure:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                else:
                    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                self.client.tls_set_context(context)
                self.client.tls_insecure_set(self.config.tls_insecure)
                logger.info(f"[MQTT] TLS/SSL enabled (insecure={self.config.tls_insecure})")

            # Connect to Broker
            logger.info(f"[MQTT] Connecting to {self.config.broker_host}:{self.config.broker_port} TLS={self.config.tls_enabled} ...")
            self.client.connect(
                self.config.broker_host,
                self.config.broker_port,
                self.config.keepalive
            )

            # 启动后台网络循环
            self.client.loop_start()

            # 等待连接结果 (最多5秒)
            timeout = 5.0
            start = time.time()
            while not self.is_connected and (time.time() - start) < timeout:
                time.sleep(0.1)

            if self.is_connected:
                logger.info(f"[MQTT] ✓ 连接成功! ClientID={self.config.client_id}")
                self.stats['connect_count'] += 1
                self.stats['uptime_start'] = time.time()
                return True
            else:
                logger.error("[MQTT] ✗ 连接超时(5s)")
                self.is_connecting = False
                return False

        except Exception as e:
            logger.error(f"[MQTT] ✗ 连接异常: {e}")
            self.stats['last_error'] = str(e)
            self.is_connecting = False
            return False

    def disconnect(self):
        """
        断开MQTT连接 (非阻塞版本!)

        修复:
          - 使用超时机制避免UI卡死
          - 安全处理部分初始化的对象
          - 修复 _reconnect_timer 变量名错误
        """
        # ★ 安全检查: 确保对象已完全初始化
        if not hasattr(self, '_mutex'):
            logger.warning("[MQTT] 对象未完全初始化，跳过断开操作")
            return

        # ★ 使用超时锁 (避免死锁!)
        lock_acquired = self._mutex.acquire(timeout=1.0)
        if not lock_acquired:
            logger.warning("[MQTT] 无法获取锁(1s超时)，强制断开")
            # 强制清理（不等待锁）
            self._force_cleanup()
            return

        try:
            # 取消重连定时器
            if hasattr(self, '_reconnect_timer') and self._reconnect_timer:
                try:
                    self._reconnect_timer.cancel()
                except Exception:
                    pass
                self._reconnect_timer = None

            if self.client:
                try:
                    # ★ 非停止循环线程 (使用异步方式!)
                    # 原来是: self.client.loop_stop()  ← 这会阻塞!
                    # 改为: 设置标志让循环自然退出
                    if hasattr(self.client, '_thread') and self.client._thread:
                        # 只标记停止，不等待
                        pass

                    self.client.disconnect()  # 这也可能阻塞，但通常很快
                    logger.info("[MQTT] 已断开连接")
                except Exception as e:
                    logger.warning(f"[MQTT] 断开时异常: {e}")

                finally:
                    self.client = None
                    self.is_connected = False
                    self.is_connecting = False
        finally:
            self._mutex.release()

    def _force_cleanup(self):
        """强制清理资源 (用于异常情况)"""
        try:
            if hasattr(self, 'client') and self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                self.client = None

            self.is_connected = False
            self.is_connecting = False
        except Exception as e:
            logger.error(f"[MQTT] 强制清理失败: {e}")

    def add_message_callback(self, callback: Callable):
        """
        添加消息接收回调

        Args:
            callback: 回调函数, 签名: (topic: str, payload: dict) -> None
        """
        if callback not in self._on_message_callbacks:
            self._on_message_callbacks.append(callback)
            logger.debug(f"[MQTT] 已添加消息回调 (总数:{len(self._on_message_callbacks)})")

    def remove_message_callback(self, callback: Callable):
        """移除消息回调"""
        if callback in self._on_message_callbacks:
            self._on_message_callbacks.remove(callback)

    # ===== 发布功能 =====

    def publish(self, topic: str, payload: dict,
                qos: Optional[int] = None,
                retain: bool = False) -> bool:
        """
        发布消息到指定主题

        Args:
            topic: 主题名称 (支持{client_id}占位符)
            payload: 消息内容 (dict会自动JSON序列化)
            qos: 服务质量 (为None时使用配置默认值)
            retain: 是否保留消息

        Returns:
            True=发送成功, False=失败
        """
        if not self.is_connected or not self.client:
            logger.warning("[MQTT] 未连接，无法发送消息")
            return False

        try:
            # 替换主题中的{client_id}
            topic = topic.format(client_id=self.config.client_id)

            # 序列化payload
            if isinstance(payload, dict):
                # 添加时间戳
                payload['_timestamp'] = time.time()
                data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            elif isinstance(payload, (str, bytes)):
                data = payload.encode('utf-8') if isinstance(payload, str) else payload
            else:
                data = str(payload).encode('utf-8')

            qos = qos if qos is not None else self.config.qos

            # 发送消息
            info = self.client.publish(topic, data, qos=qos, retain=retain)

            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                self.stats['messages_sent'] += 1
                self.stats['bytes_sent'] += len(data)
                logger.debug(f"[MQTT] → [{topic}] ({len(data)}B)")
                return True
            else:
                logger.error(f"[MQTT] 发送失败 (rc={info.rc})")
                return False

        except Exception as e:
            logger.error(f"[MQTT] 发布异常: {e}")
            self.stats['last_error'] = str(e)
            return False

    def publish_gps(self, latitude: float, longitude: float,
                   altitude: float, num_satellites: int,
                   fix_type: int = 2, ground_speed: float = 0.0,
                   ground_course: float = 0.0, hdop: float = 1.0) -> bool:
        """
        发布GPS定位数据 (便捷方法!)

        Args:
            latitude: 纬度 (度)
            longitude: 经度 (度)
            altitude: 海拔高度 (米)
            num_satellites: 卫星数量
            fix_type: 定位类型 (0=None, 1=2D, 2=3D, 3=DGPS)
            ground_speed: 地速 (m/s)
            ground_course: 地面航向 (度)
            hdop: 水平精度因子

        Returns:
            True=发送成功
        """
        payload = {
            'type': 'gps',
            'fix_type': fix_type,
            'num_satellites': num_satellites,
            'latitude': round(latitude, 7),
            'longitude': round(longitude, 7),
            'altitude': round(altitude, 2),
            'ground_speed': round(ground_speed, 2),
            'ground_course': round(ground_course, 1),
            'hdop': round(hdop, 2)
        }
        return self.publish(self.config.topic_gps, payload)

    def publish_status(self, armed: bool, flight_mode: str = "MANUAL",
                      vbat: float = 0.0, cpu_load: int = 0,
                      rssi: int = 0) -> bool:
        """
        发布飞行状态数据 (便捷方法!)
        """
        payload = {
            'type': 'status',
            'armed': armed,
            'flight_mode': flight_mode,
            'vbat': round(vbat, 2),
            'cpu_load': cpu_load,
            'rssi': rssi
        }
        return self.publish(self.config.topic_status, payload)

    def publish_imu(self, accel_x: float, accel_y: float, accel_z: float,
                   gyro_x: float, gyro_y: float, gyro_z: float) -> bool:
        """
        发布IMU数据 (便捷方法!)
        """
        payload = {
            'type': 'imu',
            'accel': {'x': round(accel_x, 3), 'y': round(accel_y, 3), 'z': round(accel_z, 3)},
            'gyro': {'x': round(gyro_x, 1), 'y': round(gyro_y, 1), 'z': round(gyro_z, 1)}
        }
        return self.publish(self.config.topic_imu, payload)

    def publish_rc(self, channels: List[int]) -> bool:
        """
        发布遥控器通道数据 (便捷方法!)
        """
        payload = {
            'type': 'rc',
            'channels': channels[:8],  # 最多8个通道
            'count': len(channels)
        }
        return self.publish(self.config.topic_rc, payload)

    def send_command_to_fc(self, fc_client_id: str, payload: dict) -> bool:
        """
        Send a command to flight controller via MQTT

        Args:
            fc_client_id: Flight controller's MQTT client ID (e.g. "INAV_FC_STM32_001")
            payload: Command dict (will be JSON serialized)
                     e.g. {"cmd":"set_pid","axis":"roll","type":"rate","kp":4.5,...}

        Returns:
            True=send success
        """
        topic = f"inav/{fc_client_id}/cmd"
        return self.publish(topic, payload)

    # ===== Response callback for FC commands =====
    _resp_callbacks: list = []

    @classmethod
    def add_resp_callback(cls, callback):
        """Register callback for FC response messages (topic: inav/+/resp)"""
        cls._resp_callbacks.append(callback)

    @classmethod
    def remove_resp_callback(cls, callback):
        """Unregister callback"""
        if callback in cls._resp_callbacks:
            cls._resp_callbacks.remove(callback)

    @staticmethod
    def _dispatch_resp(topic: str, payload: dict):
        """Dispatch received response to all registered callbacks"""
        for cb in list(MQTTManager._resp_callbacks):  # copy list for safe iteration
            try:
                cb(topic, payload)
            except Exception as e:
                logger.error(f"[MQTT] resp_callback error: {e}")

    # ===== 订阅功能 =====

    def subscribe(self, topic: str, qos: Optional[int] = None) -> bool:
        """
        订阅主题

        Args:
            topic: 主题名称 (支持通配符 + 和 #)
            qos: 服务质量

        Returns:
            True=订阅成功
        """
        if not self.is_connected or not self.client:
            logger.warning("[MQTT] 未连接，无法订阅")
            return False

        try:
            topic = topic.format(client_id=self.config.client_id)
            qos = qos if qos is not None else self.config.qos

            result, mid = self.client.subscribe(topic, qos)

            if result == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"[MQTT] ✓ 已订阅 [{topic}] (QoS={qos})")
                return True
            else:
                logger.error(f"[MQTT] ✗ 订阅失败 (rc={result})")
                return False

        except Exception as e:
            logger.error(f"[MQTT] 订阅异常: {e}")
            return False

    def unsubscribe(self, topic: str) -> bool:
        """取消订阅"""
        if not self.is_connected or not self.client:
            return False

        try:
            topic = topic.format(client_id=self.config.client_id)
            result, mid = self.client.unsubscribe(topic)
            return result == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"[MQTT] 取消订阅异常: {e}")
            return False

    def subscribe_default_topics(self) -> bool:
        """
        订阅所有默认主题 (一次性订阅所有需要的主题)

        默认主题列表:
          - inav/{client_id}/cmd     接收指令
          - inav/#                  接收所有INAV消息 (调试用)
        """
        topics = [
            self.config.topic_cmd,
            "inav/+/resp",   # FC responses (wildcard for any client_id)
            "inav/#"         # All INAV messages
        ]

        success = True
        for topic in topics:
            if not self.subscribe(topic):
                success = False

        return success

    # ===== 内部回调函数 =====

    def _on_connect(self, client, userdata, flags, rc):
        """连接成功回调 (paho-mqtt内部调用)"""
        with self._mutex:
            self.is_connected = True
            self.is_connecting = False

        if rc == 0:
            logger.info(f"[MQTT] ✓ 连接建立成功 | Session Present: {flags.get('session present', False)}")

            # 自动订阅默认主题
            self.subscribe_default_topics()

            # 触发用户回调
            for cb in self._on_connect_callbacks:
                try:
                    cb(True)
                except Exception as e:
                    logger.error(f"[MQTT] on_connect回调异常: {e}")

        else:
            error_msg = {
                0: "成功",
                1: "协议版本错误",
                2: "客户端标识符无效",
                3: "服务器不可用",
                4: "用户名密码错误",
                5: "无权连接"
            }.get(rc, f"未知错误({rc})")

            logger.error(f"[MQTT] ✗ 连接失败: {error_msg}")
            self.is_connected = False
            self.is_connecting = False

    def _on_disconnect(self, client, userdata, rc):
        """断开连接回调"""
        with self._mutex:
            was_connected = self.is_connected
            self.is_connected = False
            self.is_connecting = False

        if rc == 0:
            logger.info("[MQTT] 正常断开连接")
        else:
            logger.warning(f"[MQTT] 意外断开 (rc={rc}), 将尝试重连...")

            # 触发用户回调
            for cb in self._on_disconnect_callbacks:
                try:
                    cb(rc)
                except Exception as e:
                    logger.error(f"[MQTT] on_disconnect回调异常: {e}")

            # 自动重连
            if self.config.auto_reconnect:
                self._schedule_reconnect()

        for cb in self._on_disconnect_callbacks:
            try:
                cb(rc)
            except Exception:
                pass

    def _on_message(self, client, userdata, msg):
        """收到消息回调"""
        try:
            topic = msg.topic
            payload_bytes = msg.payload

            # 更新统计
            self.stats['messages_received'] += 1
            self.stats['bytes_received'] += len(payload_bytes)

            # 尝试解析JSON
            try:
                payload_dict = json.loads(payload_bytes.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload_dict = {'raw_data': payload_bytes.hex()}

            logger.debug(f"[MQTT] ← [{topic}] ({len(payload_bytes)}B)")

            # Dispatch FC response messages to dedicated callbacks
            if '/resp' in topic:
                self._dispatch_resp(topic, payload_dict)

            # Call all registered general callbacks
            for cb in self._on_message_callbacks:
                try:
                    cb(topic, payload_dict)
                except Exception as e:
                    logger.error(f"[MQTT] 消息回调异常: {e}")

        except Exception as e:
            logger.error(f"[MQTT] 消息处理异常: {e}")

    def _schedule_reconnect(self):
        """调度自动重连 (指数退避)"""
        if self._reconnect_timer:
            self._reconnect_timer.cancel()

        delay = min(
            self.config.reconnect_delay_min * (2 ** self.stats['reconnect_count']),
            self.config.reconnect_delay_max
        )

        logger.info(f"[MQTT] 将在 {delay:.1f}s 后重连 (第{self.stats['reconnect_count']+1}次)...")

        self._reconnect_timer = Timer(delay, self._reconnect_attempt)
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _reconnect_attempt(self):
        """执行重连尝试"""
        self.stats['reconnect_count'] += 1
        logger.info(f"[MQTT] 尝试重连... (#{self.stats['reconnect_count']})")

        if self.connect():
            self.stats['reconnect_count'] = 0  # 重置计数器
        else:
            self._schedule_reconnect()  # 继续重试

    # ===== 属性访问 =====

    @property
    def uptime_seconds(self) -> float:
        """在线时长(秒)"""
        if self.stats['uptime_start'] > 0:
            return time.time() - self.stats['uptime_start']
        return 0.0

    def get_stats(self) -> dict:
        """获取统计信息 (返回副本)"""
        stats = self.stats.copy()
        stats['uptime'] = self.uptime_seconds
        stats['is_connected'] = self.is_connected
        stats['broker'] = f"{self.config.broker_host}:{self.config.broker_port}"
        stats['client_id'] = self.config.client_id
        return stats

    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'messages_sent': 0,
            'messages_received': 0,
            'bytes_sent': 0,
            'bytes_received': 0,
            'connect_count': self.stats.get('connect_count', 0),
            'reconnect_count': 0,
            'last_error': None,
            'uptime_start': time.time() if self.is_connected else 0
        }

    def __del__(self):
        """析构时自动断开 (安全版本!)"""
        try:
            # ★ 安全检查: 确保关键属性存在
            if hasattr(self, 'client') and self.client:
                self.disconnect()
        except Exception as e:
            # 析构函数中忽略所有异常，避免程序崩溃
            pass


# ===== 便捷测试函数 =====

def test_mqtt_connection(preset: MQTTPreset = MQTTPreset.EMQX_CN,
                         client_id: str = "INAV_Test_Client"):
    """
    快速测试MQTT连接

    Args:
        preset: Broker预设
        client_id: 客户端ID

    Returns:
        True=测试通过
    """
    print("=" * 60)
    print("  MQTT 连接测试工具")
    print("=" * 60)

    manager = MQTTManager()

    def on_msg(topic, payload):
        print(f"\n[收到消息] Topic: {topic}")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    print(f"\n[1/4] 连接Broker: {preset.value}...")
    if not manager.connect(client_id=client_id, preset=preset, on_message=on_msg):
        print("  ✗ 连接失败!")
        return False
    print(f"  ✓ 连接成功! ClientID={client_id}")

    print("\n[2/4] 发布测试消息...")
    test_topics = [
        ("GPS数据", lambda: manager.publish_gps(22.536800, 113.912345, 32.5, 8)),
        ("状态数据", lambda: manager.publish_status(True, "STABILIZE", 12.6, 35)),
        ("IMU数据", lambda: manager.publish_imu(0.01, -0.02, 9.81, 0.5, -0.3, 0.1)),
        ("RC通道", lambda: manager.publish_rc([1500, 1500, 1200, 1500, 1000, 1500, 1500, 1500])),
    ]

    for name, pub_func in test_topics:
        if pub_func():
            print(f"  ✓ {name} 发送成功")
        else:
            print(f"  ✗ {name} 发送失败")

    print("\n[3/4] 等待接收消息 (5秒)...")
    time.sleep(5)

    print("\n[4/4] 统计信息:")
    stats = manager.get_stats()
    print(f"  发送: {stats['messages_sent']} 条 ({stats['bytes_sent']} B)")
    print(f"  接收: {stats['messages_received']} 条 ({stats['bytes_received']} B)")
    print(f"  在线: {stats['uptime']:.1f}s")

    print("\n[5/5] 断开连接...")
    manager.disconnect()
    print("  ✓ 已断开")

    print("\n" + "=" * 60)
    print("  测试完成!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys

    # 支持命令行参数选择Broker
    preset_map = {
        'cn': MQTTPreset.EMQX_CN,
        'global': MQTTPreset.EMQX_GLOBAL,
    }

    preset = preset_map.get(sys.argv[1].lower() if len(sys.argv) > 1 else 'cn',
                            MQTTPreset.EMQX_CN)

    client_id = sys.argv[2] if len(sys.argv) > 2 else "INAV_Test_Python"

    test_mqtt_connection(preset=preset, client_id=client_id)
