# -*- coding: utf-8 -*-

from app.constants import (
  SLURM_STATE,
  SLURM_REST_GENERIC_USERNAME,
)

class SlurmJobSummary(object):
    '''
    Base class for metadata derived from querying the Slurm scheduler.
    '''

    def __init__(self, username:str, job_id:int, job_state:str) -> None:
        self.username = username
        self.job_id = job_id
        self.job_state = job_state


    def set_job_state(self, job_state: str) -> None:
        """
        Set the job state of the task job.
        
        Args:
            job_state (str): The new job state to set.
        
        Returns:
            T: The updated task job instance.
        """
        if job_state in SLURM_STATE.keys():
            self.job_state = job_state


    def get_job_state(self) -> str:
        """
        Get the job state of the task job.
        
        Returns:
            str: The current job state of the task job.
        """
        return self.job_state
    

    def set_username(self, username: str) -> None:
        """
        Set the username of the task job.
        
        Args:
            username (str): The new username to set.
        
        Returns:
            T: The updated task job instance.
        """
        self.username = username if username and len(username) > 0 else SLURM_REST_GENERIC_USERNAME


    def get_username(self) -> str:
        """
        Get the username of the task job.
        
        Returns:
            str: The current username of the task job.
        """
        return self.username


    def set_job_id(self, job_id: str) -> None:
        """
        Set the job ID of the task job.
        
        Args:
            job_id (str): The new job ID to set.
        
        Returns:
            T: The updated task job instance.
        """
        self.job_id = job_id


    def get_job_id(self) -> str:
        """
        Get the job ID of the task job.
        
        Returns:
            str: The current job ID of the task job.
        """
        return self.job_id
    

    def to_dict(self) -> dict:
        """
        Convert the task job to a dictionary representation.
        
        Returns:
            dict: Dictionary representation of the task job.
        """
        return {
            "username": self.username,
            "job_id": self.job_id,
            "job_state": self.job_state,
        }
    
    def __repr__(self) -> str:
        """
        String representation of the task job.
        
        Returns:
            str: String representation of the task job.
        """
        return f"SlurmJob(job_id={self.job_id}, job_state={self.job_state}, username={self.username})"
    