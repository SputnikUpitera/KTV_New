"""
Installation verification module
Verifies that KTV daemon is properly installed and running
"""

import logging
from typing import Dict, Tuple
import time

logger = logging.getLogger(__name__)


class InstallationVerifier:
    """Verifies KTV daemon installation"""
    
    def __init__(self, ssh_client):
        """
        Initialize installation verifier
        
        Args:
            ssh_client: Connected SSH client instance
        """
        self.ssh = ssh_client
    
    def verify(self) -> Tuple[bool, Dict[str, any], str]:
        """
        Verify the installation
        
        Returns:
            Tuple of (success, verification_results, error_message)
        """
        if not self.ssh.is_connected():
            return False, {}, "SSH not connected"
        
        results = {
            'daemon_files_present': False,
            'systemd_service_exists': False,
            'service_enabled': False,
            'service_running': False,
            'database_exists': False,
            'media_directories_exist': False,
            'config_exists': False,
            'api_port_responding': False,
            'vlc_available': False,
            'all_checks_passed': False,
            'errors': []
        }
        
        try:
            # Check daemon files
            logger.info("Checking daemon files...")
            exit_code, stdout, stderr = self.ssh.execute_command('test -f /opt/ktv/daemon.py && echo "yes" || echo "no"')
            if 'yes' in stdout:
                results['daemon_files_present'] = True
                logger.info("✓ Daemon files present")
            else:
                results['errors'].append("Daemon files not found in /opt/ktv/")
                logger.error("✗ Daemon files not found")
            
            # Check systemd service
            logger.info("Checking systemd service...")
            exit_code, stdout, stderr = self.ssh.execute_command('systemctl list-unit-files ktv-daemon.service')
            if 'ktv-daemon.service' in stdout:
                results['systemd_service_exists'] = True
                logger.info("✓ Systemd service exists")
            else:
                results['errors'].append("Systemd service not found")
                logger.error("✗ Systemd service not found")
            
            # Check if service is enabled
            logger.info("Checking if service is enabled...")
            exit_code, stdout, stderr = self.ssh.execute_command('systemctl is-enabled ktv-daemon 2>/dev/null')
            if 'enabled' in stdout:
                results['service_enabled'] = True
                logger.info("✓ Service is enabled")
            else:
                results['errors'].append("Service is not enabled for auto-start")
                logger.warning("✗ Service not enabled")
            
            # Check if service is running
            logger.info("Checking if service is running...")
            exit_code, stdout, stderr = self.ssh.execute_command('systemctl is-active ktv-daemon 2>/dev/null')
            if stdout.strip() == 'active':
                results['service_running'] = True
                logger.info("✓ Service is running")
            else:
                results['errors'].append("Service is not running")
                logger.error("✗ Service not running")
                
                # Try to get service status for debugging
                exit_code, stdout, stderr = self.ssh.execute_command('systemctl status ktv-daemon 2>&1')
                logger.info(f"Service status:\n{stdout}")
            
            # Check database
            logger.info("Checking database...")
            exit_code, stdout, stderr = self.ssh.execute_command('test -f /var/lib/ktv/schedule.db && echo "yes" || echo "no"')
            if 'yes' in stdout:
                results['database_exists'] = True
                logger.info("✓ Database exists")
            else:
                results['errors'].append("Database file not found")
                logger.warning("✗ Database not found")
            
            # Check media directories (home-based structure)
            logger.info("Checking media directories...")
            exit_code, stdout, stderr = self.ssh.execute_command('test -d ~/clips && echo "yes" || echo "no"')
            if 'yes' in stdout:
                results['media_directories_exist'] = True
                logger.info("✓ Media directories exist")
            else:
                results['errors'].append("Clips directory ~/clips not found")
                logger.warning("✗ Media directories not found")
            
            # Check config file
            logger.info("Checking configuration...")
            exit_code, stdout, stderr = self.ssh.execute_command('test -f /etc/ktv/config.json && echo "yes" || echo "no"')
            if 'yes' in stdout:
                results['config_exists'] = True
                logger.info("✓ Configuration file exists")
            else:
                results['errors'].append("Configuration file not found")
                logger.warning("✗ Configuration not found")
            
            # Check VLC
            logger.info("Checking VLC...")
            exit_code, stdout, stderr = self.ssh.execute_command('which vlc')
            if exit_code == 0:
                results['vlc_available'] = True
                logger.info("✓ VLC is available")
            else:
                results['errors'].append("VLC is not installed")
                logger.error("✗ VLC not found")
            
            # Check API port (if service is running)
            if results['service_running']:
                logger.info("Checking API port...")
                time.sleep(2)  # Give service time to fully start
                
                # Try to connect to API port
                exit_code, stdout, stderr = self.ssh.execute_command(
                    'timeout 5 bash -c "echo > /dev/tcp/localhost/8888" 2>&1 && echo "yes" || echo "no"'
                )
                if 'yes' in stdout:
                    results['api_port_responding'] = True
                    logger.info("✓ API port responding")
                else:
                    results['errors'].append("API port not responding")
                    logger.warning("✗ API port not responding")
            
            # Determine overall success
            critical_checks = [
                results['daemon_files_present'],
                results['systemd_service_exists'],
                results['service_running'],
                results.get('vlc_available', False)
            ]
            results['all_checks_passed'] = all(critical_checks)
            
            if results['all_checks_passed']:
                logger.info("✓ All critical checks passed")
                return True, results, ""
            else:
                error = f"Installation verification failed: {len(results['errors'])} errors"
                logger.error(error)
                return False, results, error
            
        except Exception as e:
            error = f"Verification failed: {str(e)}"
            logger.error(error)
            results['errors'].append(error)
            return False, results, error
    
    def get_verification_summary(self, results: Dict) -> str:
        """
        Get a human-readable summary of verification results
        
        Args:
            results: Results dictionary from verify()
            
        Returns:
            Formatted summary string
        """
        lines = []
        lines.append("=== Installation Verification ===")
        
        checks = [
            ("Daemon Files", results.get('daemon_files_present')),
            ("Systemd Service", results.get('systemd_service_exists')),
            ("Service Enabled", results.get('service_enabled')),
            ("Service Running", results.get('service_running')),
            ("Database", results.get('database_exists')),
            ("Media Directories", results.get('media_directories_exist')),
            ("Configuration", results.get('config_exists')),
            ("VLC Available", results.get('vlc_available')),
            ("API Port 8888", results.get('api_port_responding'))
        ]
        
        for name, passed in checks:
            status = "✓" if passed else "✗"
            lines.append(f"{status} {name}")
        
        if results.get('errors'):
            lines.append("\nErrors/Warnings:")
            for error in results['errors']:
                lines.append(f"  - {error}")
        
        if results.get('all_checks_passed'):
            lines.append("\n✓ Installation verified successfully!")
        else:
            lines.append("\n✗ Installation verification failed!")
        
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
        
        verifier = InstallationVerifier(ssh)
        success, results, error = verifier.verify()
        
        print(verifier.get_verification_summary(results))
        
        ssh.disconnect()
    else:
        print(f"SSH connection failed: {error}")
