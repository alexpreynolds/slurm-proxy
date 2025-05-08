# -*- coding: utf-8 -*-

from pymongo import MongoClient
from threading import Lock
from app.constants import (
    MONGODB_URI,
    MONGODB_MONITOR_DB,
    MONGODB_TIMEOUT,
)

class MongoDBConnection:

    _instance = None
    _lock = Lock()

    def __new__(cls, 
                uri=MONGODB_URI, 
                database_name=MONGODB_MONITOR_DB, 
                serverSelectionTimeoutMS=MONGODB_TIMEOUT, 
                **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(MongoDBConnection, cls).__new__(cls)
                    cls._instance._client = MongoClient(uri, 
                                                        serverSelectionTimeoutMS=serverSelectionTimeoutMS, 
                                                        **kwargs)
                    cls._instance._monitor_db = cls._instance._client[database_name]
        return cls._instance


    def get_client(self):
        return self._client


    def get_monitor_db(self):
        return self._monitor_db


    def get_monitor_jobs_collection(self):
        return self._monitor_db["jobs"]