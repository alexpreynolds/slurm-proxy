# -*- coding: utf-8 -*-

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

from app.task_submission import task_submission
from app.task_monitoring import task_monitoring, poll_slurm_jobs
from app.task_slurm_rest import task_slurm_rest
from app.constants import (
    APP_NAME,
    APP_PORT,
    MONITOR_POLLING_INTERVAL,
)
from app.helpers import (
    init_mongodb,
)

def create_app():    
    app = Flask(APP_NAME)
    app.register_blueprint(task_submission, url_prefix="/submit")
    app.register_blueprint(task_monitoring, url_prefix="/monitor")
    app.register_blueprint(task_slurm_rest, url_prefix="/slurm")

    @app.route("/ping")
    def ping():
        return "pong"

    print(f" * Starting {APP_NAME} on port {APP_PORT}")
    init_mongodb()
    scheduler = BackgroundScheduler()
    poll_scheduler = scheduler.add_job(
        poll_slurm_jobs,
        "interval",
        minutes=int(MONITOR_POLLING_INTERVAL),
    )
    scheduler.start()

    return app
