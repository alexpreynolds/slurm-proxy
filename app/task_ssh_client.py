# -*- coding: utf-8 -*-

import os
import sys
import paramiko
from socket import gaierror
from app.constants import (
            SSH_HOSTNAME,
            SSH_USERNAME,
            SSH_PRIVATE_KEY,
        )
from threading import Lock

class SSHClientConnection:

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(SSHClientConnection, cls).__new__(cls)
                    cls._instance._ssh_client = cls._instance.init_ssh_client()
        return cls._instance


    def get_ssh_client(self) -> paramiko.SSHClient:
        return self._ssh_client


    def init_ssh_client(self) -> paramiko.SSHClient:
        """
        Create an SSH client to connect to the SLURM scheduler.
        This function uses the Paramiko library to create an SSH client
        and sets the missing host key policy to automatically add the host key.

        Returns:
            paramiko.SSHClient: An SSH client object configured to connect to the SLURM scheduler.
        """
        ssh_client = paramiko.SSHClient()
        ssh_client.load_system_host_keys()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return ssh_client
    

    def ssh_client_exec(self, cmd: str) -> tuple:
        """
        Execute a command via SSH. 
        
        The private key for the SSH connection is obtained via the SSH agent.

        This function uses the provided SSH client to execute a command on
        the SLURM scheduler and returns the output and error streams.

        Args:
            ssh_client (paramiko.SSHClient): The SSH client used to connect to the SLURM scheduler.
            cmd (str): The command to be executed on the SLURM scheduler.

        Returns:
            tuple: A tuple containing the output and error streams of the executed command.
        """
        try:
            if not self._ssh_client:
                self._ssh_client = self.init_ssh_client()

            self._ssh_client.connect(
                hostname=SSH_HOSTNAME,
                username=SSH_USERNAME,
                pkey=SSH_PRIVATE_KEY,
                look_for_keys=False,
                allow_agent=False,
                timeout=10,
            )
            return self._ssh_client.exec_command(cmd)
        except gaierror as err:
            print(f" * SSH connection failed: {err}", file=sys.stderr)
            self.report_ssh_environment()
        except paramiko.SSHException as err:
            print(f" * SSH connection failed: {err}", file=sys.stderr)
            self.report_ssh_environment()
        except paramiko.AuthenticationException as err:
            print(f" * SSH authentication failed: {err}", file=sys.stderr)
            self.report_ssh_environment()


    def report_ssh_environment(self):
        print(f" * SSH_HOSTNAME={os.environ.get('SSH_HOSTNAME', SSH_HOSTNAME)}", file=sys.stderr)
        print(f" * SSH_USERNAME={os.environ.get('SSH_USERNAME', SSH_USERNAME)}", file=sys.stderr)
        print(f" * SSH_PRIVATE_KEY={os.environ.get('SSH_PRIVATE_KEY', SSH_PRIVATE_KEY)}", file=sys.stderr)
        print(f" * SSH_AUTH_SOCK={os.environ.get('SSH_AUTH_SOCK')}", file=sys.stderr)

ssh_client_connection_singleton = SSHClientConnection()