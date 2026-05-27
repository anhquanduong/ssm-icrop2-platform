import concurrent.futures
import threading
import logging
import time
from typing import Dict, Any, Callable, Optional
import pandas as pd

logger = logging.getLogger(__name__)

class SimulationTracker:
    """
    Thread-safe progress and state tracker to monitor the asynchronous execution 
    of the SSM-iCrop physiological simulation.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.progress = 0.0          # Progress percentage from 0.0 to 100.0
        self.completed = False
        self.result: Optional[pd.DataFrame] = None
        self.error: Optional[str] = None

    def update_progress(self, current: int, total: int):
        with self.lock:
            if total > 0:
                self.progress = min(100.0, round((current / total) * 100.0, 1))

    def set_result(self, result: pd.DataFrame):
        with self.lock:
            self.result = result
            self.progress = 100.0
            self.completed = True

    def set_error(self, error_msg: str):
        with self.lock:
            self.error = error_msg
            self.completed = True

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "progress": self.progress,
                "completed": self.completed,
                "has_result": self.result is not None,
                "error": self.error
            }

class AsyncSimulationRunner:
    """
    DevOps performance utility utilizing ThreadPoolExecutor to isolate CPU-intensive
    mathematical iterations from the main Streamlit UI thread.
    """
    def __init__(self):
        # Dedicated thread pool for agricultural modeling threads
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def execute_async_simulation(
        self, 
        engine_instance, 
        crop_type: str, 
        pden: float = 8.0, 
        vpdf: float = 1.0
    ) -> SimulationTracker:
        """
        Executes run_simulation asynchronously on a background thread and returns
        a thread-safe state tracker monitoring the loop progress.
        """
        tracker = SimulationTracker()
        
        def job():
            try:
                # Progress callback update hook
                def progress_hook(current, total):
                    tracker.update_progress(current, total)
                    # Tiny micro-sleep lets UI thread catch up and render progress bar increments smoothly
                    time.sleep(0.005)
                
                # Execute engine computational loop in background worker thread
                df_result = engine_instance.run_simulation(
                    crop_type=crop_type,
                    pden=pden,
                    vpdf=vpdf,
                    progress_callback=progress_hook
                )
                tracker.set_result(df_result)
            except Exception as e:
                logger.error(f"Async simulation execution failed: {e}")
                tracker.set_error(str(e))
                
        # Dispatch execution to background worker thread
        self.executor.submit(job)
        return tracker
