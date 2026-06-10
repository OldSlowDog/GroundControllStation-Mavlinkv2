"""
IMU校准数据采集器
包含加速度计、陀螺仪的校准采集和算法实现
"""

import math
import time
from typing import List, Optional, Tuple

from core.data_collector import (
    DataCollector, CalibrationType, CalibrationDataPoint, 
    CalibrationResult, calibration_manager
)
from core.protocol_parser import FlightData
from core.data_manager import data_manager


class IMUAccelCalibrator(DataCollector):
    """
    IMU加速度计校准采集器
    
    使用方法：
    1. 将飞控水平放置在桌面上
    2. 启动采集（默认1000个样本）
    3. 自动计算零偏和灵敏度
    
    算法原理：
    - 假设静止时加速度计应该读取 [0, 0, g] 或其变体
    - 计算各轴的平均值作为零偏
    - g值用于校准灵敏度
    """
    
    # 重力加速度标准值 (m/s^2)
    GRAVITY = 9.80665
    
    def __init__(self, 
                 sample_rate_hz: int = 100,
                 required_samples: int = 1000,
                 timeout_seconds: float = 15.0,
                 orientation: str = 'level'):
        """
        初始化加速度计校准器
        
        Args:
            sample_rate_hz: 采样率 (Hz)
            required_samples: 需要的样本数
            timeout_seconds: 超时时间 (秒)
            orientation: 放置方向 ('level'=水平, 'upside_down'=倒置)
        """
        super().__init__(
            calibration_type=CalibrationType.IMU_ACCEL,
            sample_rate_hz=sample_rate_hz,
            required_samples=required_samples,
            timeout_seconds=timeout_seconds
        )
        
        self.orientation = orientation
        
        # 校准结果参数
        self.accel_bias = {'x': 0.0, 'y': 0.0, 'z': 0.0}      # 零偏
        self.accel_scale = {'x': 1.0, 'y': 1.0, 'z': 1.0}     # 灵敏度
        
    def _collect_sample(self) -> Optional[CalibrationDataPoint]:
        """采集单个加速度计样本"""
        data = data_manager.get_current()
        
        if data.timestamp == 0:
            return None
        
        return CalibrationDataPoint(
            timestamp=data.timestamp,
            values={
                'accel_x': data.accel_x,
                'accel_y': data.accel_y,
                'accel_z': data.accel_z,
                'temperature': getattr(data, 'temperature', 25.0)
            }
        )
    
    def _process_data(self) -> bool:
        """处理加速度计数据，计算零偏和灵敏度"""
        if len(self._data_buffer) < 10:
            self.result.error_message = "采样数量不足"
            return False
        
        # 提取各轴数据
        accel_x = [dp.values['accel_x'] for dp in self._data_buffer]
        accel_y = [dp.values['accel_y'] for dp in self._data_buffer]
        accel_z = [dp.values['accel_z'] for dp in self._data_buffer]
        
        n = len(accel_x)
        
        # 计算平均值（零偏估计）
        mean_x = sum(accel_x) / n
        mean_y = sum(accel_y) / n
        mean_z = sum(accel_z) / n
        
        # 计算标准差（评估稳定性）
        std_x = math.sqrt(sum((x - mean_x)**2 for x in accel_x) / n)
        std_y = math.sqrt(sum((y - mean_y)**2 for y in accel_y) / n)
        std_z = math.sqrt(sum((z - mean_z)**2 for z in accel_z) / n)
        
        # 稳定性检查：标准差应小于阈值（说明飞机确实静止）
        stability_threshold = 0.02  # 0.02g 以内认为稳定
        if std_x > stability_threshold or std_y > stability_threshold:
            self.result.error_message = (
                f"数据不稳定！标准差: X={std_x:.4f}, Y={std_y:.4f} "
                f"(阈值: {stability_threshold})。请确保飞机完全静止。"
            )
            return False
        
        # 根据放置方向确定期望的重力向量
        if self.orientation == 'level':
            # 水平放置：Z轴向上，期望读取 [0, 0, +g]
            expected_gravity_axis = 'z'
            expected_sign = +1
        elif self.orientation == 'upside_down':
            # 倒置：Z轴向下，期望读取 [0, 0, -g]
            expected_gravity_axis = 'z'
            expected_sign = -1
        else:
            expected_gravity_axis = None
            expected_sign = 0
        
        # 计算零偏（水平轴应为0，垂直轴减去重力）
        bias_x = mean_x
        bias_y = mean_y
        
        if expected_gravity_axis == 'z':
            bias_z = mean_z - (expected_sign * self.GRAVITY)
            # 计算Z轴灵敏度
            measured_g = abs(mean_z)
            scale_z = measured_g / self.GRAVITY if measured_g > 0 else 1.0
        else:
            bias_z = mean_z
            scale_z = 1.0
        
        # X/Y轴灵敏度假设为1.0（需要多位置校准才能精确计算）
        scale_x = 1.0
        scale_y = 1.0
        
        # 保存校准参数
        self.accel_bias = {
            'x': round(bias_x, 6),
            'y': round(bias_y, 6),
            'z': round(bias_z, 6)
        }
        
        self.accel_scale = {
            'x': round(scale_x, 6),
            'y': round(scale_y, 6),
            'z': round(scale_z, 6)
        }
        
        # 保存到result
        self.result.parameters = {
            'accel_bias': self.accel_bias,
            'accel_scale': self.accel_scale,
            'orientation': self.orientation,
            'gravity_used': self.GRAVITY,
            'method': 'single_position'
        }
        
        # 保存统计信息
        self.result.statistics = {
            'raw_mean': {
                'x': round(mean_x, 6),
                'y': round(mean_y, 6),
                'z': round(mean_z, 6)
            },
            'std_dev': {
                'x': round(std_x, 6),
                'y': round(std_y, 6),
                'z': round(std_z, 6)
            },
            'sample_count': n,
            'stability': 'PASS' if max(std_x, std_y) < stability_threshold else 'FAIL'
        }
        
        print(f"[加速度计校准] 完成!")
        print(f"  零偏 (Bias): X={self.accel_bias['x']:+.4f}, Y={self.accel_bias['y']:+.4f}, Z={self.accel_bias['z']:+.4f}")
        print(f"  灵敏度 (Scale): X={self.accel_scale['x']:.4f}, Y={self.accel_scale['y']:.4f}, Z={self.accel_scale['z']:.4f}")
        print(f"  稳定性: {self.result.statistics['stability']}")
        
        return True
    
    def get_calibration_code(self) -> str:
        """生成C语言格式的校准代码"""
        code = f"""// 加速度计校准参数 (自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')})
// 方法: 单位置法 ({self.orientation})
// 样本数: {len(self._data_buffer)}

#define ACCEL_BIAS_X  {self.accel_bias['x']:+.8ff}
#define ACCEL_BIAS_Y  {self.accel_bias['y']:+.8ff}
#define ACCEL_BIAS_Z  {self.accel_bias['z']:+.8ff}

#define ACCEL_SCALE_X {self.accel_scale['x']:.8ff}
#define ACCEL_SCALE_Y {self.accel_scale['y']:.8ff}
#define ACCEL_SCALE_Z {self.accel_scale['z']:.8ff}

// 应用校准:
// accel_corrected.x = (raw.x - ACCEL_BIAS_X) * ACCEL_SCALE_X;
// accel_corrected.y = (raw.y - ACCEL_BIAS_Y) * ACCEL_SCALE_Y;
// accel_corrected.z = (raw.z - ACCEL_BIAS_Z) * ACCEL_SCALE_Z;
"""
        return code


class IMUGyroCalibrator(DataCollector):
    """
    IMU陀螺仪零偏校准采集器
    
    使用方法：
    1. 保持飞控完全静止
    2. 采集若干秒的数据
    3. 计算陀螺仪零偏（静止时输出应为0）
    
    注意事项：
    - 采集期间绝对不能移动飞控
    - 避免振动和温度变化
    - 建议在开机后等待温度稳定再校准
    """
    
    def __init__(self,
                 sample_rate_hz: int = 200,
                 required_samples: int = 2000,   # 2000样本 @200Hz = 10秒
                 timeout_seconds: float = 20.0):
        
        super().__init__(
            calibration_type=CalibrationType.IMU_GYRO,
            sample_rate_hz=sample_rate_hz,
            required_samples=required_samples,
            timeout_seconds=timeout_seconds
        )
        
        self.gyro_bias = {'x': 0.0, 'y': 0.0, 'z': 0.0}
        
    def _collect_sample(self) -> Optional[CalibrationDataPoint]:
        """采集单个陀螺仪样本"""
        data = data_manager.get_current()
        
        if data.timestamp == 0:
            return None
        
        return CalibrationDataPoint(
            timestamp=data.timestamp,
            values={
                'gyro_x': data.gyro_x,
                'gyro_y': data.gyro_y,
                'gyro_z': data.gyro_z,
                'temperature': getattr(data, 'temperature', 25.0)
            }
        )
    
    def _process_data(self) -> bool:
        """处理陀螺仪数据，计算零偏"""
        if len(self._data_buffer) < 100:
            self.result.error_message = "采样数量不足"
            return False
        
        gyro_x = [dp.values['gyro_x'] for dp in self._data_buffer]
        gyro_y = [dp.values['gyro_y'] for dp in self._data_buffer]
        gyro_z = [dp.values['gyro_z'] for dp in self._data_buffer]
        
        n = len(gyro_x)
        
        # 计算均值（零偏）
        mean_x = sum(gyro_x) / n
        mean_y = sum(gyro_y) / n
        mean_z = sum(gyro_z) / n
        
        # 计算标准差（噪声水平）
        std_x = math.sqrt(sum((x - mean_x)**2 for x in gyro_x) / n)
        std_y = math.sqrt(sum((y - mean_y)**2 for y in gyro_y) / n)
        std_z = math.sqrt(sum((z - mean_z)**2 for z in gyro_z) / n)
        
        # 计算峰峰值（最大偏差）
        peak_peak_x = max(gyro_x) - min(gyro_x)
        peak_peak_y = max(gyro_y) - min(gyro_y)
        peak_peak_z = max(gyro_z) - min(gyro_z)
        
        # 稳定性检查：如果标准差过大，可能存在运动或振动
        noise_threshold = 5.0  # °/s，超过此值认为不稳定
        if max(std_x, std_y, std_z) > noise_threshold:
            self.result.error_message = (
                f"噪声过大！标准差: X={std_x:.2f}, Y={std_y:.2f}, Z={std_z:.2f} °/s\n"
                f"请确保飞控完全静止且无振动。"
            )
            return False
        
        # 保存零偏参数
        self.gyro_bias = {
            'x': round(mean_x, 6),
            'y': round(mean_y, 6),
            'z': round(mean_z, 6)
        }
        
        # 保存结果
        self.result.parameters = {
            'gyro_bias': self.gyro_bias,
            'method': 'static_average',
            'duration_sec': n / self.sample_rate_hz
        }
        
        self.result.statistics = {
            'bias': {
                'x': round(mean_x, 4),
                'y': round(mean_y, 4),
                'z': round(mean_z, 4)
            },
            'noise_std': {
                'x': round(std_x, 4),
                'y': round(std_y, 4),
                'z': round(std_z, 4)
            },
            'peak_peak': {
                'x': round(peak_peak_x, 4),
                'y': round(peak_peak_y, 4),
                'z': round(peak_peak_z, 4)
            },
            'sample_count': n,
            'quality': 'GOOD' if max(std_x, std_y, std_z) < 2.0 else 
                      ('ACCEPTABLE' if max(std_x, std_y, std_z) < 5.0 else 'POOR')
        }
        
        print(f"[陀螺仪校准] 完成!")
        print(f"  零偏 (°/s): X={self.gyro_bias['x']:+.4f}, Y={self.gyro_bias['y']:+.4f}, Z={self.gyro_bias['z']:+.4f}")
        print(f"  噪声 (σ): X={std_x:.2f}, Y={std_y:.2f}, Z={std_z:.2f} °/s")
        print(f"  质量: {self.result.statistics['quality']}")
        
        return True
    
    def get_calibration_code(self) -> str:
        """生成C语言格式的校准代码"""
        code = f"""// 陀螺仪校准参数 (自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')})
// 方法: 静态平均法
// 样本数: {len(self._data_buffer)}
// 采集时长: {self.result.parameters.get('duration_sec', 0):.1f}秒

#define GYRO_BIAS_X  {self.gyro_bias['x']:+.8ff}f
#define GYRO_BIAS_Y  {self.gyro_bias['y']:+.8ff}f
#define GYRO_BIAS_Z  {self.gyro_bias['z']:+.8ff}f

// 应用校准:
// gyro_corrected.x = raw.x - GYRO_BIAS_X;
// gyro_corrected.y = raw.y - GYRO_BIAS_Y;
// gyro_corrected.z = raw.z - GYRO_BIAS_Z;
"""
        return code


# 工厂函数：创建指定类型的校准器
def create_calibrator(cal_type: CalibrationType, **kwargs) -> DataCollector:
    """工厂函数，创建校准采集器"""
    if cal_type == CalibrationType.IMU_ACCEL:
        return IMUAccelCalibrator(**kwargs)
    elif cal_type == CalibrationType.IMU_GYRO:
        return IMUGyroCalibrator(**kwargs)
    else:
        raise ValueError(f"不支持的校准类型: {cal_type}")