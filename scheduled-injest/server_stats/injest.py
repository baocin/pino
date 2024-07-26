import psutil
import time
import threading
import os
import logging
import GPUtil

# Configure logging
logging.basicConfig(filename='server_stats.log', level=logging.INFO, 
                    format='%(asctime)s - server_stats - %(levelname)s - %(message)s')


class SystemStatsRecorder:
    def __init__(self, DB):
        db_instance = DB(
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD")
        )
        self.db = db_instance.connection
        self.device_id = 2 # to tie to an enum later

    def record_stats(self):
        try:
            stat = {
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
                'disk_usage': self.get_disk_usage(),
                'cpu_usage': psutil.cpu_percent(interval=None),
                'ram_usage': self.get_ram_usage(),
                'gpu_usage': self.get_gpu_usage()
            }
            self.insert_server_stats(stat, self.device_id)
            logging.info(f"Recorded stats: {stat}")
        except Exception as e:
            logging.error(f"Error recording stats: {e}")

    def get_disk_usage(self):
        total, used, free = psutil.disk_usage('/').total, psutil.disk_usage('/').used, psutil.disk_usage('/').free
        return (used / total) * 100

    def get_ram_usage(self):
        mem = psutil.virtual_memory()
        return mem.percent

    def get_gpu_usage(self):
        try:
            gpus = GPUtil.getGPUs()
            if gpus:
                return sum(gpu.load for gpu in gpus) / len(gpus) * 100
            else:
                return 0.0
        except ImportError:
            logging.warning('GPUtil not installed')
            return 'GPUtil not installed'

    def insert_server_stats(self, stat, device_id):
        # Assuming a SQL database, construct the SQL query
        sql = """
        INSERT INTO server_stats (timestamp, device_id, disk_usage, cpu_usage, ram_usage, gpu_usage)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        values = (
            stat['timestamp'],
            device_id,
            stat['disk_usage'],
            stat['cpu_usage'],
            stat['ram_usage'],
            stat['gpu_usage']
        )
        # Execute the SQL query using a cursor
        cursor = self.db.cursor()
        cursor.execute(sql, values)
        self.db.commit()
        cursor.close()
