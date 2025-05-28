# -*- coding: utf-8 -*-

from app.task_metadata_slurm_job_summary import SlurmJobSummary
from app.task_metadata_monitor_job_summary import MonitorJobSummary

class JobSummary(object):

    def __init__(self, slurm_summary: SlurmJobSummary, monitor_summary: MonitorJobSummary) -> None:
        """
        Initialize a JobSummary instance with Slurm and Monitor summary metadata.

        Args:
            slurm_summary (SlurmJobSummary): The Slurm metadata for the job.
            monitor_summary (MonitorJobSummary): The Monitor metadata for the job.
        """
        self.slurm = slurm_summary
        self.monitor = monitor_summary


    def to_dict(self) -> dict:
        """
        Convert the JobSummary instance to a dictionary representation.

        Returns:
            dict: Dictionary representation of the job.
        """
        return {
            "slurm": self.slurm.to_dict(),
            "monitor": self.monitor.to_dict(),
        }
    
    def __repr__(self) -> str:
        """
        String representation of the JobSummary instance.
        
        Returns:
            str: String representation of the job.
        """
        return f"JobSummary(slurm_md={self.slurm}, monitor_md={self.monitor})"