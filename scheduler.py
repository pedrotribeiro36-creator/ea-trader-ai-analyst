# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

_scheduler: BackgroundScheduler | None = None

def _job_wrapper(func):
    def inner():
        try:
            func()
        except Exception as e:
            # função passada já faz logs/try-catch
            pass
    return inner

def start_scheduler(run_cycle_callable):
    global _scheduler
    if _scheduler:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    # a cada 10 minutos
    _scheduler.add_job(_job_wrapper(run_cycle_callable), "interval", minutes=10, next_run_time=None, id="market")
    _scheduler.start()

def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None

def get_scheduler_status() -> str:
    if not _scheduler:
        return "⏸️ Scheduler: parado."
    jobs = _scheduler.get_jobs()
    if not jobs:
        return "⏸️ Scheduler: sem jobs."
    j = jobs[0]
    nxt = j.next_run_time.strftime("%Y-%m-%d %H:%M:%S UTC") if j.next_run_time else "N/D"
    return f"🟢 Scheduler ativo.\nPróxima análise: {nxt}\nFrequência: 10 min"
