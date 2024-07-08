import psutil
import time
import threading
import os
import json
import logging

# Configure logging
logging.basicConfig(filename='server_stats.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

class SystemStatsRecorder:
    def __init__(self, db_interface, interval=1, device_id=2):
        self.device_id = device_id
        self.db = db_interface
        self.interval = interval
        self.running = False
        self.thread = threading.Thread(target=self.record_stats)

    def start(self):
        self.running = True
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()

    def record_stats(self):
        while self.running:
            try:
                stat = {
                    'timestamp': time.time(),
                    'disk_usage': self.get_disk_usage(),
                    'cpu_usage': psutil.cpu_percent(interval=None),
                    'ram_usage': self.get_ram_usage(),
                    'gpu_usage': self.get_gpu_usage()
                }
                self.db.insert_server_stats(stat, self.device_id)
                logging.info(f"Recorded stats: {stat}")
            except Exception as e:
                logging.error(f"Error recording stats: {e}")
            time.sleep(self.interval)

    def get_disk_usage(self):
        disk_usage = {}
        disk_usage['/'] = psutil.disk_usage('/')._asdict()
        for partition in psutil.disk_partitions():
            if partition.mountpoint.startswith('/mnt'):
                disk_usage[partition.mountpoint] = psutil.disk_usage(partition.mountpoint)._asdict()
        return disk_usage

    def get_ram_usage(self):
        mem = psutil.virtual_memory()
        return {'used': mem.used, 'total': mem.total}

    def get_gpu_usage(self):
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            return [{'id': gpu.id, 'load': gpu.load, 'memoryUsed': gpu.memoryUsed, 'memoryTotal': gpu.memoryTotal} for gpu in gpus]
        except ImportError:
            logging.warning('GPUtil not installed')
            return 'GPUtil not installed'