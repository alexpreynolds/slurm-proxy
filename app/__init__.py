# -*- coding: utf-8 -*-

import os
# import logging
# import logging.config
from flask import Flask
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

from app.task_submission import task_submission
from app.task_monitoring import task_monitoring, poll_slurm_jobs
from app.task_slurm_rest import task_slurm_rest
from app.constants import (
    APP_NAME,
    MONITOR_POLLING_INTERVAL,
)
from app.helpers import (
    ping_mongodb_client,
)

def create_app():
    """
    If there is a valid key for generating Slurm authentication tokens, 
    create a Flask application instance and configure it. This function 
    initializes the Flask application, registers blueprints, and sets up
    the MongoDB connection. It also initializes the background scheduler
    for polling SLURM jobs.
    """
    dotenv_path = os.environ.get("DOTENV_FILE", os.path.join(os.path.dirname(__file__), '.env'))
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)

    slurm_private_key = os.environ.get("SLURM_JWT_HS256_KEY_BASE64")
    if not slurm_private_key:
        raise ValueError("SLURM_JWT_HS256_KEY_BASE64 environment variable not set")

    app = Flask(APP_NAME)

    # app.config.from_object('app.config.Config')
    # logging.config.dictConfig(app.config['LOGGING_CONFIG'])

    app.register_blueprint(task_submission, url_prefix="/submit")
    app.register_blueprint(task_monitoring, url_prefix="/monitor")
    app.register_blueprint(task_slurm_rest, url_prefix="/slurm")

    @app.route("/ping")
    def ping():
        return "pong"
    
    with app.app_context():
        ping_mongodb_client()
        scheduler = BackgroundScheduler()
        poll_scheduler = scheduler.add_job(
            poll_slurm_jobs,
            "interval",
            minutes=int(MONITOR_POLLING_INTERVAL),
            id="poll_slurm_jobs",
        )
        scheduler.start()

    return app
