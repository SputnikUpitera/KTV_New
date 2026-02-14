"""
Package deployment module
Handles upload and installation of offline package on remote system
"""

import logging
import os
from pathlib import Path
from typing import Callable, Tuple
import time

logger = logging.getLogger(__name__)


class PackageDeployer:
    """Deploys offline installation package to remote system"""
    
    def __init__(self, ssh_client):
        """
        Initialize package deployer
        
        Args:
            ssh_client: Connected SSH client instance
        """
        self.ssh = ssh_client
        self.package_path = None
        self.remote_temp_dir = '/tmp/ktv_install'
    
    def set_package_path(self, package_path: str) -> bool:
        """
        Set the path to the offline package
        
        Args:
            package_path: Path to ktv_offline_package.tar.gz
            
        Returns:
            True if package exists
        """
        path = Path(package_path)
        if not path.exists():
            logger.error(f"Package not found: {package_path}")
            return False
        
        self.package_path = str(path)
        logger.info(f"Package set: {self.package_path}")
        return True
    
    def deploy(self, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """
        Deploy the package to remote system
        
        Args:
            progress_callback: Optional callback(message, percent) for progress updates
            
        Returns:
            Tuple of (success, error_message)
        """
        if not self.ssh.is_connected():
            return False, "SSH not connected"
        
        if not self.package_path:
            return False, "Package path not set"
        
        try:
            # Step 1: Create temp directory
            if progress_callback:
                progress_callback("Creating temporary directory...", 5)
            
            logger.info("Creating remote temp directory...")
            exit_code, stdout, stderr = self.ssh.execute_command(f'mkdir -p {self.remote_temp_dir}')
            if exit_code != 0:
                return False, f"Failed to create temp directory: {stderr}"
            
            # Step 2: Upload package
            if progress_callback:
                progress_callback("Uploading installation package...", 10)
            
            logger.info("Uploading package...")
            package_name = Path(self.package_path).name
            remote_package_path = f"{self.remote_temp_dir}/{package_name}"
            
            # Upload with progress tracking
            file_size = os.path.getsize(self.package_path)
            last_percent = 0
            
            def upload_progress(transferred, total):
                nonlocal last_percent
                percent = int((transferred / total) * 100)
                # Only update every 5%
                if percent >= last_percent + 5:
                    last_percent = percent
                    # Map to 10-50% of overall progress
                    overall_percent = 10 + int(percent * 0.4)
                    if progress_callback:
                        progress_callback(f"Uploading... {transferred}/{total} bytes", overall_percent)
            
            success, error = self.ssh.upload_file(
                self.package_path,
                remote_package_path,
                callback=upload_progress
            )
            
            if not success:
                return False, f"Upload failed: {error}"
            
            # Step 3: Extract package
            if progress_callback:
                progress_callback("Extracting package...", 55)
            
            logger.info("Extracting package...")
            exit_code, stdout, stderr = self.ssh.execute_command(
                f'cd {self.remote_temp_dir} && tar -xzf {package_name}'
            )
            if exit_code != 0:
                return False, f"Failed to extract package: {stderr}"
            
            # Step 4: Run installation script
            if progress_callback:
                progress_callback("Running installation script...", 60)
            
            logger.info("Running installation script...")
            install_dir = f"{self.remote_temp_dir}/ktv_offline_package"
            install_script = f"{install_dir}/install.sh"
            
            # Make script executable
            exit_code, stdout, stderr = self.ssh.execute_command(f'chmod +x {install_script}')
            if exit_code != 0:
                return False, f"Failed to make script executable: {stderr}"
            
            # Run installation (this may take a while)
            logger.info("Executing install.sh (this may take several minutes)...")
            if progress_callback:
                progress_callback("Installing components (this may take a few minutes)...", 65)
            
            # Execute with sudo - use the stored password
            # Use bash -c to execute cd && command as a single shell command
            exit_code, stdout, stderr = self.ssh.execute_command(
                f'bash -c "cd {install_dir} && bash install.sh"',
                sudo=True,  # Execute with sudo, will use stored password
                timeout=600  # Allow 10 minutes for installation
            )
            
            # Log installation output
            logger.info(f"Installation output:\n{stdout}")
            if stderr:
                logger.warning(f"Installation warnings/errors:\n{stderr}")
            
            if exit_code != 0:
                return False, f"Installation failed with exit code {exit_code}:\n{stderr}"
            
            # Step 5: Cleanup
            if progress_callback:
                progress_callback("Cleaning up...", 95)
            
            logger.info("Cleaning up...")
            self.ssh.execute_command(f'rm -rf {self.remote_temp_dir}')
            
            if progress_callback:
                progress_callback("Installation complete!", 100)
            
            logger.info("Deployment complete!")
            return True, ""
            
        except Exception as e:
            error = f"Deployment failed: {str(e)}"
            logger.error(error)
            return False, error
    
    def cleanup_remote_files(self):
        """Clean up remote temporary files"""
        if self.ssh.is_connected():
            try:
                self.ssh.execute_command(f'rm -rf {self.remote_temp_dir}')
                logger.info("Cleaned up remote temporary files")
            except Exception as e:
                logger.warning(f"Failed to cleanup: {e}")


# Test functionality
if __name__ == '__main__':
    import sys
    sys.path.append('..')
    from network.ssh_client import SSHClient
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    def progress_callback(message, percent):
        print(f"[{percent}%] {message}")
    
    # Test with your own credentials
    ssh = SSHClient()
    success, error = ssh.connect(
        host='192.168.1.100',
        username='user',
        password='password'
    )
    
    if success:
        print("SSH connected!\n")
        
        deployer = PackageDeployer(ssh)
        
        # Set package path (adjust to your actual package location)
        package_path = "../../offline_package/ktv_offline_package.tar.gz"
        if deployer.set_package_path(package_path):
            print(f"Package found: {package_path}\n")
            
            print("Starting deployment...")
            success, error = deployer.deploy(progress_callback=progress_callback)
            
            if success:
                print("\nDeployment successful!")
            else:
                print(f"\nDeployment failed: {error}")
        else:
            print(f"Package not found: {package_path}")
        
        ssh.disconnect()
    else:
        print(f"SSH connection failed: {error}")
