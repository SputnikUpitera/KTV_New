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
        self.cache_dir = Path('download_cache')
        self.deb_cache = self.cache_dir / 'packages'
        self.whl_cache = self.cache_dir / 'python_wheels'
        
    def setup_directories(self):
        """Create necessary directories (clean build_temp first)"""
        print("[1/7] Setting up directories...")
        
        # Always start with a fresh build directory
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        
        dirs = [
            self.build_dir / 'packages',
            self.build_dir / 'python_wheels',
            self.build_dir / 'daemon',
            self.build_dir / 'systemd',
            self.build_dir / 'config',
            self.deb_cache,
            self.whl_cache,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
        print("✓ Directories created")
    
    def download_packages(self):
        """Download .deb packages (uses cache to avoid re-downloading)"""
        print(f"[2/7] Downloading packages for {self.arch}...")
        
        packages_dir = self.build_dir / 'packages'
        
        manifest = []
        if self.arch in PACKAGE_URLS:
            for url in PACKAGE_URLS[self.arch]['mpv'] + PACKAGE_URLS[self.arch].get('dependencies', []):
                manifest.append(url)
        
        manifest_file = packages_dir / 'download_manifest.txt'
        with open(manifest_file, 'w') as f:
            f.write('\n'.join(manifest))
        
        cached = 0
        downloaded = 0
        
        for url in manifest:
            filename = os.path.basename(url)
            cache_path = self.deb_cache / filename
            build_path = packages_dir / filename
            
            # Check cache first
            if cache_path.exists():
                shutil.copy2(cache_path, build_path)
                print(f"  ✓ {filename} (из кеша)")
                cached += 1
                continue
            
            # Download and cache
            print(f"  Скачивание {filename}...")
            try:
                subprocess.run(['wget', '-q', '-O', str(cache_path), url], check=True)
            except Exception:
                try:
                    subprocess.run(['curl', '-s', '-o', str(cache_path), url], check=True)
                except Exception:
                    print(f"  ✗ Не удалось скачать {filename}")
                    continue
            
            shutil.copy2(cache_path, build_path)
            print(f"  ✓ {filename} (скачано)")
            downloaded += 1
        
        print(f"✓ Пакеты готовы (из кеша: {cached}, скачано: {downloaded})")
        
    def _get_requirements_hash(self) -> str:
        """Get a hash of requirements file to detect changes"""
        import hashlib
        req_path = Path('requirements_linux.txt')
        if req_path.exists():
            return hashlib.md5(req_path.read_bytes()).hexdigest()[:12]
        return "unknown"
    
    def download_python_wheels(self):
        """Download Python wheel files (uses cache, invalidates on requirements change)"""
        print("[3/7] Downloading Python packages...")
        wheels_dir = self.build_dir / 'python_wheels'
        
        # Check if cache is still valid (requirements haven't changed)
        req_hash = self._get_requirements_hash()
        hash_file = self.whl_cache / '.requirements_hash'
        cache_valid = False
        
        cached_wheels = list(self.whl_cache.glob('*.whl'))
        if cached_wheels and hash_file.exists():
            saved_hash = hash_file.read_text().strip()
            if saved_hash == req_hash:
                cache_valid = True
        
        if cache_valid:
            print(f"  Найдено {len(cached_wheels)} пакетов в кеше (актуален), пропуск скачивания")
            for whl in cached_wheels:
                shutil.copy2(whl, wheels_dir / whl.name)
            print(f"✓ Python wheels скопированы из кеша")
            return
        
        # Cache invalid or empty — clear and re-download
        if cached_wheels:
            print("  Кеш устарел (requirements изменились), перекачиваю...")
            for old_whl in cached_wheels:
                old_whl.unlink()
        
        try:
            subprocess.run([
                sys.executable, '-m', 'pip', 'download',
                '-r', 'requirements_linux.txt',
                '-d', str(self.whl_cache),
                '--platform', 'manylinux2014_x86_64',
                '--platform', 'manylinux1_x86_64',
                '--platform', 'linux_x86_64',
                '--platform', 'any',
                '--only-binary=:all:',
                '--python-version', '38',
                '--implementation', 'cp',
                '--abi', 'cp38',
            ], check=True)
            
            # Save hash to mark cache as valid
            hash_file.write_text(req_hash)
            
            # Copy from cache to build dir
            for whl in self.whl_cache.glob('*.whl'):
                shutil.copy2(whl, wheels_dir / whl.name)
            
            print("✓ Python wheels скачаны и закешированы")
        except subprocess.CalledProcessError as e:
            print(f"✗ Не удалось скачать Python wheels: {e}")
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
        """Create systemd service file template.
        The actual User= field will be filled in by install.sh at install time,
        since we need the real SSH user (not the ktv system user) to resolve ~ correctly.
        """
        print("[5/7] Creating systemd service template...")
        service_content = """[Unit]
Description=KTV Media Player Daemon
After=network.target

[Service]
Type=simple
User=__DAEMON_USER__
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
        with open(service_file, 'w', encoding='utf-8', newline='\n') as f:
            f.write(service_content)
        print("✓ Systemd service template created")
    
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
    echo -e "${YELLOW}Warning: This package was built for x86_64, continuing anyway...${NC}"
fi

# Install .deb packages
echo -e "${GREEN}[1/8] Installing system packages...${NC}"
cd packages
if ls *.deb 1> /dev/null 2>&1; then
    dpkg -i *.deb 2>/dev/null || apt-get install -f -y
    echo "✓ System packages installed"
else
    echo -e "${YELLOW}Warning: No .deb packages found. VLC should be pre-installed.${NC}"
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

# Check if VLC is available
echo -e "${GREEN}[3/8] Checking VLC...${NC}"
if ! command -v vlc &> /dev/null; then
    echo -e "${RED}Error: VLC is not installed${NC}"
    exit 1
fi
VLC_VERSION=$(vlc --version 2>/dev/null | head -1)
echo "✓ Found $VLC_VERSION"

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
mkdir -p /var/lib/ktv
mkdir -p /var/log/ktv
mkdir -p /etc/ktv

# Create clips folder in user's home directory
if [ "$ORIGINAL_USER" != "root" ]; then
    USER_HOME=$(eval echo "~$ORIGINAL_USER")
    mkdir -p "$USER_HOME/clips"
    chown "$ORIGINAL_USER:ktv" "$USER_HOME/clips"
    chmod 775 "$USER_HOME/clips"
    echo "✓ Created clips directory: $USER_HOME/clips"
fi

# Pre-create log file
touch /var/log/ktv/daemon.log

# Set ownership to the actual user, group ktv
chown -R "$ORIGINAL_USER:ktv" /opt/ktv
chown -R "$ORIGINAL_USER:ktv" /var/lib/ktv
chown -R "$ORIGINAL_USER:ktv" /var/log/ktv
chown -R "$ORIGINAL_USER:ktv" /etc/ktv

chmod -R 775 /var/lib/ktv
chmod -R 775 /var/log/ktv

echo "✓ Directories created with proper permissions"

# Install Python packages
echo -e "${GREEN}[6/8] Installing Python packages...${NC}"

# Check if pip3 is available, install if not
if ! command -v pip3 &> /dev/null; then
    echo "pip3 not found, installing..."
    python3 -m ensurepip --default-pip 2>/dev/null || true
fi

# Install Python packages from wheels to system Python
if [ -d "python_wheels" ] && [ "$(ls -A python_wheels/*.whl 2>/dev/null)" ]; then
    if command -v pip3 &> /dev/null; then
        # Try with --break-system-packages first (needed for Python 3.11+/PEP 668)
        # --force-reinstall ensures clean state on re-installation
        pip3 install --force-reinstall --break-system-packages --no-index --find-links=python_wheels python_wheels/*.whl 2>/dev/null \
            || pip3 install --force-reinstall --no-index --find-links=python_wheels python_wheels/*.whl
        echo "✓ Python packages installed"
    else
        echo -e "${RED}Error: pip3 not available${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}Warning: No Python wheels found${NC}"
fi

# Copy daemon files (clean old files first to avoid stale code)
echo -e "${GREEN}[7/8] Installing daemon...${NC}"
if [ -d "daemon" ]; then
    # Remove old daemon code but preserve any user data
    find /opt/ktv -name '*.py' -delete 2>/dev/null || true
    find /opt/ktv -name '*.pyc' -delete 2>/dev/null || true
    find /opt/ktv -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    
    cp -r daemon/* /opt/ktv/
    echo "✓ Daemon files copied (old code cleaned)"
else
    echo -e "${RED}Error: Daemon files not found${NC}"
    exit 1
fi

# Copy configuration and replace ~ with actual home path
if [ -f "config/config.json" ]; then
    USER_HOME=$(eval echo "~$ORIGINAL_USER")
    sed "s|~|$USER_HOME|g" config/config.json > /etc/ktv/config.json
    echo "✓ Configuration installed (media path: $USER_HOME)"
fi

# Set permissions on daemon code and data directories
chown -R "$ORIGINAL_USER:ktv" /opt/ktv
chown -R "$ORIGINAL_USER:ktv" /var/lib/ktv
chown -R "$ORIGINAL_USER:ktv" /var/log/ktv
chmod -R 755 /opt/ktv
chmod -R 775 /var/lib/ktv
chmod -R 775 /var/log/ktv

# Install systemd service (set actual user)
echo -e "${GREEN}[8/8] Installing systemd service...${NC}"
if [ -f "systemd/ktv-daemon.service" ]; then
    # Stop old daemon if running
    systemctl stop ktv-daemon.service 2>/dev/null || true
    
    # Replace placeholder with the actual user who will run the daemon
    sed "s/__DAEMON_USER__/$ORIGINAL_USER/" systemd/ktv-daemon.service > /etc/systemd/system/ktv-daemon.service
    echo "✓ Service configured to run as user '$ORIGINAL_USER'"
    
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
   - Check VLC availability
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
- `~/MM/DD/HH-MM/` - Movies storage (in user's home directory)
- `~/clips/` - Clips/playlists storage (in user's home directory)
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
    
    def cleanup(self, clear_cache=False):
        """Clean up build directory (cache is preserved by default)"""
        if self.build_dir.exists():
            shutil.rmtree(self.build_dir)
        if clear_cache and self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            print("✓ Кеш очищен")
    
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
    parser.add_argument('--clear-cache', action='store_true',
                       help='Clear download cache and re-download everything')
    
    args = parser.parse_args()
    
    builder = OfflinePackageBuilder(arch=args.arch, output_dir=args.output)
    
    if args.clear_cache:
        print("Очистка кеша...")
        builder.cleanup(clear_cache=True)
    
    package = builder.build()
    
    if not args.no_cleanup and package:
        print("\nCleaning up build directory...")
        builder.cleanup()
        print("✓ Cleanup complete")
    
    sys.exit(0 if package else 1)

if __name__ == '__main__':
    main()
