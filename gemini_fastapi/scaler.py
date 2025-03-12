import os
import time
import signal
import subprocess
import uuid
from celery import Celery
from redis import Redis
from redis.exceptions import RedisError
import logging
from dataclasses import dataclass
from typing import Optional
import atexit
import threading
from datetime import datetime, timedelta
import socket

@dataclass
class ScalingConfig:
    min_workers: int = 3
    max_workers: int = 50
    tasks_per_worker: int = 1
    check_interval: int = 10  # seconds
    scale_up_threshold: float = 0.8  # Scale up when worker utilization > 80%
    scale_down_threshold: float = 0.3  # Scale down when worker utilization < 30%
    cooldown_period: int = 60  # seconds between scaling operations
    worker_startup_time: int = 30  # seconds to wait for worker to start
    worker_prefix: str = "celery_worker"

class CeleryScaler:
    def __init__(self, 
                 redis_url: str = 'redis://redis:6379/0',
                 celery_app_name: str = 'tasks',
                 config: Optional[ScalingConfig] = None):
        # Configure logging
        self.setup_logging()
        
        # Initialize configuration
        self.config = config or ScalingConfig()
        
        # Connect to Redis and Celery
        self.redis_conn = Redis.from_url(redis_url, decode_responses=True)
        self.celery_app = Celery(celery_app_name, broker=redis_url)
        
        # State tracking
        self.last_scale_time = datetime.now() - timedelta(seconds=self.config.cooldown_period)
        self.running = False
        self.worker_processes = {}  # Dictionary to store processes with their unique IDs
        self.lock = threading.Lock()
        
        # Register cleanup handlers
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self.handle_sigterm)
        signal.signal(signal.SIGINT, self.handle_sigterm)

    def setup_logging(self):
        """Configure logging with rotation and proper formatting."""
        self.logger = logging.getLogger("celery_scaler")
        self.logger.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            'celery_scaler.log',
            maxBytes=10485760,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def generate_worker_name(self) -> str:
        """Generate a unique name for each worker."""
        unique_id = str(uuid.uuid4())[:8]
        hostname = socket.gethostname()
        return f"{self.config.worker_prefix}_{hostname}_{unique_id}"

    def get_queue_length(self, queue_name: str = "celery") -> int:
        """Get the number of tasks in the specified queue with error handling."""
        try:
            return int(self.redis_conn.llen(queue_name))
        except RedisError as e:
            self.logger.error(f"Redis error while getting queue length: {e}")
            return 0
        except Exception as e:
            self.logger.error(f"Unexpected error while getting queue length: {e}")
            return 0

    def get_active_workers(self) -> int:
        """Get number of currently active Celery workers with improved accuracy."""
        try:
            # Use celery inspect to get actual running workers
            i = self.celery_app.control.inspect()
            active_workers = i.active()
            if active_workers is None:
                return len(self.worker_processes)
            return len(active_workers)
        except Exception as e:
            self.logger.error(f"Failed to get active workers count: {e}")
            # Fallback to process counting
            return len(self.worker_processes)

    def should_scale(self, desired_workers: int, current_workers: int) -> bool:
        """Determine if scaling should occur based on cooldown and thresholds."""
        if (datetime.now() - self.last_scale_time).seconds < self.config.cooldown_period:
            return False
        
        # Prevent rapid scaling
        worker_difference = abs(desired_workers - current_workers)
        return worker_difference >= max(2, int(current_workers * 0.2))

    def scale_workers(self, queue_length: int):
        """Scale workers based on queue length with safety checks."""
        with self.lock:
            current_workers = self.get_active_workers()
            desired_workers = max(
                self.config.min_workers,
                min(self.config.max_workers,
                    (queue_length // self.config.tasks_per_worker) + 1)
            )

            if not self.should_scale(desired_workers, current_workers):
                return

            if current_workers < desired_workers:
                self.scale_up(desired_workers - current_workers)
            elif current_workers > desired_workers:
                self.scale_down(current_workers - desired_workers)

    def scale_up(self, count: int):
        """Scale up the number of Celery workers with process tracking."""
        self.logger.info(f"Scaling up by {count} workers")
        try:
            for _ in range(count):
                worker_name = self.generate_worker_name()
                process = subprocess.Popen(
                    ["celery", "-A", self.celery_app.main, "worker",
                     "--loglevel=info", "--concurrency=1",
                     "-n", worker_name],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                self.worker_processes[worker_name] = process
            
            self.last_scale_time = datetime.now()
            # Wait briefly to ensure workers are starting up
            time.sleep(min(2, self.config.worker_startup_time // count))
            
        except Exception as e:
            self.logger.error(f"Failed to scale up workers: {e}")

    def scale_down(self, count: int):
        """Scale down workers gracefully with process tracking."""
        self.logger.info(f"Scaling down by {count} workers")
        try:
            workers_to_remove = list(self.worker_processes.items())[:count]
            
            for worker_name, process in workers_to_remove:
                # Send SIGTERM for graceful shutdown
                process.terminate()
                
                # Wait briefly for graceful shutdown
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if graceful shutdown fails
                    process.kill()
                
                del self.worker_processes[worker_name]
            
            self.last_scale_time = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Failed to scale down workers: {e}")

    def cleanup(self):
        """Cleanup resources and shut down workers gracefully."""
        self.logger.info("Cleaning up resources...")
        self.running = False
        
        # Gracefully shutdown all workers
        for worker_name, process in self.worker_processes.items():
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                process.kill()

    def handle_sigterm(self, signum, frame):
        """Handle termination signals gracefully."""
        self.logger.info(f"Received signal {signum}")
        self.cleanup()
        exit(0)

    def run(self):
        """Main loop with improved error handling and monitoring."""
        self.logger.info("Starting Celery auto-scaler...")
        self.running = True
        
        while self.running:
            try:
                queue_length = self.get_queue_length()
                current_workers = self.get_active_workers()
                
                self.logger.info(
                    f"Status - Queue: {queue_length}, Workers: {current_workers}"
                )
                
                self.scale_workers(queue_length)
                
                # Health check
                if current_workers < self.config.min_workers:
                    self.logger.warning(
                        f"Worker count ({current_workers}) below minimum "
                        f"threshold ({self.config.min_workers})"
                    )
                    self.scale_up(self.config.min_workers - current_workers)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}")
            
            time.sleep(self.config.check_interval)

if __name__ == "__main__":
    # Example usage with custom configuration
    config = ScalingConfig(
        min_workers=int(os.getenv('MIN_WORKERS', '3')),
        max_workers=int(os.getenv('MAX_WORKERS', '50')),
        tasks_per_worker=int(os.getenv('TASKS_PER_WORKER', '1')),
        check_interval=int(os.getenv('CHECK_INTERVAL', '10')),
        scale_up_threshold=float(os.getenv('SCALE_UP_THRESHOLD', '0.8')),
        scale_down_threshold=float(os.getenv('SCALE_DOWN_THRESHOLD', '0.3')),
        cooldown_period=int(os.getenv('COOLDOWN_PERIOD', '60')),
        worker_startup_time=int(os.getenv('WORKER_STARTUP_TIME', '30')),
        worker_prefix=os.getenv('WORKER_PREFIX', 'celery_worker')
    )
    
    scaler = CeleryScaler(
        redis_url=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
        celery_app_name=os.getenv('CELERY_APP_NAME', 'tasks'),
        config=config
    )
    
    scaler.run()