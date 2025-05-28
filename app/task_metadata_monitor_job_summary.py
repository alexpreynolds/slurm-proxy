# -*- coding: utf-8 -*-

from typing import Any
from app.helpers import get_current_datetime

class MonitorJobSummary(object):
    '''
    Base class for monitor job object data. This is the object entered into 
    the database when a task is monitored, and when it is updated, such as 
    when the job completion status changes. Slurm job metadata is stored with
    the task metadata, and this object is used to track the job's state and
    other relevant information where it differs from the Slurm scheduler.
    '''

    def __init__(self, slurm_username:str, slurm_job_id:int, slurm_job_state:str, task:dict) -> None:
        self.slurm_username = slurm_username
        self.slurm_job_id = slurm_job_id
        self.slurm_job_state = slurm_job_state
        self.task = task
        self.created_at = get_current_datetime()
        self.updated_at = None
    

    def get_slurm_job_id(self) -> int:
        """
        Get the Slurm job ID of the monitor job.
        
        Returns:
            int: The Slurm job ID.
        """
        return self.slurm_job_id
    
    
    def get_slurm_job_state(self) -> str:
        """
        Get the Slurm job state of the monitor job.
        
        Returns:
            str: The Slurm job state.
        """
        return self.slurm_job_state
    

    def get_slurm_username(self) -> str:
        """
        Get the Slurm username of the monitor job.
        Returns:
            str: The Slurm username.
        """
        return self.slurm_username
    

    def get_task(self) -> dict:
        """
        Get the task associated with the monitor job.
        
        Returns:
            dict: The task object associated with the monitor job.
        """
        return self.task
    

    def get_created_at(self) -> str:
        """
        Get the creation timestamp of the monitor job.
        
        Returns:
            str: The creation timestamp in ISO format.
        """
        return self.created_at.isoformat()
    

    def get_updated_at(self) -> str:
        """
        Get the last updated timestamp of the monitor job.
        
        Returns:
            str: The last updated timestamp in ISO
            format, or None if not updated.
        """
        return self.updated_at.isoformat() if self.updated_at else None
    

    def update(self, **kwargs) -> Any:
        """
        Update the monitor job object with new parameters.
        
        Args:
            **kwargs: Keyword arguments to update the monitor job object.
        """
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.updated_at = get_current_datetime()
        return self
    

    def to_dict(self) -> dict:
        """
        Convert the monitor job to a dictionary representation.
        
        Returns:
            dict: Dictionary representation of the monitor job object.
        """
        return {
            "slurm_username": self.slurm_username,
            "slurm_job_id": self.slurm_job_id,
            "slurm_job_state": self.slurm_job_state,
            "task": self.task,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self) -> str:
        """
        String representation of the monitor job object.
        
        Returns:
            str: String representation of the monitor job object.
        """
        return f"MonitorJob(slurm_job_id={self.slurm_job_id}, slurm_job_state={self.slurm_job_state}, slurm_username={self.slurm_username}, task_uuid={self.task.uuid}, created_at={self.created_at.isoformat()}, updated_at={self.updated_at.isoformat() if self.updated_at else None})"
    