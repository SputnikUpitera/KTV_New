"""
Remote command protocol for communicating with KTV daemon
"""

import json
import socket
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)


class CommandClient:
    """Client for sending commands to KTV daemon API"""
    
    def __init__(self, ssh_client):
        """
        Initialize command client
        
        Args:
            ssh_client: Connected SSH client instance
        """
        self.ssh_client = ssh_client
        self.daemon_port = 8888

    def _send_via_ssh_tunnel(self, request_json: str) -> Dict[str, Any]:
        """Send a command through an SSH direct-tcpip channel to the daemon."""
        transport = self.ssh_client.client.get_transport() if self.ssh_client.client else None
        if not transport or not transport.is_active():
            raise RuntimeError("SSH transport is not active")

        channel = transport.open_channel(
            'direct-tcpip',
            ('127.0.0.1', self.daemon_port),
            ('127.0.0.1', 0),
        )
        try:
            channel.settimeout(10.0)
            channel.sendall(request_json.encode('utf-8'))
            channel.shutdown_write()

            data = bytearray()
            while True:
                chunk = channel.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
                try:
                    return json.loads(data.decode('utf-8'))
                except json.JSONDecodeError:
                    continue

            if not data:
                raise RuntimeError("Empty response from daemon")
            return json.loads(data.decode('utf-8'))
        finally:
            try:
                channel.close()
            except Exception:
                pass

    def _send_via_remote_python(self, request_json: str) -> Dict[str, Any]:
        """Fallback path using a short remote Python bridge."""
        request_literal = repr(request_json)
        python_cmd = f'''python3 -c "
import socket
import json
import sys

try:
    request_json = {request_literal}

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(('localhost', {self.daemon_port}))

    sock.sendall(request_json.encode('utf-8'))

    data = b''
    while True:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
        try:
            json.loads(data.decode('utf-8'))
            break
        except Exception:
            continue

    sock.close()
    print(data.decode('utf-8'))
    sys.exit(0)
except Exception as e:
    print(json.dumps({{'success': False, 'error': str(e)}}))
    sys.exit(1)
"
'''
        exit_code, stdout, stderr = self.ssh_client.execute_command(python_cmd)
        if exit_code != 0 and not stdout:
            raise RuntimeError(f"Command failed: {stderr}")
        return json.loads(stdout.strip())
    
    def send_command(self, command: str, params: Dict[str, Any] = None) -> Tuple[bool, Any, str]:
        """
        Send a command to the daemon
        
        Args:
            command: Command name
            params: Command parameters
            
        Returns:
            Tuple of (success, result, error_message)
        """
        if not self.ssh_client.is_connected():
            return False, None, "SSH not connected"
        
        if params is None:
            params = {}
        
        try:
            request = {
                'command': command,
                'params': params
            }
            request_json = json.dumps(request)
            
            logger.debug(f"Sending command: {command}")

            try:
                response = self._send_via_ssh_tunnel(request_json)
            except Exception as tunnel_error:
                logger.warning("Direct SSH tunnel command failed, falling back: %s", tunnel_error)
                response = self._send_via_remote_python(request_json)

            if response.get('success'):
                return True, response.get('result'), ""

            error = response.get('error', 'Unknown error')
            return False, None, error
            
        except Exception as e:
            error = f"Command execution failed: {str(e)}"
            logger.error(error)
            return False, None, error
    
    # Convenience methods for specific commands
    
    def add_schedule(self, month: int, day: int, hour: int, minute: int,
                    filepath: str, filename: str, category: str = 'movies') -> Tuple[bool, int, str]:
        """Add a schedule entry"""
        params = {
            'month': month,
            'day': day,
            'hour': hour,
            'minute': minute,
            'filepath': filepath,
            'filename': filename,
            'category': category
        }
        success, result, error = self.send_command('add_schedule', params)
        schedule_id = result.get('schedule_id', 0) if result else 0
        return success, schedule_id, error
    
    def remove_schedule(self, schedule_id: int) -> Tuple[bool, str]:
        """Remove a schedule entry"""
        success, result, error = self.send_command('remove_schedule', {'schedule_id': schedule_id})
        return success, error
    
    def toggle_schedule(self, schedule_id: int, enabled: bool) -> Tuple[bool, str]:
        """Toggle schedule enabled status"""
        params = {
            'schedule_id': schedule_id,
            'enabled': enabled
        }
        success, result, error = self.send_command('toggle_schedule', params)
        return success, error
    
    def list_schedules(self, enabled_only: bool = False, category: str = None) -> Tuple[bool, list, str]:
        """List all schedules"""
        params = {}
        if enabled_only:
            params['enabled_only'] = True
        if category:
            params['category'] = category
        
        success, result, error = self.send_command('list_schedules', params)
        schedules = result.get('schedules', []) if result else []
        return success, schedules, error

    def update_schedule(self, schedule_id: int, month: int, day: int, hour: int, minute: int) -> Tuple[bool, Dict, str]:
        """Update the time and canonical file path for a schedule."""
        params = {
            'schedule_id': schedule_id,
            'month': month,
            'day': day,
            'hour': hour,
            'minute': minute,
        }
        success, result, error = self.send_command('update_schedule', params)
        return success, result or {}, error

    def sync_schedules(self) -> Tuple[bool, Dict, str]:
        """Synchronize movie schedule rows with filesystem directories."""
        success, result, error = self.send_command('sync_schedules')
        return success, result or {}, error
    
    def create_playlist(self, name: str, folder_path: str) -> Tuple[bool, int, str]:
        """Create a new playlist"""
        params = {
            'name': name,
            'folder_path': folder_path
        }
        success, result, error = self.send_command('create_playlist', params)
        playlist_id = result.get('playlist_id', 0) if result else 0
        return success, playlist_id, error
    
    def delete_playlist(self, playlist_id: int) -> Tuple[bool, str]:
        """Delete a playlist"""
        success, result, error = self.send_command('delete_playlist', {'playlist_id': playlist_id})
        return success, error
    
    def set_active_playlist(self, playlist_id: int) -> Tuple[bool, str]:
        """Set active playlist"""
        success, result, error = self.send_command('set_active_playlist', {'playlist_id': playlist_id})
        return success, error
    
    def list_playlists(self) -> Tuple[bool, list, str]:
        """List all playlists"""
        success, result, error = self.send_command('list_playlists')
        playlists = result.get('playlists', []) if result else []
        return success, playlists, error

    def sync_playlists(self) -> Tuple[bool, Dict, str]:
        """Synchronize playlist rows with playlist directories."""
        success, result, error = self.send_command('sync_playlists')
        return success, result or {}, error
    
    def get_status(self) -> Tuple[bool, Dict, str]:
        """Get daemon status"""
        success, result, error = self.send_command('get_status')
        return success, result or {}, error

    def toggle_play_pause(self) -> Tuple[bool, Dict, str]:
        """Toggle play/pause for clip playback."""
        success, result, error = self.send_command('toggle_play_pause')
        return success, result or {}, error

    def stop_playback(self) -> Tuple[bool, Dict, str]:
        """Stop clip playback and leave it paused."""
        success, result, error = self.send_command('stop_playback')
        return success, result or {}, error

    def next_clip(self) -> Tuple[bool, Dict, str]:
        """Skip to the next clip."""
        success, result, error = self.send_command('next_clip')
        return success, result or {}, error

    def play_playlist_file(self, filename: str) -> Tuple[bool, Dict, str]:
        """Play a specific file from the selected playlist immediately."""
        success, result, error = self.send_command('play_playlist_file', {'filename': filename})
        return success, result or {}, error

    def previous_clip(self) -> Tuple[bool, Dict, str]:
        """Go back to the previous clip."""
        success, result, error = self.send_command('previous_clip')
        return success, result or {}, error

    def toggle_loop(self) -> Tuple[bool, Dict, str]:
        """Toggle playlist loop mode."""
        success, result, error = self.send_command('toggle_loop')
        return success, result or {}, error

    def toggle_shuffle(self) -> Tuple[bool, Dict, str]:
        """Toggle random clip playback."""
        success, result, error = self.send_command('toggle_shuffle')
        return success, result or {}, error
    
    def ping(self) -> Tuple[bool, str]:
        """Ping the daemon"""
        success, result, error = self.send_command('ping')
        return success, error


# Test functionality
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    import sys
    sys.path.append('..')
    from network.ssh_client import SSHClient
    
    # Test with your own credentials
    ssh = SSHClient()
    success, error = ssh.connect(
        host='192.168.1.100',
        username='user',
        password='password'
    )
    
    if success:
        print("SSH connected!")
        
        cmd_client = CommandClient(ssh)
        
        # Test ping
        success, error = cmd_client.ping()
        if success:
            print("Ping successful!")
        else:
            print(f"Ping failed: {error}")
        
        # Test status
        success, status, error = cmd_client.get_status()
        if success:
            print(f"Status: {status}")
        else:
            print(f"Status failed: {error}")
        
        ssh.disconnect()
    else:
        print(f"SSH connection failed: {error}")
