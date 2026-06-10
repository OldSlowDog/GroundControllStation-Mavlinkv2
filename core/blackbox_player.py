"""
黑匣子数据回放器 (Blackbox Data Player)
支持飞行数据的录制、回放、时间轴控制和多通道同步显示
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Callable, Any
from enum import Enum
import threading


class PlaybackState(Enum):
    """播放状态枚举"""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"


@dataclass
class FlightDataPoint:
    """单个时刻的完整飞行数据"""
    timestamp: float              # 时间戳（秒）
    
    # 姿态数据
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    
    # IMU传感器
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    
    # 遥控器输入
    rc_roll: int = 1500
    rc_pitch: int = 1500
    rc_yaw: int = 1500
    rc_throttle: int = 1000
    rc_aux1: int = 1500
    rc_aux2: int = 1500
    rc_aux3: int = 1500
    rc_aux4: int = 1500
    
    # 电机输出
    motor_1: int = 0
    motor_2: int = 0
    motor_3: int = 0
    motor_4: int = 0
    
    # 系统状态
    armed: bool = False
    vbat: float = 12.6
    amperage: float = 0.0
    altitude: float = 0.0
    
    # GPS数据（可选）
    gps_lat: float = 0.0
    gps_lon: float = 0.0
    gps_alt: float = 0.0
    gps_speed: float = 0.0
    gps_heading: float = 0.0
    
    # 事件标记
    event: str = ""          # 如 "ARMED", "DISARMED", "ERROR"
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BlackboxSession:
    """一次完整的黑匣子记录会话"""
    filename: str = ""
    start_time: str = ""         # ISO格式开始时间
    end_time: str = ""           # ISO格式结束时间
    total_duration: float = 0.0   # 总时长(秒)
    total_samples: int = 0        # 总样本数
    sample_rate_hz: int = 20      # 采样率
    
    # 完整数据序列
    data_points: List[FlightDataPoint] = field(default_factory=list)
    
    # 元信息
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 统计摘要
    summary: Dict[str, Any] = field(default_factory=dict)
    
    def get_data_at_time(self, target_time: float) -> Optional[FlightDataPoint]:
        """
        获取指定时刻的数据点（线性插值）
        
        Args:
            target_time: 目标时间（秒，从0开始）
            
        Returns:
            插值后的数据点，如果超出范围则返回边界值
        """
        if not self.data_points:
            return None
        
        if len(self.data_points) == 1:
            return self.data_points[0]
        
        # 边界检查
        if target_time <= 0:
            return self.data_points[0]
        if target_time >= self.total_duration:
            return self.data_points[-1]
        
        # 二分查找最近的两个数据点
        left = 0
        right = len(self.data_points) - 1
        
        while left < right - 1:
            mid = (left + right) // 2
            if self.data_points[mid].timestamp < target_time:
                left = mid
            else:
                right = mid
        
        # 线性插值
        t1 = self.data_points[left].timestamp
        t2 = self.data_points[right].timestamp
        
        if abs(t2 - t1) < 0.0001:  # 避免除零
            return self.data_points[left]
        
        ratio = (target_time - t1) / (t2 - t1)
        ratio = max(0.0, min(1.0, ratio))  # 限制在[0,1]范围
        
        p1 = self.data_points[left]
        p2 = self.data_points[right]
        
        # 对所有数值字段进行插值
        result = FlightDataPoint(timestamp=target_time)
        
        numeric_fields = [
            'roll', 'pitch', 'yaw',
            'accel_x', 'accel_y', 'accel_z',
            'gyro_x', 'gyro_y', 'gyro_z',
            'rc_roll', 'rc_pitch', 'rc_yaw', 'rc_throttle',
            'rc_aux1', 'rc_aux2', 'rc_aux3', 'rc_aux4',
            'motor_1', 'motor_2', 'motor_3', 'motor_4',
            'vbat', 'amperage', 'altitude',
            'gps_lat', 'gps_lon', 'gps_alt', 'gps_speed', 'gps_heading'
        ]
        
        for field_name in numeric_fields:
            v1 = getattr(p1, field_name, 0)
            v2 = getattr(p2, field_name, 0)
            interpolated = v1 + (v2 - v1) * ratio
            setattr(result, field_name, interpolated)
        
        # 布尔字段取最近值
        result.armed = p1.armed if ratio < 0.5 else p2.armed
        result.event = p1.event if ratio < 0.5 else p2.event
        
        return result
    
    def get_time_range(self, start_offset: float = 0.0, duration: float = 10.0) -> List[FlightDataPoint]:
        """
        获取指定时间范围内的所有数据点
        
        Args:
            start_offset: 开始偏移（秒）
            duration: 持续时长（秒）
            
        Returns:
            该时间段内的数据点列表
        """
        result = []
        end_time = start_offset + duration
        
        for dp in self.data_points:
            if start_offset <= dp.timestamp <= end_time:
                result.append(dp)
            elif dp.timestamp > end_time:
                break
        
        return result
    
    def save_to_file(self, filepath: str) -> bool:
        """保存会话到JSON文件"""
        try:
            data = {
                'filename': os.path.basename(filepath),
                'start_time': self.start_time,
                'end_time': self.end_time,
                'total_duration': self.total_duration,
                'total_samples': self.total_samples,
                'sample_rate_hz': self.sample_rate_hz,
                'metadata': self.metadata,
                'summary': self.summary,
                'data_points': [dp.to_dict() for dp in self.data_points[:10000]]  # 最多保存前1万个点
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"保存失败: {e}")
            return False
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'BlackboxSession':
        """从文件加载会话"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            session = cls()
            session.filename = data.get('filename', filepath)
            session.start_time = data.get('start_time', '')
            session.end_time = data.get('end_time', '')
            session.total_duration = data.get('total_duration', 0.0)
            session.total_samples = data.get('total_samples', 0)
            session.sample_rate_hz = data.get('sample_rate_hz', 20)
            session.metadata = data.get('metadata', {})
            session.summary = data.get('summary', {})
            
            # 加载数据点
            raw_points = data.get('data_points', [])
            session.data_points = [
                FlightDataPoint(**dp) for dp in raw_points
            ]
            
            return session
            
        except Exception as e:
            print(f"加载失败: {e}")
            return None


class BlackboxPlayer:
    """
    黑匣子数据回放器核心类
    
    功能：
    - 播放/暂停/停止控制
    - 时间轴拖动定位
    - 变速播放（0.25x - 4x）
    - 循环播放
    - 多通道数据同步回调
    """
    
    def __init__(self):
        # 会话数据
        self.session: Optional[BlackboxSession] = None
        
        # 播放状态
        self.state = PlaybackState.STOPPED
        self.current_time: float = 0.0     # 当前播放位置（秒）
        self.playback_speed: float = 1.0  # 播放速度倍率
        self.loop_enabled: bool = False    # 是否循环播放
        
        # 控制线程
        self._playback_thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._paused: bool = False
        
        # 定时器精度（毫秒）
        self._tick_interval_ms: int = 50  # 20Hz更新频率
        
        # 回调函数
        self.on_position_changed: Optional[Callable[[float, FlightDataPoint], None]] = None
        self.on_state_changed: Optional[Callable[[PlaybackState], None]] = None
        self.on_session_loaded: Optional[Callable[[BlackboxSession], None]] = None
    
    @property
    def is_playing(self) -> bool:
        return self.state == PlaybackState.PLAYING
    
    @property
    def duration(self) -> float:
        """获取总时长"""
        if self.session:
            return self.session.total_duration
        return 0.0
    
    @property
    def progress(self) -> float:
        """获取当前进度 (0.0 - 1.0)"""
        if self.duration > 0:
            return min(1.0, max(0.0, self.current_time / self.duration))
        return 0.0
    
    def load_session(self, session: BlackboxSession) -> bool:
        """加载回放会话"""
        self.stop()
        self.session = session
        self.current_time = 0.0
        self.state = PlaybackState.LOADED
        
        if self.on_session_loaded:
            self.on_session_loaded(session)
        
        return True
    
    def load_from_file(self, filepath: str) -> bool:
        """从文件加载会话并准备回放"""
        session = BlackboxSession.load_from_file(filepath)
        if session:
            return self.load_session(session)
        return False
    
    def play(self):
        """开始或恢复播放"""
        if not self.session or not self.session.data_points:
            return
        
        if self.state == PlaybackState.PLAYING:
            return  # 已经在播放
        
        self._running = True
        self._paused = False
        self.state = PlaybackState.PLAYING
        
        # 启动播放线程
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()
        
        if self.on_state_changed:
            self.on_state_changed(self.state)
    
    def pause(self):
        """暂停播放"""
        self._paused = True
        self.state = PlaybackState.PAUSED
        
        if self.on_state_changed:
            self.on_state_changed(self.state)
    
    def stop(self):
        """停止播放并重置位置"""
        self._running = False
        self._paused = False
        self._playback_thread = None
        
        old_state = self.state
        self.state = PlaybackState.STOPPED
        self.current_time = 0.0
        
        if old_state != PlaybackState.STOPPED and self.on_state_changed:
            self.on_state_changed(self.state)
    
    def seek(self, time_position: float):
        """跳转到指定时间位置"""
        if not self.session:
            return
        
        was_playing = self.is_playing
        
        if was_playing:
            self.pause()
        
        self.current_time = max(0.0, min(time_position, self.duration))
        
        # 发送当前位置的数据
        data_point = self.session.get_data_at_time(self.current_time)
        if data_point and self.on_position_changed:
            self.on_position_changed(self.current_time, data_point)
        
        if was_playing:
            self.play()
    
    def set_speed(self, speed: float):
        """设置播放速度 (0.25x - 4.0x)"""
        self.playback_speed = max(0.25, min(4.0, speed))
    
    def toggle_loop(self):
        """切换循环模式"""
        self.loop_enabled = not self.loop_enabled
        return self.loop_enabled
    
    def _playback_loop(self):
        """播放主循环（后台线程）"""
        last_tick = time.time()
        
        while self._running and self.session:
            if self._paused:
                time.sleep(0.05)
                continue
            
            # 计算实际经过的时间
            now = time.time()
            real_elapsed = now - last_tick
            last_tick = now
            
            # 应用速度倍率
            playback_elapsed = real_elapsed * self.playback_speed
            
            # 更新当前时间
            self.current_time += playback_elapsed
            
            # 检查是否到达结尾
            if self.current_time >= self.duration:
                if self.loop_enabled:
                    self.current_time = 0.0  # 循环回到开头
                else:
                    # 自动停止
                    self._running = False
                    self.state = PlaybackState.STOPPED
                    if self.on_state_changed:
                        self.on_state_changed(self.state)
                    break
            
            # 获取当前位置的数据并发送回调
            data_point = self.session.get_data_at_time(self.current_time)
            if data_point and self.on_position_changed:
                self.on_position_changed(self.current_time, data_point)
            
            # 控制更新频率
            sleep_time = self._tick_interval_ms / 1000.0 - (time.time() - now)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        # 确保状态正确
        if not self._paused:
            self.state = PlaybackState.STOPPED
            if self.on_state_changed:
                self.on_state_changed(self.state)
    
    def get_statistics(self) -> Dict:
        """获取当前会话的统计信息"""
        if not self.session:
            return {}
        
        stats = {
            'duration_sec': self.session.total_duration,
            'sample_count': self.session.total_samples,
            'sample_rate': self.session.sample_rate_hz,
            'current_pos': round(self.current_time, 2),
            'progress_pct': f"{self.progress*100:.1f}%",
            'speed': f"{self.playback_speed:.2f}x",
            'loop': "ON" if self.loop_enabled else "OFF",
            'state': self.state.value
        }
        
        # 从summary中获取额外统计
        stats.update(self.session.summary)
        
        return stats