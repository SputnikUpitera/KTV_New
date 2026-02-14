"""
Remote system checker
Verifies remote Linux system is compatible and checks installation status
"""

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class RemoteChecker:
    """Checks remote system compatibility and installation status"""
    
    def __init__(self, ssh_client):
        """
        Initialize remote checker
        
        Args:
            ssh_client: Connected SSH client instance
        """
        self.ssh = ssh_client
    
    def check_system(self) -> Tuple[bool, Dict[str, any], str]:
        """
        Perform comprehensive system check
        
        Returns:
            Tuple of (success, check_results, error_message)
        """
        if not self.ssh.is_connected():
            return False, {}, "SSH not connected"
        
        results = {
            'os': None,
            'os_compatible': False,
            'arch': None,
            'arch_compatible': False,
            'python3': None,
            'python3_available': False,
            'mpv': None,
            'mpv_available': False,
            'daemon_installed': False,
            'daemon_running': False,
            'sudo_available': False,
            'disk_space_mb': 0,
            'has_errors': False,
            'errors': []
        }
        
        try:
            # Check OS
            logger.info("Checking operating system...")
            exit_code, stdout, stderr = self.ssh.execute_command('lsb_release -a 2>/dev/null || cat /etc/os-release')
            if exit_code == 0:
                results['os'] = stdout.strip()
                # Check for Ubuntu/Debian
                if 'ubuntu' in stdout.lower() or 'debian' in stdout.lower():
                    results['os_compatible'] = True
                logger.info(f"OS check: {'compatible' if results['os_compatible'] else 'incompatible'}")
            
            # Check architecture
            logger.info("Checking architecture...")
            exit_code, stdout, stderr = self.ssh.execute_command('uname -m')
            if exit_code == 0:
                results['arch'] = stdout.strip()
                if results['arch'] in ['x86_64', 'amd64', 'armv7l', 'aarch64']:
                    results['arch_compatible'] = True
                logger.info(f"Architecture: {results['arch']}")
            
            # Check Python3
            logger.info("Checking Python3...")
            exit_code, stdout, stderr = self.ssh.execute_command('python3 --version')
            if exit_code == 0:
                results['python3'] = stdout.strip()
                results['python3_available'] = True
                logger.info(f"Python3: {results['python3']}")
            
            # Check MPV
            logger.info("Checking MPV...")
            exit_code, stdout, stderr = self.ssh.execute_command('mpv --version 2>/dev/null | head -1')
            if exit_code == 0:
                results['mpv'] = stdout.strip()
                results['mpv_available'] = True
                logger.info(f"MPV: {results['mpv']}")
            
            # Check if daemon is installed
            logger.info("Checking daemon installation...")
            exit_code, stdout, stderr = self.ssh.execute_command('test -f /opt/ktv/daemon.py && echo "installed" || echo "not_installed"')
            if 'installed' in stdout:
                results['daemon_installed'] = True
                logger.info("Daemon is installed")
            
            # Check if daemon is running
            if results['daemon_installed']:
                logger.info("Checking daemon status...")
                exit_code, stdout, stderr = self.ssh.execute_command('systemctl is-active ktv-daemon 2>/dev/null')
                if 'active' in stdout:
                    results['daemon_running'] = True
                    logger.info("Daemon is running")
            
            # Check sudo availability
            logger.info("Checking sudo...")
            exit_code, stdout, stderr = self.ssh.execute_command('sudo -n true 2>&1')
            if exit_code == 0:
                results['sudo_available'] = True
                logger.info("Sudo available without password")
            else:
                # May require password, but sudo exists
                exit_code, stdout, stderr = self.ssh.execute_command('which sudo')
                if exit_code == 0:
                    results['sudo_available'] = True
                    logger.info("Sudo available (may require password)")
            
            # Check disk space
            logger.info("Checking disk space...")
            exit_code, stdout, stderr = self.ssh.execute_command("df -m /opt 2>/dev/null | tail -1 | awk '{print $4}'")
            if exit_code == 0:
                try:
                    results['disk_space_mb'] = int(stdout.strip())
                    logger.info(f"Available disk space: {results['disk_space_mb']} MB")
                except:
                    pass
            
            # Collect errors
            if not results['os_compatible']:
                results['errors'].append("Operating system may not be compatible (Ubuntu/Debian recommended)")
            
            if not results['arch_compatible']:
                results['errors'].append(f"Architecture {results['arch']} may not be supported")
            
            if not results['sudo_available']:
                results['errors'].append("Sudo is required for installation")
            
            if results['disk_space_mb'] < 500:
                results['errors'].append(f"Low disk space: {results['disk_space_mb']} MB available (500 MB recommended)")
            
            results['has_errors'] = len(results['errors']) > 0
            
            return True, results, ""
            
        except Exception as e:
            error = f"System check failed: {str(e)}"
            logger.error(error)
            results['has_errors'] = True
            results['errors'].append(error)
            return False, results, error
    
    def get_system_info_summary(self, results: Dict) -> str:
        """
        Get a human-readable summary of system check results
        
        Args:
            results: Results dictionary from check_system()
            
        Returns:
            Formatted summary string
        """
        lines = []
        lines.append("=== Remote System Information ===")
        lines.append(f"OS: {results.get('os', 'Unknown')[:50]}")
        lines.append(f"Architecture: {results.get('arch', 'Unknown')}")
        lines.append(f"Python3: {results.get('python3', 'Not found')}")
        lines.append(f"MPV: {results.get('mpv', 'Not found')}")
        lines.append(f"Disk Space: {results.get('disk_space_mb', 0)} MB")
        lines.append(f"Daemon Installed: {'Yes' if results.get('daemon_installed') else 'No'}")
        lines.append(f"Daemon Running: {'Yes' if results.get('daemon_running') else 'No'}")
        
        if results.get('has_errors'):
            lines.append("\nWarnings/Errors:")
            for error in results.get('errors', []):
                lines.append(f"  - {error}")
        
        return '\n'.join(lines)


# Test functionality
if __name__ == '__main__':
    import sys
    sys.path.append('..')
    from network.ssh_client import SSHClient
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test with your own credentials
    ssh = SSHClient()
    success, error = ssh.connect(
        host='192.168.1.100',
        username='user',
        password='password'
    )
    
    if success:
        print("SSH connected!\n")
        
        checker = RemoteChecker(ssh)
        success, results, error = checker.check_system()
        
        if success:
            print(checker.get_system_info_summary(results))
        else:
            print(f"Check failed: {error}")
        
        ssh.disconnect()
    else:
        print(f"SSH connection failed: {error}")
