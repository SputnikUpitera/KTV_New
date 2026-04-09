"""
SSH/SFTP Client for remote Linux system communication
"""

import paramiko
import socket
import logging
import json
from pathlib import Path
from typing import Optional, Callable, Tuple, Dict, Any

logger = logging.getLogger(__name__)


class SSHClient:
    """SSH/SFTP client for communicating with remote Linux system"""
    
    def __init__(self):
        self.client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self.connected = False
        self.host = None
        self.port = None
        self.username = None
        self.password = None  # Store password for sudo operations
        self.remote_home: Optional[str] = None
        self.remote_daemon_config: Optional[Dict[str, Any]] = None
    
    def connect(self, host: str, port: int = 22, username: str = None, 
                password: str = None, key_file: str = None, timeout: int = 30) -> Tuple[bool, str]:
        """
        Connect to remote SSH server
        
        Args:
            host: IP address or hostname
            port: SSH port (default 22)
            username: Username for authentication
            password: Password for authentication
            key_file: Path to private key file
            timeout: Connection timeout in seconds
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            logger.info(f"Attempting SSH connection to {host}:{port} as {username}")
            logger.debug(f"Connection timeout: {timeout}s, banner_timeout: {timeout}s")
            
            # Prepare connection kwargs
            connect_kwargs = {
                'hostname': host,
                'port': port,
                'username': username,
                'timeout': timeout,
                'banner_timeout': timeout,
                'auth_timeout': timeout,
                'look_for_keys': False,  # Don't look for system keys
                'allow_agent': False,    # Don't use SSH agent
                'disabled_algorithms': {}  # Don't disable any algorithms
            }
            
            if key_file:
                logger.debug(f"Using key file: {key_file}")
                connect_kwargs['key_filename'] = key_file
            elif password:
                logger.debug("Using password authentication")
                connect_kwargs['password'] = password
            else:
                error = "Either password or key_file must be provided"
                logger.error(error)
                return False, error
            
            # Connect
            logger.debug(f"Initiating SSH connection...")
            self.client.connect(**connect_kwargs)
            logger.debug("SSH connection established")
            
            # Open SFTP session
            logger.debug("Opening SFTP session...")
            self.sftp = self.client.open_sftp()
            logger.debug("SFTP session opened")
            
            self.connected = True
            self.host = host
            self.port = port
            self.username = username
            self.password = password  # Store password for sudo operations
            self.remote_home = None
            self.remote_daemon_config = None
            
            logger.info(f"Successfully connected to {host}:{port}")
            return True, ""
            
        except paramiko.AuthenticationException as e:
            error = f"Authentication failed: {str(e)}"
            logger.error(error)
            logger.debug(f"Auth exception details: {e.__class__.__name__}", exc_info=True)
            return False, error
        except paramiko.SSHException as e:
            error = f"SSH error: {str(e)}"
            logger.error(error)
            logger.debug(f"SSH exception details: {e.__class__.__name__}", exc_info=True)
            
            # Provide more specific error messages
            error_str = str(e).lower()
            if 'banner' in error_str or 'protocol' in error_str:
                error = (f"SSH protocol error: {str(e)}\n\n"
                        f"Возможные причины:\n"
                        f"1. SSH сервер не полностью запущен\n"
                        f"2. SSH сервер перегружен\n"
                        f"3. Проблема с TCP Wrappers (/etc/hosts.allow)\n"
                        f"4. Несовместимая версия SSH\n\n"
                        f"Попробуйте:\n"
                        f"- Перезапустить SSH: sudo systemctl restart ssh\n"
                        f"- Проверить логи: sudo journalctl -u ssh -n 50\n"
                        f"- Проверить конфиг: sudo sshd -t")
            elif 'timeout' in error_str:
                error = f"SSH timeout: {str(e)}\nСервер не отвечает в течение {timeout} секунд"
            elif 'kex' in error_str or 'exchange' in error_str:
                error = (f"Key exchange error: {str(e)}\n\n"
                        f"SSH сервер закрыл соединение во время handshake.\n\n"
                        f"Попробуйте на Linux:\n"
                        f"1. sudo systemctl restart ssh\n"
                        f"2. sudo journalctl -u ssh -n 50\n"
                        f"3. Проверьте /etc/hosts.allow: echo 'sshd: ALL' | sudo tee -a /etc/hosts.allow")
            
            return False, error
        except socket.timeout as e:
            error = f"Connection timeout after {timeout}s\nПроверьте:\n- IP адрес правильный\n- Сервер доступен в сети\n- Файрвол не блокирует порт {port}"
            logger.error(error)
            logger.debug("Timeout details", exc_info=True)
            return False, error
        except socket.error as e:
            error = f"Network error: {str(e)}\nПроверьте сетевое подключение"
            logger.error(error)
            logger.debug("Socket error details", exc_info=True)
            return False, error
        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            logger.error(error)
            logger.debug("Exception details", exc_info=True)
            return False, error
    
    def disconnect(self):
        """Close the SSH connection"""
        if self.sftp:
            try:
                self.sftp.close()
            except:
                pass
            self.sftp = None
        
        if self.client:
            try:
                self.client.close()
            except:
                pass
            self.client = None
        
        self.connected = False
        self.password = None  # Clear password from memory
        self.remote_home = None
        self.remote_daemon_config = None
        logger.info("Disconnected")
    
    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.connected and self.client and self.client.get_transport() and self.client.get_transport().is_active()
    
    def execute_command(self, command: str, sudo: bool = False, sudo_password: str = None, timeout: int = 300) -> Tuple[int, str, str]:
        """
        Execute a command on the remote system
        
        Args:
            command: Command to execute
            sudo: Whether to execute with sudo
            sudo_password: Password for sudo (if required, defaults to connection password)
            timeout: Command timeout in seconds (default 300s for long operations)
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        if not self.is_connected():
            return -1, "", "Not connected"
        
        try:
            use_pty = False
            
            # Use stored password if sudo_password not explicitly provided
            if sudo and sudo_password is None:
                sudo_password = self.password
            
            if sudo and sudo_password:
                # Use sudo -S to read password from stdin, needs pty
                command = f"sudo -S -p '' {command}"
                use_pty = True
            elif sudo:
                command = f"sudo {command}"
            
            logger.debug(f"Executing (pty={use_pty}): {command[:100]}{'...' if len(command) > 100 else ''}")
            
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout, get_pty=use_pty)
            
            # If using sudo -S, send password to stdin
            if sudo and sudo_password:
                stdin.write(sudo_password + '\n')
                stdin.flush()
            
            # Wait for command to complete and get exit code
            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode('utf-8')
            stderr_text = stderr.read().decode('utf-8')
            
            # Clean up sudo password prompt from output if present
            if sudo and sudo_password:
                lines = stdout_text.split('\n')
                if lines and (not lines[0].strip() or '[sudo]' in lines[0]):
                    stdout_text = '\n'.join(lines[1:])
            
            logger.debug(f"Exit code: {exit_code}")
            if exit_code != 0:
                logger.warning(f"Command stderr: {stderr_text[:500]}")
            
            return exit_code, stdout_text, stderr_text
            
        except Exception as e:
            error = f"Command execution failed: {str(e)}"
            logger.error(error)
            return -1, "", error

    def get_remote_home(self) -> str:
        """Return the remote user's home directory and cache the result."""
        if self.remote_home:
            return self.remote_home

        exit_code, stdout, _ = self.execute_command("echo $HOME")
        if exit_code == 0 and stdout.strip():
            self.remote_home = stdout.strip()
        else:
            self.remote_home = "/home/user"
        return self.remote_home

    def get_remote_daemon_config(self, refresh: bool = False) -> Dict[str, Any]:
        """Load `/etc/ktv/config.json` from the remote host when available."""
        if self.remote_daemon_config is not None and not refresh:
            return dict(self.remote_daemon_config)

        command = (
            "python3 -c \"import json, pathlib; "
            "path = pathlib.Path('/etc/ktv/config.json'); "
            "print(json.dumps(json.load(path.open('r', encoding='utf-8'))) if path.exists() else '{}')\""
        )
        exit_code, stdout, _ = self.execute_command(command, timeout=30)
        if exit_code == 0 and stdout.strip():
            try:
                self.remote_daemon_config = json.loads(stdout.strip())
            except json.JSONDecodeError:
                logger.warning("Could not decode remote daemon config")
                self.remote_daemon_config = {}
        else:
            self.remote_daemon_config = {}
        return dict(self.remote_daemon_config)

    def get_remote_daemon_port(self, default: int = 8888, refresh: bool = False) -> int:
        """Return the daemon API port from remote config or the default."""
        config = self.get_remote_daemon_config(refresh=refresh)
        try:
            return int(config.get('api_port', default))
        except (TypeError, ValueError):
            return default
    
    def upload_file(self, local_path: str, remote_path: str, 
                   callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, str]:
        """
        Upload a file to remote system via SFTP
        
        Args:
            local_path: Local file path
            remote_path: Remote file path
            callback: Optional callback(transferred, total) for progress
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.is_connected():
            return False, "Not connected"
        
        try:
            local_file = Path(local_path)
            if not local_file.exists():
                return False, f"Local file not found: {local_path}"
            
            logger.info(f"Uploading {local_path} to {remote_path}")
            
            # Ensure remote directory exists
            remote_dir = str(Path(remote_path).parent).replace('\\', '/')
            self._ensure_remote_dir(remote_dir)
            
            # Upload file
            self.sftp.put(local_path, remote_path, callback=callback)
            
            logger.info(f"Upload complete: {local_path}")
            return True, ""
            
        except Exception as e:
            error = f"Upload failed: {str(e)}"
            logger.error(error)
            return False, error
    
    def download_file(self, remote_path: str, local_path: str,
                     callback: Optional[Callable[[int, int], None]] = None) -> Tuple[bool, str]:
        """
        Download a file from remote system via SFTP
        
        Args:
            remote_path: Remote file path
            local_path: Local file path
            callback: Optional callback(transferred, total) for progress
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.is_connected():
            return False, "Not connected"
        
        try:
            logger.info(f"Downloading {remote_path} to {local_path}")
            
            # Ensure local directory exists
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Download file
            self.sftp.get(remote_path, local_path, callback=callback)
            
            logger.info(f"Download complete: {remote_path}")
            return True, ""
            
        except Exception as e:
            error = f"Download failed: {str(e)}"
            logger.error(error)
            return False, error
    
    def delete_file(self, remote_path: str) -> Tuple[bool, str]:
        """
        Delete a file on remote system
        
        Args:
            remote_path: Remote file path
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.is_connected():
            return False, "Not connected"
        
        try:
            logger.info(f"Deleting remote file: {remote_path}")
            self.sftp.remove(remote_path)
            return True, ""
        except Exception as e:
            error = f"Delete failed: {str(e)}"
            logger.error(error)
            return False, error
    
    def create_directory(self, remote_path: str) -> Tuple[bool, str]:
        """
        Create a directory on remote system
        
        Args:
            remote_path: Remote directory path
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.is_connected():
            return False, "Not connected"
        
        try:
            return self._ensure_remote_dir(remote_path), ""
        except Exception as e:
            error = f"Create directory failed: {str(e)}"
            logger.error(error)
            return False, error
    
    def list_directory(self, remote_path: str) -> Tuple[bool, list, str]:
        """
        List files in remote directory
        
        Args:
            remote_path: Remote directory path
            
        Returns:
            Tuple of (success, file_list, error_message)
        """
        if not self.is_connected():
            return False, [], "Not connected"
        
        try:
            files = self.sftp.listdir(remote_path)
            return True, files, ""
        except Exception as e:
            error = f"List directory failed: {str(e)}"
            logger.error(error)
            return False, [], error
    
    def file_exists(self, remote_path: str) -> bool:
        """Check if remote file exists"""
        if not self.is_connected():
            return False
        
        try:
            self.sftp.stat(remote_path)
            return True
        except:
            return False
    
    def _ensure_remote_dir(self, remote_path: str) -> bool:
        """Ensure remote directory exists, create if necessary"""
        if not self.is_connected():
            return False
        
        try:
            # Try to stat the directory
            self.sftp.stat(remote_path)
            return True
        except:
            # Directory doesn't exist, create it
            try:
                # Create parent directories recursively
                parts = remote_path.split('/')
                current = ''
                for part in parts:
                    if not part:
                        continue
                    current += '/' + part
                    try:
                        self.sftp.stat(current)
                    except:
                        self.sftp.mkdir(current)
                return True
            except Exception as e:
                logger.error(f"Failed to create directory {remote_path}: {e}")
                return False


# Test functionality
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test with your own credentials
    client = SSHClient()
    
    success, error = client.connect(
        host='192.168.1.100',
        username='user',
        password='password'
    )
    
    if success:
        print("Connected!")
        
        # Test command execution
        exit_code, stdout, stderr = client.execute_command('uname -a')
        print(f"Exit code: {exit_code}")
        print(f"Output: {stdout}")
        
        client.disconnect()
    else:
        print(f"Connection failed: {error}")
