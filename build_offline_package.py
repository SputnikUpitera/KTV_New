#!/usr/bin/env python3
"""
Build offline package for KTV Linux daemon installation
This script creates a complete offline installation package
"""

import os
import sys
import subprocess
import shutil
import argparse
import tarfile
from pathlib import Path

# Package URLs for Ubuntu 20.04 (Focal)
PACKAGE_URLS = {
    'x86_64': {
        'mpv': [
            'http://archive.ubuntu.com/ubuntu/pool/universe/m/mpv/mpv_0.32.0-3ubuntu1_amd64.deb',
            'http://archive.ubuntu.com/ubuntu/pool/universe/m/mpv/libmpv1_0.32.0-3ubuntu1_amd64.deb',
        ],
        'dependencies': [
            # Core dependencies for mpv
            'http://archive.ubuntu.com/ubuntu/pool/universe/f/ffmpeg/libavcodec58_4.2.7-0ubuntu0.1_amd64.deb',
            'http://archive.ubuntu.com/ubuntu/pool/universe/f/ffmpeg/libavformat58_4.2.7-0ubuntu0.1_amd64.deb',
            'http://archive.ubuntu.com/ubuntu/pool/universe/f/ffmpeg/libavutil56_4.2.7-0ubuntu0.1_amd64.deb',
            'http://archive.ubuntu.com/ubuntu/pool/universe/f/ffmpeg/libswscale5_4.2.7-0ubuntu0.1_amd64.deb',
        ]
    }
}

class OfflinePackageBuilder:
    def __init__(self, arch='x86_64', output_dir='offline_package'):
        self.arch = arch
        self.output_dir = Path(output_dir)
        self.build_dir = Path('build_temp')
        
    def setup_directories(self):
        """Create necessary directories"""
        print("[1/7] Setting up directories...")
        dirs = [
            self.build_dir / 'packages',
            self.build_dir / 'python_wheels',
            self.build_dir / 'daemon',
            self.build_dir / 'systemd',
            self.build_dir / 'config'
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        print("✓ Directories created")
    
    def download_packages(self):
        """Download .deb packages"""
        print(f"[2/7] Downloading packages for {self.arch}...")
        print("Note: This requires internet. Run this script on a machine with internet access.")
        
        packages_dir = self.build_dir / 'packages'
        
        # Create a manifest file with all required packages
        manifest = []
        if self.arch in PACKAGE_URLS:
            for url in PACKAGE_URLS[self.arch]['mpv'] + PACKAGE_URLS[self.arch].get('dependencies', []):
                manifest.append(url)
        
        # Write manifest for manual download if needed
        manifest_file = packages_dir / 'download_manifest.txt'
        with open(manifest_file, 'w') as f:
            f.write('\n'.join(manifest))
        
        print(f"✓ Package manifest created at: {manifest_file}")
        print("  You can download these manually and place them in the packages/ directory")
        
        # Try to download using wget or curl if available
        for url in manifest:
            filename = os.path.basename(url)
            output_path = packages_dir / filename
            if output_path.exists():
                print(f"  ✓ {filename} already exists")
                continue
            
            print(f"  Downloading {filename}...")
            # Try wget first, then curl
            try:
                subprocess.run(['wget', '-q', '-O', str(output_path), url], check=True)
                print(f"  ✓ Downloaded {filename}")
            except:
                try:
                    subprocess.run(['curl', '-s', '-o', str(output_path), url], check=True)
                    print(f"  ✓ Downloaded {filename}")
                except:
                    print(f"  ✗ Could not download {filename}. Please download manually from:")
                    print(f"    {url}")
        
    def download_python_wheels(self):
        """Download Python wheel files"""
        print("[3/7] Downloading Python packages...")
        wheels_dir = self.build_dir / 'python_wheels'
        
        try:
            # Download wheels for Linux
            subprocess.run([
                sys.executable, '-m', 'pip', 'download',
                '-r', 'requirements_linux.txt',
                '-d', str(wheels_dir),
                '--platform', 'manylinux2014_x86_64',
                '--only-binary=:all:',
                '--python-version', '38'
            ], check=True)
            print("✓ Python wheels downloaded")
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to download Python wheels: {e}")
            print("  Creating a minimal set...")
            # Create a README for manual download
            with open(wheels_dir / 'README.txt', 'w') as f:
                f.write("Download these Python packages and place .whl files here:\n")
                with open('requirements_linux.txt') as req:
                    f.write(req.read())
    
    def copy_daemon_files(self):
        """Copy daemon source files"""
        print("[4/7] Copying daemon files...")
        daemon_src = Path('remote_player')
        daemon_dst = self.build_dir / 'daemon'
        
        if daemon_src.exists():
            shutil.copytree(daemon_src, daemon_dst, dirs_exist_ok=True)
            print("✓ Daemon files copied")
        else:
            print("✗ Daemon source directory not found. Will create placeholder.")
            (daemon_dst / 'placeholder.txt').write_text("Daemon files will be added here", encoding='utf-8')
    
    def create_systemd_service(self):
        """Create systemd service file"""
        print("[5/7] Creating systemd service...")
        service_content = """[Unit]
Description=KTV Media Player Daemon
After=network.target

[Service]
Type=simple
User=ktv
Group=ktv
WorkingDirectory=/opt/ktv
ExecStart=/usr/bin/python3 /opt/ktv/daemon.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/ktv/daemon.log
StandardError=append:/var/log/ktv/daemon.log

[Install]
WantedBy=multi-user.target
"""
        service_file = self.build_dir / 'systemd' / 'ktv-daemon.service'
        # Use Unix line endings (LF) even on Windows
        with open(service_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(service_content)
        print("✓ Systemd service created")
    
    def create_config(self):
        """Create default configuration"""
        print("[6/7] Creating configuration...")
        config_content = """{
    "api_port": 8888,
    "media_base_path": "~",
    "clips_folder": "~/clips",
    "database_path": "/var/lib/ktv/schedule.db",
    "log_path": "/var/log/ktv/daemon.log",
    "broadcast_start": "06:00",
    "broadcast_end": "22:00",
    "vlc_path": "/usr/bin/vlc",
    "display": ":0"
}
"""
        config_file = self.build_dir / 'config' / 'config.json'
        # Use Unix line endings (LF) even on Windows
        with open(config_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(config_content)
        print("✓ Configuration created")
    
    def create_install_script(self):
        """Create installation script"""
        print("[7/7] Creating installation script...")
        
        install_script = """#!/bin/bash
set -e

# Colors for output
RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m' # No Color

echo -e "${GREEN}=== KTV Media Player Installation ===${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

# Detect architecture
ARCH=$(uname -m)
echo "Detected architecture: $ARCH"

if [ "$ARCH" != "x86_64" ]; then
    echo -e "${YELLOW}Warning: This package was built for x86_64${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Install .deb packages
echo -e "${GREEN}[1/8] Installing system packages...${NC}"
cd packages
if ls *.deb 1> /dev/null 2>&1; then
    dpkg -i *.deb 2>/dev/null || apt-get install -f -y
    echo "✓ System packages installed"
else
    echo -e "${YELLOW}Warning: No .deb packages found. MPV should be pre-installed.${NC}"
fi
cd ..

# Check if python3 is available
echo -e "${GREEN}[2/8] Checking Python3...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python3 is not installed${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✓ Found $PYTHON_VERSION"

# Check if mpv is available
echo -e "${GREEN}[3/8] Checking MPV...${NC}"
if ! command -v mpv &> /dev/null; then
    echo -e "${RED}Error: MPV is not installed${NC}"
    exit 1
fi
MPV_VERSION=$(mpv --version | head -1)
echo "✓ Found $MPV_VERSION"

# Create KTV user and group
echo -e "${GREEN}[4/8] Creating KTV user and group...${NC}"
if id "ktv" &>/dev/null; then
    echo "✓ User 'ktv' already exists"
else
    useradd -r -s /bin/false ktv
    echo "✓ User 'ktv' created"
fi

# Add current user (who runs this script via sudo) to ktv group
ORIGINAL_USER="${SUDO_USER:-$USER}"
if [ "$ORIGINAL_USER" != "root" ]; then
    usermod -aG ktv "$ORIGINAL_USER"
    echo "✓ User '$ORIGINAL_USER' added to 'ktv' group"
fi

# Create directories
echo -e "${GREEN}[5/8] Creating directories...${NC}"
mkdir -p /opt/ktv
mkdir -p /opt/ktv/media/movies
mkdir -p /opt/ktv/media/clips
mkdir -p /var/lib/ktv
mkdir -p /var/log/ktv
mkdir -p /etc/ktv

# Set ownership and permissions
chown -R ktv:ktv /opt/ktv
chown -R ktv:ktv /var/lib/ktv
chown -R ktv:ktv /var/log/ktv
chown -R ktv:ktv /etc/ktv

# Make media directories writable by group
chmod -R 775 /opt/ktv/media
chmod -R 775 /var/lib/ktv
chmod -R 775 /var/log/ktv

# Set setgid bit so new files inherit group ownership
chmod g+s /opt/ktv/media/movies
chmod g+s /opt/ktv/media/clips

echo "✓ Directories created with proper permissions"

# Install Python packages
echo -e "${GREEN}[6/8] Installing Python packages...${NC}"

# Check if pip3 is available, install if not
if ! command -v pip3 &> /dev/null; then
    echo "pip3 not found, installing..."
    python3 -m ensurepip --default-pip 2>/dev/null || true
fi

# Install Python packages from wheels to system Python
# Use --break-system-packages for newer Python versions (3.11+) with PEP 668
if [ -d "python_wheels" ] && [ "$(ls -A python_wheels/*.whl 2>/dev/null)" ]; then
    if command -v pip3 &> /dev/null; then
        pip3 install --break-system-packages --no-index --find-links=python_wheels python_wheels/*.whl
        echo "✓ Python packages installed"
    else
        echo -e "${RED}Error: pip3 not available${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Warning: No Python wheels found${NC}"
fi

# Copy daemon files
echo -e "${GREEN}[7/8] Installing daemon...${NC}"
if [ -d "daemon" ]; then
    cp -r daemon/* /opt/ktv/
    echo "✓ Daemon files copied"
else
    echo -e "${RED}Error: Daemon files not found${NC}"
    exit 1
fi

# Copy configuration
if [ -f "config/config.json" ]; then
    cp config/config.json /etc/ktv/config.json
    echo "✓ Configuration copied"
fi

# Set permissions
chown -R ktv:ktv /opt/ktv
chown -R ktv:ktv /var/lib/ktv
chown -R ktv:ktv /var/log/ktv
chmod -R 755 /opt/ktv

# Media directories need group write permissions
chmod -R 775 /opt/ktv/media
chmod g+s /opt/ktv/media/movies
chmod g+s /opt/ktv/media/clips

# Install systemd service
echo -e "${GREEN}[8/8] Installing systemd service...${NC}"
if [ -f "systemd/ktv-daemon.service" ]; then
    cp systemd/ktv-daemon.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ktv-daemon.service
    systemctl start ktv-daemon.service
    
    sleep 2
    if systemctl is-active --quiet ktv-daemon.service; then
        echo -e "${GREEN}✓ KTV daemon is running${NC}"
    else
        echo -e "${YELLOW}Warning: Daemon installed but not running. Check logs with: journalctl -u ktv-daemon${NC}"
    fi
else
    echo -e "${YELLOW}Warning: Systemd service file not found${NC}"
fi

# Optional: Setup Samba for Windows access
echo -e "${GREEN}[9/9] Setting up Samba (optional)...${NC}"
if command -v smbpasswd &> /dev/null; then
    echo "Samba is already installed"
    echo "To share home directory, add to /etc/samba/smb.conf:"
    echo ""
    echo "[home]"
    echo "   path = /home/$ORIGINAL_USER"
    echo "   browseable = yes"
    echo "   read only = no"
    echo "   create mask = 0775"
    echo "   directory mask = 0775"
    echo "   valid users = $ORIGINAL_USER"
    echo ""
    echo "Then set Samba password: sudo smbpasswd -a $ORIGINAL_USER"
    echo "And restart: sudo systemctl restart smbd"
else
    echo -e "${YELLOW}Samba not installed. Install with: sudo apt install samba${NC}"
    echo "Then configure as shown above for Windows file access"
fi

echo -e "${GREEN}=== Installation Complete ===${NC}"
echo ""
echo "Configuration file: /etc/ktv/config.json"
echo "Media directory: ~/ (home folder, structure MM/DD/HH-MM/)"
echo "Clips directory: ~/clips/"
echo "Logs: /var/log/ktv/daemon.log"
echo ""
echo "Service commands:"
echo "  systemctl status ktv-daemon   - Check status"
echo "  systemctl restart ktv-daemon  - Restart service"
echo "  journalctl -u ktv-daemon -f   - View logs"
echo ""
echo -e "${YELLOW}IMPORTANT: User '$ORIGINAL_USER' was added to 'ktv' group.${NC}"
echo -e "${YELLOW}You must log out and log back in for file upload permissions to work!${NC}"
echo ""
echo -e "${YELLOW}API Port: 8888 (не конфликтует со старой системой на порту 9999)${NC}"
echo ""
"""
        
        install_file = self.build_dir / 'install.sh'
        # Use Unix line endings (LF) even on Windows
        with open(install_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(install_script)
        install_file.chmod(0o755)
        print("✓ Installation script created")
    
    def create_readme(self):
        """Create README for the package"""
        readme_content = """# KTV Media Player Offline Installation Package

## System Requirements
- Ubuntu 20.04 LTS (Focal Fossa) or compatible
- x86_64 architecture
- At least 500MB free disk space
- SSH server installed and running
- sudo privileges

## Installation Instructions

1. Extract this package on the target Linux system:
   ```
   tar -xzf ktv_offline_package.tar.gz
   cd ktv_offline_package
   ```

2. Run the installation script with sudo:
   ```
   sudo bash install.sh
   ```

3. The installation will:
   - Install MPV and dependencies
   - Create KTV user and directories
   - Install Python packages
   - Install and start the KTV daemon service

4. Verify installation:
   ```
   systemctl status ktv-daemon
   ```

## Manual Installation

If automatic installation fails, you can:

1. Install packages manually:
   ```
   cd packages
   sudo dpkg -i *.deb
   sudo apt-get install -f
   ```

2. Follow the steps in install.sh manually

## Troubleshooting

- Check logs: `journalctl -u ktv-daemon -f`
- Check daemon log: `/var/log/ktv/daemon.log`
- Restart service: `sudo systemctl restart ktv-daemon`

## Files and Directories

- `/opt/ktv/` - Main application directory
- `/opt/ktv/media/movies/` - Movies storage
- `/opt/ktv/media/clips/` - Clips/playlists storage
- `/etc/ktv/config.json` - Configuration file
- `/var/lib/ktv/schedule.db` - Schedule database
- `/var/log/ktv/daemon.log` - Application logs

## Configuration

Edit `/etc/ktv/config.json` to change:
- API port (default: 8888)
- Media paths
- Broadcast hours (default: 06:00-22:00)

After changes, restart the service:
```
sudo systemctl restart ktv-daemon
```
"""
        readme_file = self.build_dir / 'README_INSTALL.txt'
        readme_file.write_text(readme_content, encoding='utf-8')
        print("✓ README created")
    
    def create_tarball(self):
        """Create final tar.gz package"""
        print("\nCreating final package...")
        
        # Create install script and README
        self.create_install_script()
        self.create_readme()
        
        output_file = self.output_dir / 'ktv_offline_package.tar.gz'
        self.output_dir.mkdir(exist_ok=True)
        
        with tarfile.open(output_file, 'w:gz') as tar:
            tar.add(self.build_dir, arcname='ktv_offline_package')
        
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"\n✓ Package created: {output_file}")
        print(f"  Size: {size_mb:.2f} MB")
        
        return output_file
    
    def cleanup(self):
        """Clean up build directory"""
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
    
    def build(self):
        """Build the complete package"""
        try:
            self.setup_directories()
            self.download_packages()
            self.download_python_wheels()
            self.copy_daemon_files()
            self.create_systemd_service()
            self.create_config()
            
            package_file = self.create_tarball()
            
            print("\n" + "="*60)
            print("Build complete!")
            print("="*60)
            print(f"\nPackage location: {package_file}")
            print("\nThis package should be embedded in the Windows GUI application.")
            print("The GUI will transfer and install it on the remote Linux system.")
            
            return package_file
            
        except Exception as e:
            print(f"\n✗ Build failed: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # Optional: cleanup build directory
            # self.cleanup()
            pass

def main():
    parser = argparse.ArgumentParser(description='Build KTV offline installation package')
    parser.add_argument('--arch', default='x86_64', choices=['x86_64', 'armv7l'],
                       help='Target architecture (default: x86_64)')
    parser.add_argument('--output', default='offline_package',
                       help='Output directory (default: offline_package)')
    parser.add_argument('--no-cleanup', action='store_true',
                       help='Keep build directory after completion')
    
    args = parser.parse_args()
    
    builder = OfflinePackageBuilder(arch=args.arch, output_dir=args.output)
    package = builder.build()
    
    if not args.no_cleanup and package:
        print("\nCleaning up build directory...")
        builder.cleanup()
        print("✓ Cleanup complete")
    
    sys.exit(0 if package else 1)

if __name__ == '__main__':
    main()
