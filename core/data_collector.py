"""
校准数据采集器基类
提供统一的数据采集、处理、保存接口
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Callable, Optional, Any
from datetime import datetime
from enum import Enum
import threading
import time
import math


class CalibrationType(Enum):
    """校准类型枚举"""
    IMU_ACCEL = "imu_accel"           # 加速度计校准
    IMU_GYRO = "imu_gyro"             # 陀螺仪校准
    RC_MIDPOINT = "rc_midpoint"       # 遥控器中点校准
    ESC_CALIBRATION = "esc"           # 电调校准
    MAGNETOMETER = "magnetometer"     # 磁力计校准


class CalibrationStatus(Enum):
    """校准状态枚举"""
    IDLE = "idle"                     # 空闲
    PREPARING = "preparing"           # 准备中
    COLLECTING = "collecting"         # 采集中
    PROCESSING = "processing"         # 处理中
    COMPLETED = "completed"           # 已完成
    FAILED = "failed"                 # 失败
    CANCELLED = "cancelled"           # 已取消


@dataclass
class CalibrationDataPoint:
    """单个校准数据点"""
    timestamp: float                  # 时间戳
    values: Dict[str, float]          # 传感器值 {axis: value}
    
    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp,
            'values': self.values
        }


@dataclass
class CalibrationResult:
    """校准结果"""
    calibration_type: CalibrationType
    status: CalibrationStatus
    start_time: float = 0.0
    end_time: float = 0.0
    total_samples: int = 0
    
    # 原始数据
    raw_data: List[CalibrationDataPoint] = field(default_factory=list)
    
    # 校准参数（根据类型不同而不同）
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # 统计信息
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    # 错误信息
    error_message: str = ""
    
    def to_dict(self) -> dict:
        return {
            'calibration_type': self.calibration_type.value,
            'status': self.status.value,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'total_samples': self.total_samples,
            'parameters': self.parameters,
            'statistics': self.statistics,
            'error_message': self.error_message,
            'raw_data_count': len(self.raw_data)
        }
    
    def save_to_file(self, filepath: str) -> bool:
        """保存校准结果到JSON文件"""
        try:
            data = self.to_dict()
            # 保存原始数据（可选，可能很大）
            if len(self.raw_data) < 10000:  # 只在数据量不太大时保存
                data['raw_data'] = [dp.to_dict() for dp in self.raw_data]
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存失败: {e}")
            return False


class DataCollector(ABC):
    """
    数据采集器抽象基类
    
    所有具体的校准采集器都需要继承此类并实现：
    - _collect_sample(): 采集单个样本
    - _process_data(): 处理采集到的数据
    - validate_data(): 验证数据有效性
    """
    
    def __init__(self, 
                 calibration_type: CalibrationType,
                 sample_rate_hz: int = 100,
                 required_samples: int = 1000,
                 timeout_seconds: float = 30.0):
        
        self.calibration_type = calibration_type
        self.sample_rate_hz = sample_rate_hz
        self.required_samples = required_samples
        self.timeout_seconds = timeout_seconds
        
        # 状态管理
        self.status = CalibrationStatus.IDLE
        self.result = CalibrationResult(calibration_type=calibration_type, status=CalibrationStatus.IDLE)
        
        # 控制标志
        self._running = False
        self._cancelled = False
        
        # 回调函数
        self.on_progress: Optional[Callable[[int, int], None]] = None      # (current, total)
        self.on_status_changed: Optional[Callable[[CalibrationStatus], None]] = None
        self.on_data_received: Optional[Callable[[CalibrationDataPoint], None]] = None
        self.on_completed: Optional[Callable[[CalibrationResult], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        
        # 数据缓冲区
        self._data_buffer: List[CalibrationDataPoint] = []
        
        # 采集线程
        self._collect_thread: Optional[threading.Thread] = None
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def progress_percentage(self) -> float:
        if self.required_samples == 0:
            return 0.0
        return min(100.0, len(self._data_buffer) / self.required_samples * 100)
    
    def start_collection(self):
        """开始数据采集"""
        if self._running:
            return
        
        self._reset()
        self._running = True
        self._cancelled = False
        self.status = CalibrationStatus.PREPARING
        self._emit_status_changed()
        
        # 启动采集线程
        self._collect_thread = threading.Thread(target=self._collection_loop, daemon=True)
        self._collect_thread.start()
    
    def cancel_collection(self):
        """取消采集"""
        self._cancelled = True
        self._running = False
        self.status = CalibrationStatus.CANCELLED
        self.result.error_message = "用户取消"
        self._emit_status_changed()
    
    def _reset(self):
        """重置状态"""
        self._data_buffer.clear()
        self.result = CalibrationResult(calibration_type=self.calibration_type, status=CalibrationStatus.IDLE)
        self.result.start_time = time.time()
        self._cancelled = False
    
    def _collection_loop(self):
        """采集主循环（在后台线程中运行）"""
        try:
            self.status = CalibrationStatus.COLLECTING
            self._emit_status_changed()
            
            start_time = time.time()
            sample_interval = 1.0 / self.sample_rate_hz
            
            while (not self._cancelled and 
                   len(self._data_buffer) < self.required_samples and
                   (time.time() - start_time) < self.timeout_seconds):
                
                # 采集单个样本
                sample = self._collect_sample()
                if sample:
                    self._data_buffer.append(sample)
                    self.result.total_samples = len(self._data_buffer)
                    
                    # 发送进度回调
                    if self.on_progress:
                        self.on_progress(len(self._data_buffer), self.required_samples)
                    
                    # 发送数据回调（实时显示用）
                    if self.on_data_received:
                        self.on_data_received(sample)
                
                # 控制采样率
                elapsed = time.time() - start_time
                expected_time = len(self._data_buffer) * sample_interval
                sleep_time = expected_time - elapsed
                if sleep_time > 0:
                    time.sleep(min(sleep_time, 0.1))  # 最大睡眠10ms
            
            # 检查是否完成或超时/取消
            if self._cancelled:
                self.status = CalibrationStatus.CANCELLED
            elif len(self._data_buffer) < self.required_samples:
                self.status = CalibrationStatus.FAILED
                self.result.error_message = f"采样不足：仅采集到 {len(self._data_buffer)}/{self.required_samples} 个样本"
            else:
                self.status = CalibrationStatus.PROCESSING
                self._emit_status_changed()
                
                # 处理数据
                self.result.raw_data = self._data_buffer.copy()
                success = self._process_data()
                
                if success and self.validate_data():
                    self.status = CalibrationStatus.COMPLETED
                else:
                    self.status = CalibrationStatus.FAILED
            
            self.result.end_time = time.time()
            self.result.status = self.status
            self._running = False
            
            self._emit_status_changed()
            
            # 发送完成回调
            if self.on_completed:
                self.on_completed(self.result)
            
        except Exception as e:
            self.status = CalibrationStatus.FAILED
            self.result.error_message = str(e)
            self.result.end_time = time.time()
            self._running = False
            
            if self.on_error:
                self.on_error(str(e))
            if self.on_completed:
                self.on_completed(self.result)
            
            self._emit_status_changed()
    
    @abstractmethod
    def _collect_sample(self) -> Optional[CalibrationDataPoint]:
        """
        采集单个数据样本（子类必须实现）
        
        返回: CalibrationDataPoint 或 None（如果采集失败）
        """
        pass
    
    @abstractmethod
    def _process_data(self) -> bool:
        """
        处理采集到的数据（子类必须实现）
        
        返回: True表示成功，False表示失败
        """
        pass
    
    def validate_data(self) -> bool:
        """
        验证数据有效性（可被子类重写）
        
        默认实现：检查是否有足够的数据和基本统计合理性
        """
        if len(self._data_buffer) < self.required_samples // 2:
            self.result.error_message = "数据量不足以进行校准"
            return False
        
        # 检查数据是否为空
        if not self._data_buffer:
            self.result.error_message = "未采集到任何数据"
            return False
        
        return True
    
    def get_raw_data(self) -> List[CalibrationDataPoint]:
        """获取原始数据"""
        return self._data_buffer.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self._data_buffer:
            return {}
        
        stats = {}
        
        # 提取所有轴的数据
        axes = set()
        for dp in self._data_buffer:
            axes.update(dp.values.keys())
        
        for axis in sorted(axes):
            values = [dp.values.get(axis, 0) for dp in self._data_buffer]
            
            n = len(values)
            mean = sum(values) / n
            variance = sum((x - mean) ** 2 for x in values) / n
            std_dev = math.sqrt(variance)
            
            stats[axis] = {
                'mean': round(mean, 6),
                'min': round(min(values), 6),
                'max': round(max(values), 6),
                'std': round(std_dev, 6),
                'range': round(max(values) - min(values), 6),
                'count': n
            }
        
        self.result.statistics = stats
        return stats
    
    def _emit_status_changed(self):
        """发送状态改变信号"""
        if self.on_status_changed:
            self.on_status_changed(self.status)


# 全局校准管理器实例
calibration_manager = {
    'active_collector': None,
    'history': []
}