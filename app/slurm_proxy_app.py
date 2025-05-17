import os
import logging
from flask import Flask
from dotenv import load_dotenv
from logging.config import dictConfig
from apscheduler.schedulers.background import BackgroundScheduler

from app import constants
from app.task_submission import task_submission
from app.task_monitoring import task_monitoring, poll_slurm_jobs
from app.task_slurm_rest import task_slurm_rest
from app.helpers import ping_mongodb_client

'''
This module defines the SlurmProxyApp class, which is a singleton Flask application
'''

class SlurmProxyApp(Flask):
    _app = None

    def __init__(self):
        raise Error('call SlurmProxyApp()')

    @classmethod
    def app(cls):
        if cls._app is None:
            cls._app = Flask(constants.APP_NAME)

            dotenv_path = os.environ.get(
                "DOTENV_FILE", os.path.join(os.path.dirname(__file__), ".env")
            )
            if os.path.exists(dotenv_path):
                load_dotenv(dotenv_path)

            slurm_private_key = os.environ.get("SLURM_JWT_HS256_KEY_BASE64")
            if not slurm_private_key:
                raise ValueError("SLURM_JWT_HS256_KEY_BASE64 environment variable not set")

            cls._app.config.from_object("app.config.Config")
            logging.config.dictConfig(cls._app.config["LOGGING_CONFIG"])
            logging.getLogger("apscheduler").setLevel(logging.WARNING)

            cls._app.register_blueprint(task_submission, url_prefix="/submit")
            cls._app.register_blueprint(task_monitoring, url_prefix="/monitor")
            cls._app.register_blueprint(task_slurm_rest, url_prefix="/slurm")

            @cls._app.route("/ping")
            def ping():
                cls._app.logger.info(f"ping > pong")
                return "pong"

            with cls._app.app_context():
                ping_mongodb_client()
                scheduler = BackgroundScheduler()
                poll_scheduler = scheduler.add_job(
                    poll_slurm_jobs,
                    "interval",
                    minutes=int(constants.MONITOR_POLLING_INTERVAL),
                    id="poll_slurm_jobs",
                    replace_existing=True,
                    max_instances=1,
                    misfire_grace_time=60,
                )
                scheduler.start()
                cls._app.logger.info("Application started and scheduler initialized!")

        return cls._app

app = SlurmProxyApp.app()