"""
人脸识别模块 - YOLOv8 集成（稳定增强版）
============================
用于香橙派摄像头人脸识别，支持加载预训练 YOLOv8 模型。
增强特性：请求节流、安全 Base64 解码、异常降级、连接健康追踪

部署说明（香橙派）:
1. 安装依赖: pip install ultralytics opencv-python-headless numpy
2. 将训练好的 YOLOv8 人脸模型放到 models/ 目录下
3. 在 config 中配置模型路径和摄像头设备号
4. 模型就绪后自动切换到真实识别模式

模型要求:
- YOLOv8 format (.pt 文件) 或 ONNX format (.onnx 文件)
- 训练数据需包含人脸检测 + 人脸分类/识别
- 输出应包含: 人脸边界框 + 人员ID/标签
"""

import os
import json
import base64
import logging
import numpy as np
from utils import ConnectionHealth, RequestThrottler

logger = logging.getLogger(__name__)

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'face_config.json')

# 默认配置
DEFAULT_CONFIG = {
    # YOLOv8 模型配置
    "model_path": "models/face_yolov8.pt",       # 预训练模型路径
    "model_format": "pt",                         # pt / onnx
    "confidence_threshold": 0.6,                   # 置信度阈值
    "iou_threshold": 0.45,                         # NMS IOU阈值

    # 摄像头配置（香橙派）
    "camera_device": 0,                           # 摄像头设备号 (0 = /dev/video0)
    "camera_width": 640,
    "camera_height": 480,
    "camera_fps": 15,

    # 识别配置
    "max_faces": 5,                                # 单帧最大检测人脸数
    "recognition_interval": 2.0,                   # 识别间隔（秒）
    "face_db_path": "models/face_db.json",         # 人脸数据库（已知人脸特征）

    # 模拟模式（无模型时的回退）
    "simulation_mode": True,                      # True=模拟模式, False=真实YOLOv8识别
    "known_faces": {
        "FACE001": "管理员",
        "FACE002": "家庭成员A",
        "FACE003": "家庭成员B"
    }
}


class FaceRecognition:
    """YOLOv8 人脸识别引擎（稳定增强版）"""

    def __init__(self, config_path=None):
        self.config = self._load_config(config_path)
        self.model = None
        self.simulation_mode = self.config.get('simulation_mode', True)
        self._model_loaded = False
        # 请求节流器（防止请求堆积）
        self.throttler = RequestThrottler(min_interval=1.5)
        # 连接健康状态
        self.health = ConnectionHealth("FaceRecognition")

        # 如果非模拟模式，尝试加载模型
        if not self.simulation_mode:
            self._load_model()

    def _load_config(self, config_path=None):
        """加载配置文件"""
        path = config_path or CONFIG_PATH
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"配置文件加载失败: {e}，使用默认配置")
        return DEFAULT_CONFIG.copy()

    def save_config(self, config):
        """保存配置"""
        path = CONFIG_PATH
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        self.config = config

    def _load_model(self):
        """加载 YOLOv8 预训练模型"""
        model_path = self.config.get('model_path', '')

        if not os.path.exists(model_path):
            logger.warning(f"模型文件不存在: {model_path}，切换到模拟模式")
            self.simulation_mode = True
            return False

        try:
            from ultralytics import YOLO

            model_format = self.config.get('model_format', 'pt')
            if model_format == 'onnx':
                self.model = YOLO(model_path, task='detect')
            else:
                self.model = YOLO(model_path)

            self._model_loaded = True
            self.simulation_mode = False
            logger.info(f"YOLOv8 模型加载成功: {model_path}")
            return True

        except ImportError:
            logger.warning("ultralytics 未安装，切换到模拟模式。安装: pip install ultralytics")
            self.simulation_mode = True
            return False
        except Exception as e:
            logger.error(f"模型加载失败: {e}，切换到模拟模式")
            self.simulation_mode = True
            return False

    def recognize_from_base64(self, image_base64):
        """
        从 Base64 编码的图像中识别人脸（带请求节流）

        Args:
            image_base64: Base64编码的JPEG图像（可能含 data:image/jpeg;base64, 前缀）

        Returns:
            dict: {
                'detected': bool,           # 是否检测到人脸
                'face_id': str or None,      # 识别出的人脸ID
                'confidence': float,         # 置信度
                'faces': list,               # 检测到的所有人脸信息
                'mode': str                  # 'yolov8' or 'simulation'
            }
        """
        # 请求节流检查
        if not self.throttler.can_execute():
            wait_time = self.throttler.time_until_next()
            return {
                'detected': False,
                'face_id': None,
                'confidence': 0,
                'faces': [],
                'mode': 'throttled',
                'message': f'请求过于频繁，请等待 {wait_time:.1f} 秒后再试'
            }

        if self.simulation_mode:
            result = self._simulate_recognition()
            if result['detected']:
                self.health.record_success()
            return result

        # 真实 YOLOv8 识别
        return self._yolov8_recognize(image_base64)

    def recognize_from_frame(self, frame):
        """
        从 numpy 数组（OpenCV 帧）中识别人脸（带请求节流）

        Args:
            frame: numpy数组 (H, W, 3) BGR格式

        Returns:
            dict: 同 recognize_from_base64
        """
        # 请求节流检查
        if not self.throttler.can_execute():
            wait_time = self.throttler.time_until_next()
            return {
                'detected': False,
                'face_id': None,
                'confidence': 0,
                'faces': [],
                'mode': 'throttled',
                'message': f'请求过于频繁，请等待 {wait_time:.1f} 秒后再试'
            }

        if self.simulation_mode:
            result = self._simulate_recognition()
            if result['detected']:
                self.health.record_success()
            return result

        return self._yolov8_recognize_frame(frame)

    def _yolov8_recognize(self, image_base64):
        """YOLOv8 真实识别（Base64输入）"""
        try:
            import cv2
            import numpy as np

            # Base64 解码为图像（去掉前缀）
            if ',' in image_base64:
                image_base64 = image_base64.split(',')[1]

            img_data = base64.b64decode(image_base64)
            img_array = np.frombuffer(img_data, dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if frame is None:
                logger.warning("Failed to decode image from base64")
                return self._empty_result('yolov8')

            result = self._yolov8_recognize_frame(frame)
            if result['detected']:
                self.health.record_success()
            return result

        except Exception as e:
            logger.error(f"YOLOv8 识别失败: {e}")
            self.health.record_failure(str(e))
            return self._empty_result('yolov8', error=str(e))

    def _yolov8_recognize_frame(self, frame):
        """YOLOv8 真实识别（帧输入）"""
        try:
            conf_thresh = self.config.get('confidence_threshold', 0.6)
            iou_thresh = self.config.get('iou_threshold', 0.45)
            max_faces = self.config.get('max_faces', 5)

            # YOLOv8 推理
            results = self.model(
                frame,
                conf=conf_thresh,
                iou=iou_thresh,
                max_det=max_faces,
                verbose=False
            )

            faces = []
            best_face = None
            best_conf = 0

            for result in results:
                boxes = result.boxes
                if boxes is None:
                    continue

                for box in boxes:
                    conf = float(box.conf[0])
                    cls_id = int(box.cls[0])
                    xyxy = box.xyxy[0].tolist()

                    # 获取模型类别名称作为 face_id
                    class_names = self.model.names
                    class_name = class_names.get(cls_id, f'unknown_{cls_id}')

                    face_info = {
                        'face_id': class_name,
                        'confidence': round(conf, 3),
                        'bbox': {
                            'x1': round(xyxy[0], 1),
                            'y1': round(xyxy[1], 1),
                            'x2': round(xyxy[2], 1),
                            'y2': round(xyxy[3], 1)
                        }
                    }
                    faces.append(face_info)

                    # 保留置信度最高的人脸
                    if conf > best_conf:
                        best_conf = conf
                        best_face = face_info

            if best_face:
                self.health.record_success()
                return {
                    'detected': True,
                    'face_id': best_face['face_id'],
                    'confidence': best_face['confidence'],
                    'faces': faces,
                    'mode': 'yolov8'
                }

            return {
                'detected': False,
                'face_id': None,
                'confidence': 0,
                'faces': faces,
                'mode': 'yolov8'
            }

        except Exception as e:
            logger.error(f"YOLOv8 帧识别失败: {e}")
            self.health.record_failure(str(e))
            return self._empty_result('yolov8', error=str(e))

    def _simulate_recognition(self):
        """模拟人脸识别（无模型时的回退模式）"""
        import random
        known_faces = self.config.get('known_faces', DEFAULT_CONFIG['known_faces'])
        face_ids = list(known_faces.keys())

        # 70% 概率识别到已知人脸，30% 概率未识别到人脸
        if random.random() < 0.7:
            face_id = random.choice(face_ids)
            conf = round(random.uniform(0.75, 0.99), 3)
            return {
                'detected': True,
                'face_id': face_id,
                'confidence': conf,
                'faces': [{
                    'face_id': face_id,
                    'confidence': conf,
                    'bbox': {
                        'x1': round(random.uniform(150, 250), 1),
                        'y1': round(random.uniform(50, 150), 1),
                        'x2': round(random.uniform(400, 500), 1),
                        'y2': round(random.uniform(350, 450), 1)
                    }
                }],
                'mode': 'simulation'
            }
        else:
            return {
                'detected': False,
                'face_id': None,
                'confidence': 0,
                'faces': [],
                'mode': 'simulation'
            }

    def _empty_result(self, mode, error=None):
        """返回空结果"""
        result = {
            'detected': False,
            'face_id': None,
            'confidence': 0,
            'faces': [],
            'mode': mode
        }
        if error:
            result['error'] = error
        return result

    def get_status(self):
        """获取识别引擎状态"""
        status = {
            'model_loaded': self._model_loaded,
            'simulation_mode': self.simulation_mode,
            'mode': 'simulation' if self.simulation_mode else 'yolov8',
            'model_path': self.config.get('model_path', ''),
            'confidence_threshold': self.config.get('confidence_threshold', 0.6),
            'camera_device': self.config.get('camera_device', 0),
            'known_faces': self.config.get('known_faces', {})
        }
        status.update(self.health.get_status())
        return status

    def add_known_face(self, face_id, name):
        """添加已知人脸到数据库"""
        known = self.config.get('known_faces', {})
        known[face_id] = name
        self.config['known_faces'] = known
        self.save_config(self.config)
        return True

    def remove_known_face(self, face_id):
        """移除已知人脸"""
        known = self.config.get('known_faces', {})
        if face_id in known:
            del known[face_id]
            self.config['known_faces'] = known
            self.save_config(self.config)
            return True
        return False

    def reload_model(self):
        """重新加载模型"""
        self.simulation_mode = self.config.get('simulation_mode', True)
        if not self.simulation_mode:
            return self._load_model()
        return False


# 全局人脸识别实例
face_engine = FaceRecognition()
