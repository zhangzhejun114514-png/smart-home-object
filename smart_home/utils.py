"""
通用工具模块 - 稳定性增强
===========================
提供：异常处理装饰器、重试机制、超时控制、请求节流
"""

import functools
import time
import logging
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError

logger = logging.getLogger(__name__)


# ==================== API 异常处理装饰器 ====================

def api_error_handler(func):
    """Flask API 路由全局异常处理装饰器
    
    捕获所有未处理异常，返回标准化错误响应，
    防止 Flask 返回 500 错误页面导致前端卡死。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            func_name = getattr(func, '__name__', 'unknown')
            logger.error(f"API error in {func_name}: {e}", exc_info=True)
            from flask import jsonify
            return jsonify({
                'error': '服务器内部错误',
                'error_en': 'Internal server error',
                'detail': str(e) if app_debug() else None
            }), 500
    return wrapper


def app_debug():
    """检查 Flask 是否处于 debug 模式"""
    try:
        from flask import current_app
        return current_app.debug
    except Exception:
        return False


# ==================== 重试装饰器（指数退避） ====================

def retry_with_backoff(max_retries=3, base_delay=0.5, max_delay=8.0,
                       exceptions=(Exception,), on_retry=None):
    """指数退避重试装饰器
    
    Args:
        max_retries: 最大重试次数
        base_delay: 初始延迟（秒）
        max_delay: 最大延迟（秒）
        exceptions: 需要重试的异常类型
        on_retry: 每次重试时的回调函数 (attempt, delay, exception)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt >= max_retries:
                        raise
                    # 指数退避: delay = base_delay * 2^attempt，上限 max_delay
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    if on_retry:
                        on_retry(attempt + 1, delay, e)
                    logger.warning(f"Retry {attempt+1}/{max_retries} for {func.__name__} after {delay:.1f}s: {e}")
                    time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


# ==================== 请求节流器 ====================

class RequestThrottler:
    """请求节流器 - 防止短时间内重复请求
    
    用于人脸识别等高频请求场景，避免请求堆积。
    """
    def __init__(self, min_interval=2.0):
        self.min_interval = min_interval
        self._last_request_time = 0
        self._lock = threading.Lock()
    
    def can_execute(self):
        """检查是否可以执行请求"""
        with self._lock:
            now = time.time()
            if now - self._last_request_time >= self.min_interval:
                self._last_request_time = now
                return True
            return False
    
    def time_until_next(self):
        """距离下次可执行的时间（秒）"""
        with self._lock:
            elapsed = time.time() - self._last_request_time
            return max(0, self.min_interval - elapsed)


# ==================== 安全 Base64 解码 ====================

def safe_base64_decode(image_base64, max_size_mb=5):
    """安全解码 Base64 图片，防止内存攻击
    
    Args:
        image_base64: Base64 编码的图像数据
        max_size_mb: 最大允许大小（MB）
    
    Returns:
        bytes: 解码后的二进制数据
    
    Raises:
        ValueError: 数据过大或格式错误
    """
    import base64
    
    # 去掉前缀
    if ',' in image_base64:
        image_base64 = image_base64.split(',')[1]
    
    # Base64 编码后大小约为原始数据的 4/3
    # 所以编码后大小限制 = max_size_mb * 1024 * 1024 * 4/3
    max_encoded_len = int(max_size_mb * 1024 * 1024 * 4 / 3)
    
    if len(image_base64) > max_encoded_len:
        raise ValueError(f"Image too large: {len(image_base64)} chars exceeds limit")
    
    try:
        return base64.b64decode(image_base64)
    except Exception as e:
        raise ValueError(f"Invalid base64 data: {e}")


# ==================== 连接状态管理 ====================

class ConnectionHealth:
    """连接健康状态管理器
    
    跟踪外部服务（HA、摄像头等）的连接状态，
    提供健康检查和自动恢复逻辑。
    """
    def __init__(self, name="service"):
        self.name = name
        self.connected = False
        self.last_success = None
        self.last_failure = None
        self.failure_count = 0
        self.consecutive_failures = 0
        self._lock = threading.Lock()
    
    def record_success(self):
        """记录一次成功连接"""
        with self._lock:
            self.connected = True
            self.last_success = time.time()
            self.consecutive_failures = 0
            if self.failure_count > 0:
                logger.info(f"{self.name} connection recovered after {self.failure_count} failures")
            self.failure_count = 0
    
    def record_failure(self, error=None):
        """记录一次连接失败"""
        with self._lock:
            self.connected = False
            self.last_failure = time.time()
            self.consecutive_failures += 1
            self.failure_count += 1
            if self.consecutive_failures <= 3 or self.consecutive_failures % 10 == 0:
                logger.warning(f"{self.name} connection failed ({self.consecutive_failures}x): {error}")
    
    def is_healthy(self, max_failures=5):
        """检查连接是否健康"""
        with self._lock:
            return self.connected or self.consecutive_failures < max_failures
    
    def get_status(self):
        """获取健康状态摘要"""
        with self._lock:
            return {
                'connected': self.connected,
                'consecutive_failures': self.consecutive_failures,
                'total_failures': self.failure_count,
                'last_success': self.last_success,
                'last_failure': self.last_failure,
                'is_healthy': self.is_healthy()
            }
