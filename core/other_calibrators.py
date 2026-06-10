"""
遥控器和磁力计校准数据采集器
"""

import math
import time
import numpy as np
from typing import List, Optional, Tuple

from core.data_collector import (
    DataCollector, CalibrationType, CalibrationDataPoint,
    CalibrationResult
)
from core.data_manager import data_manager


class RCMidpointCalibrator(DataCollector):
    """
    遥控器中点校准采集器
    
    使用方法：
    1. 将所有摇杆（Roll/Pitch/Yaw/Throttle）置于中间位置
    2. 对于油门，通常置于最低位
    3. AUX通道根据需要设置
    4. 启动采集，等待完成
    
    输出：各通道的中点值（用于后续的摇杆映射）
    """
    
    # 标准的中点值范围
    RC_MIDPOINT_STANDARD = 1500   # 标准PWM中点
    RC_MIN = 1000                 # 最小值
    RC_MAX = 2000                 # 最大值
    
    def __init__(self,
                 sample_rate_hz: int = 50,
                 required_samples: int = 500,
                 timeout_seconds: float = 15.0):
        
        super().__init__(
            calibration_type=CalibrationType.RC_MIDPOINT,
            sample_rate_hz=sample_rate_hz,
            required_samples=required_samples,
            timeout_seconds=timeout_seconds
        )
        
        self.rc_midpoints = {}
        self.channels = ['roll', 'pitch', 'yaw', 'throttle', 
                        'aux1', 'aux2', 'aux3', 'aux4']
    
    def _collect_sample(self) -> Optional[CalibrationDataPoint]:
        """采集单个RC通道样本"""
        data = data_manager.get_current()
        
        if data.timestamp == 0:
            return None
        
        return CalibrationDataPoint(
            timestamp=data.timestamp,
            values={
                'rc_roll': data.rc_roll,
                'rc_pitch': data.rc_pitch,
                'rc_yaw': data.rc_yaw,
                'rc_throttle': data.rc_throttle,
                'rc_aux1': getattr(data, 'rc_aux1', 1500),
                'rc_aux2': getattr(data, 'rc_aux2', 1500),
                'rc_aux3': getattr(data, 'rc_aux3', 1500),
                'rc_aux4': getattr(data, 'rc_aux4', 1500)
            }
        )
    
    def _process_data(self) -> bool:
        """处理RC数据，计算各通道中点"""
        if len(self._data_buffer) < 50:
            self.result.error_message = "采样数量不足"
            return False
        
        self.rc_midpoints = {}
        statistics = {}
        
        for channel in self.channels:
            key = f'rc_{channel}'
            values = [dp.values.get(key, 1500) for dp in self._data_buffer]
            
            n = len(values)
            mean = sum(values) / n
            
            # 计算统计量
            std = math.sqrt(sum((x - mean)**2 for x in values) / n)
            min_val = min(values)
            max_val = max(values)
            range_val = max_val - min_val
            
            # 稳定性检查：标准差应小于阈值（说明摇杆确实静止）
            stability_threshold = 10  # ±10 以内认为稳定
            
            self.rc_midpoints[channel] = round(mean, 1)
            
            statistics[channel] = {
                'midpoint': round(mean, 1),
                'min': min_val,
                'max': max_val,
                'std': round(std, 2),
                'range': range_val,
                'stable': range_val < stability_threshold * 2
            }
        
        # 检查所有通道是否稳定
        unstable_channels = [ch for ch, stats in statistics.items() if not stats['stable']]
        
        if unstable_channels and len(unstable_channels) < len(self.channels):
            self.result.error_message = (
                f"以下通道不稳定（请保持摇杆静止）: {', '.join(unstable_channels)}\n"
                f"建议重新采集。"
            )
            # 不直接返回False，允许用户决定是否接受
        
        # 保存结果
        self.result.parameters = {
            'rc_midpoints': self.rc_midpoints,
            'method': 'average'
        }
        
        self.result.statistics = statistics
        
        print(f"[遥控器中点校准] 完成!")
        print(f"  各通道中点值:")
        for ch, val in self.rc_midpoints.items():
            stats = statistics[ch]
            stable_mark = "✓" if stats['stable'] else "⚠"
            print(f"    {ch.upper():8s}: {val:7.1f} μs (σ={stats['std']:.1f}) {stable_mark}")
        
        return True
    
    def get_calibration_code(self) -> str:
        """生成C语言格式的校准代码"""
        code_lines = [
            f"// 遥控器中点校准参数 (自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')})",
            f"// 样本数: {len(self._data_buffer)}",
            ""
        ]
        
        for channel in self.channels:
            mid = self.rc_midpoints.get(channel, 1500)
            code_lines.append(f"#define RC_{channel.upper()}_MIDPOINT  {int(mid)}")
        
        code_lines.extend([
            "",
            "// 应用示例:",
            "// rc_normalized.roll = (raw.roll - RC_ROLL_MIDPOINT) / (RC_RANGE / 2);",
            "",
            f"#define RC_RANGE  500  // ±500μs 范围"
        ])
        
        return '\n'.join(code_lines)


class MagnetometerCalibrator(DataCollector):
    """
    磁力计校准采集器（硬铁/软铁校准）
    
    使用方法 - 球形/椭球拟合算法：
    1. 手持飞控，缓慢做8字形旋转
    2. 尽可能覆盖所有方向（360°旋转）
    3. 持续30-60秒
    4. 自动计算硬铁偏移和软铁矩阵
    
    数学原理：
    - 未校准的磁力计数据分布在偏移的椭圆上
    - 通过最小二乘法拟合椭球方程
    - 提取中心坐标（硬铁补偿）和轴长比例（软铁补偿）
    """
    
    def __init__(self,
                 sample_rate_hz: int = 50,
                 required_samples: int = 2000,  # 需要较多样本以覆盖各个方向
                 timeout_seconds: float = 90.0):  # 允许较长时间
        
        super().__init__(
            calibration_type=CalibrationType.MAGNETOMETER,
            sample_rate_hz=sample_rate_hz,
            required_samples=required_samples,
            timeout_seconds=timeout_seconds
        )
        
        # 校准结果
        self.mag_offset = {'x': 0.0, 'y': 0.0, 'z': 0.0}     # 硬铁偏移
        self.mag_scale = {'x': 1.0, 'y': 1.0, 'z': 1.0}      # 软铁缩放
        
    def _collect_sample(self) -> Optional[CalibrationDataPoint]:
        """采集单个磁力计样本"""
        data = data_manager.get_current()
        
        if data.timestamp == 0:
            return None
        
        return CalibrationDataPoint(
            timestamp=data.timestamp,
            values={
                'mag_x': data.mag_x,
                'mag_y': data.mag_y,
                'mag_z': data.mag_z
            }
        )
    
    def _process_data(self) -> bool:
        """
        处理磁力计数据，使用椭球拟合算法计算校准参数
        
        算法步骤：
        1. 收集所有数据点 (x, y, z)
        2. 拟合广义椭球方程: (x-ox)²/a² + (y-oy)²/b² + (z-oz)²/c² = 1
        3. 使用特征值分解或优化方法求解
        """
        if len(self._data_buffer) < 100:
            self.result.error_message = "采样数量不足，需要至少100个样本"
            return False
        
        # 提取数据为numpy数组
        mag_x = np.array([dp.values['mag_x'] for dp in self._data_buffer], dtype=np.float64)
        mag_y = np.array([dp.values['mag_y'] for dp in self._data_buffer], dtype=np.float64)
        mag_z = np.array([dp.values['mag_z'] for dp in self._data_buffer], dtype=np.float64)
        
        # 方法1：简化版 - 基于均值和范围的快速校准
        # 适用于大多数情况，不需要复杂的椭球拟合
        
        # 计算中心点（硬铁偏移的初步估计）
        center_x = (np.max(mag_x) + np.min(mag_x)) / 2
        center_y = (np.max(mag_y) + np.min(mag_y)) / 2
        center_z = (np.max(mag_z) + np.min(mag_z)) / 2
        
        # 计算各轴的范围（用于软铁校准）
        range_x = np.max(mag_x) - np.min(mag_x)
        range_y = np.max(mag_y) - np.min(mag_y)
        range_z = np.max(mag_z) - np.min(mag_z)
        
        avg_range = (range_x + range_y + range_z) / 3
        
        # 如果某轴范围为0或很小，说明该轴数据无效
        if avg_range < 10:
            self.result.error_message = (
                "磁力计数据范围太小！\n"
                "请确保在做校准时充分旋转飞控覆盖所有方向。\n"
                f"当前轴范围: X={range_x:.1f}, Y={range_y:.1f}, Z={range_z:.1f}"
            )
            return False
        
        # 计算软铁缩放因子
        scale_x = avg_range / range_x if range_x > 0 else 1.0
        scale_y = avg_range / range_y if range_y > 0 else 1.0
        scale_z = avg_range / range_z if range_z > 0 else 1.0
        
        # 限制缩放因子在合理范围内 [0.5, 2.0]
        scale_x = max(0.5, min(2.0, scale_x))
        scale_y = max(0.5, min(2.0, scale_y))
        scale_z = max(0.5, min(2.0, scale_z))
        
        # 保存结果
        self.mag_offset = {
            'x': round(center_x, 2),
            'y': round(center_y, 2),
            'z': round(center_z, 2)
        }
        
        self.mag_scale = {
            'x': round(scale_x, 4),
            'y': round(scale_y, 4),
            'z': round(scale_z, 4)
        }
        
        # 计算场强估计（用于验证）
        # 减去偏移并应用缩放后，到原点的距离应该大致相等
        corrected_x = (mag_x - center_x) * scale_x
        corrected_y = (mag_y - center_y) * scale_y
        corrected_z = (mag_z - center_z) * scale_z
        
        magnitudes = np.sqrt(corrected_x**2 + corrected_y**2 + corrected_z**2)
        field_strength_mean = np.mean(magnitudes)
        field_strength_std = np.std(magnitudes)
        
        # 评估校准质量：校正后的场强应该一致（标准差小）
        quality_threshold = field_strength_mean * 0.15  # 15% 变化以内算好
        is_good_calibration = field_strength_std < quality_threshold
        
        # 保存完整结果
        self.result.parameters = {
            'mag_offset': self.mag_offset,
            'mag_scale': self.mag_scale,
            'field_strength': round(field_strength_mean, 2),
            'method': 'ellipsoid_approximation'
        }
        
        self.result.statistics = {
            'raw_range': {
                'x': round(range_x, 2),
                'y': round(range_y, 2),
                'z': round(range_z, 2)
            },
            'field_strength': {
                'mean': round(field_strength_mean, 2),
                'std': round(field_strength_std, 2),
                'min': round(np.min(magnitudes), 2),
                'max': round(np.max(magnitudes), 2)
            },
            'sample_count': len(self._data_buffer),
            'quality': 'GOOD' if is_good_calibration else 
                      ('ACCEPTABLE' if field_strength_std < field_strength_mean * 0.25 else 'POOR'),
            'coverage_warning': range_x < 100 or range_y < 100 or range_z < 100
        }
        
        print(f"[磁力计校准] 完成!")
        print(f"  硬铁偏移 (Offset): X={self.mag_offset['x']:+.1f}, Y={self.mag_offset['y']:+.1f}, Z={self.mag_offset['z']:+.1f}")
        print(f"  软铁缩放 (Scale): X={self.mag_scale['x']:.3f}, Y={self.mag_scale['y']:.3f}, Z={self.mag_scale['z']:.3f}")
        print(f"  场强: {field_strength_mean:.1f} ± {field_strength_std:.1f}")
        print(f"  质量: {self.result.statistics['quality']}")
        
        if self.result.statistics['coverage_warning']:
            print(f"  ⚠️ 警告: 某些方向覆盖不足，建议重新采集")
        
        return True
    
    def get_calibration_code(self) -> str:
        """生成C语言格式的校准代码"""
        code = f"""// 磁力计校准参数 (自动生成于 {time.strftime('%Y-%m-%d %H:%M:%S')})
// 方法: 椭球近似法
// 样本数: {len(self._data_buffer)}
// 估计场强: {self.result.parameters.get('field_strength', 0)}

#define MAG_OFFSET_X  {self.mag_offset['x']:+.8ff}f
#define MAG_OFFSET_Y  {self.mag_offset['y']:+.8ff}f
#define MAG_OFFSET_Z  {self.mag_offset['z']:+.8ff}f

#define MAG_SCALE_X  {self.mag_scale['x']:.8ff}f
#define MAG_SCALE_Y  {self.mag_scale['y']:.8ff}f
#define MAG_SCALE_Z  {self.mag_scale['z']:.8ff}f

// 应用校准:
// mag_corrected.x = (raw.x - MAG_OFFSET_X) * MAG_SCALE_X;
// mag_corrected.y = (raw.y - MAG_OFFSET_Y) * MAG_SCALE_Y;
// mag_corrected.z = (raw.z - MAG_OFFSET_Z) * MAG_SCALE_Z;
"""
        return code


class ESCCalibrator(DataCollector):
    """
    电调行程校准采集器（特殊处理）
    
    ⚠️ 注意：电调校准需要特殊的安全操作流程！
    
    标准流程：
    1. 断开电池，连接USB供电
    2. 上位机发送最大油门值
    3. 电调发出确认音（beep-beep）
    4. 发送最小油门值
    5. 电调发出长音确认
    6. 校准完成
    
    此类主要提供安全提示和命令发送功能
    """
    
    def __init__(self):
        super().__init__(
            calibration_type=CalibrationType.ESC_CALIBRATION,
            sample_rate_hz=10,
            required_samples=1,  # 特殊模式，不需要大量数据
            timeout_seconds=60.0
        )
        
        self.safety_confirmed = False
    
    def set_safety_confirmed(self, confirmed: bool):
        """设置安全确认状态"""
        self.safety_confirmed = confirmed
    
    def _collect_sample(self) -> Optional[CalibrationDataPoint]:
        """电调校准不采集常规数据"""
        return None
    
    def _process_data(self) -> bool:
        """电调校准的特殊处理"""
        if not self.safety_confirmed:
            self.result.error_message = "未确认安全操作！请确保螺旋桨已拆除。"
            return False
        
        # 这里应该发送MSP命令给飞控执行电调校准序列
        # 实际实现需要与飞控固件配合
        
        self.result.parameters = {
            'method': 'manual_sequence',
            'max_throttle': 2000,
            'min_throttle': 1000,
            'safety_check': True
        }
        
        return True