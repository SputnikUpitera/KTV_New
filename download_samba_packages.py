"""
Download samba and all its dependencies for Ubuntu 20.04 Focal (offline install).
Resolves the full dependency tree from the Ubuntu archive Packages index.
"""
import gzip
import urllib.request
import re
import os
import sys
from pathlib import Path

ARCH = 'amd64'
DISTRO = 'focal'
MIRROR = 'http://archive.ubuntu.com/ubuntu'

REPOS = [
    f'{MIRROR}/dists/{DISTRO}/main/binary-{ARCH}/Packages.gz',
    f'{MIRROR}/dists/{DISTRO}-updates/main/binary-{ARCH}/Packages.gz',
    f'{MIRROR}/dists/{DISTRO}-security/main/binary-{ARCH}/Packages.gz',
]

BASE_SYSTEM_PACKAGES = {
    'adduser', 'apt', 'base-files', 'base-passwd', 'bash', 'bsdutils',
    'coreutils', 'dash', 'debconf', 'debianutils', 'diffutils', 'dpkg',
    'e2fsprogs', 'fdisk', 'findutils', 'gcc-10-base', 'grep', 'gzip',
    'hostname', 'init', 'init-system-helpers', 'libacl1', 'libattr1',
    'libaudit-common', 'libaudit1', 'libblkid1', 'libbz2-1.0', 'libc-bin',
    'libc6', 'libcap-ng0', 'libcap2', 'libcom-err2', 'libcrypt1',
    'libdb5.3', 'libdbus-1-3', 'libdebconfclient0', 'libelf1', 'libexpat1',
    'libext2fs2', 'libffi7', 'libgcc-s1', 'libgcrypt20', 'libgmp10',
    'libgnutls30', 'libgpg-error0', 'libgssapi-krb5-2', 'libhogweed5',
    'libidn2-0', 'libk5crypto3', 'libkeyutils1', 'libkrb5-3',
    'libkrb5support0', 'liblz4-1', 'liblzma5', 'libmount1', 'libncurses6',
    'libncursesw6', 'libnettle7', 'libnss-systemd', 'libp11-kit0',
    'libpam-modules', 'libpam-modules-bin', 'libpam-runtime', 'libpam0g',
    'libpcre2-8-0', 'libpcre3', 'libprocps8', 'libreadline8',
    'libseccomp2', 'libselinux1', 'libsemanage-common', 'libsemanage1',
    'libsepol1', 'libsmartcols1', 'libss2', 'libssl1.1', 'libstdc++6',
    'libsystemd0', 'libtasn1-6', 'libtinfo6', 'libudev1', 'libunistring2',
    'libuuid1', 'libzstd1', 'login', 'lsb-base', 'mawk', 'mount',
    'ncurses-base', 'ncurses-bin', 'passwd', 'perl-base', 'procps',
    'readline-common', 'sed', 'sensible-utils', 'sysvinit-utils', 'tar',
    'tzdata', 'util-linux', 'zlib1g',
    'python3', 'python3-minimal', 'python3.8', 'python3.8-minimal',
    'libpython3.8-minimal', 'libpython3.8-stdlib', 'libpython3-stdlib',
    'libpython3.8', 'python3-lib2to3', 'python3-distutils',
    'libmpdec2', 'libsqlite3-0', 'mime-support', 'media-types',
    'python3-pkg-resources', 'python3-setuptools',
    'dbus', 'systemd', 'udev', 'openssl', 'ca-certificates',
    'libapparmor1', 'libcap2-bin', 'libip4tc2', 'libip6tc2',
    'libnss3', 'libnspr4',
}

VIRTUAL_PROVIDES = {
    'python3-crypto': 'python3-pycryptodome',
    'default-dbus-system-bus': None,
    'logrotate': None,
    'samba-ad-dc': None,
}


def log(msg):
    print(msg, flush=True)


def fetch_url(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=timeout).read()


def fetch_package_index():
    packages = {}
    for url in REPOS:
        log(f"  Fetching {url}...")
        try:
            data = fetch_url(url, timeout=120)
        except Exception as e:
            log(f"  WARNING: Failed: {e}")
            continue

        text = gzip.decompress(data).decode('utf-8')
        current = {}

        for line in text.split('\n'):
            if line == '':
                name = current.get('Package')
                if name:
                    if name not in packages:
                        packages[name] = current
                    else:
                        old_ver = packages[name].get('Version', '')
                        new_ver = current.get('Version', '')
                        if new_ver > old_ver:
                            packages[name] = current
                current = {}
            elif line.startswith(' ') or line.startswith('\t'):
                pass
            elif ':' in line:
                key, _, value = line.partition(':')
                current[key.strip()] = value.strip()

        if current.get('Package'):
            packages[current['Package']] = current

    return packages


def parse_deps(dep_string):
    if not dep_string:
        return []
    result = []
    for item in dep_string.split(','):
        item = item.strip()
        alternatives = []
        for alt in item.split('|'):
            alt = alt.strip()
            match = re.match(r'^(\S+)', alt)
            if match:
                name = match.group(1)
                if ':' not in name:
                    alternatives.append(name)
        if alternatives:
            result.append(alternatives)
    return result


def resolve_all(packages, root_name):
    needed = []
    visited = set()
    queue = [root_name]

    while queue:
        pkg_name = queue.pop(0)
        if pkg_name in visited:
            continue
        visited.add(pkg_name)
        if pkg_name in BASE_SYSTEM_PACKAGES:
            continue
        if pkg_name in VIRTUAL_PROVIDES:
            real = VIRTUAL_PROVIDES[pkg_name]
            if real and real not in visited:
                queue.append(real)
            continue
        if pkg_name not in packages:
            continue

        pkg = packages[pkg_name]
        needed.append(pkg_name)

        deps_str = pkg.get('Depends', '')
        pre_str = pkg.get('Pre-Depends', '')
        all_deps = parse_deps(deps_str) + parse_deps(pre_str)

        for alternatives in all_deps:
            resolved = False
            for alt in alternatives:
                if alt in visited or alt in BASE_SYSTEM_PACKAGES:
                    resolved = True
                    break
                if alt in packages:
                    queue.append(alt)
                    resolved = True
                    break
                if alt in VIRTUAL_PROVIDES:
                    real = VIRTUAL_PROVIDES[alt]
                    if real:
                        queue.append(real)
                    resolved = True
                    break
            if not resolved and alternatives:
                queue.append(alternatives[0])

    return needed


def download_file(url, dest, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=timeout)
    with open(dest, 'wb') as f:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            f.write(chunk)


def create_install_script(output_dir):
    content = (
        '#!/bin/bash\n'
        'set -e\n'
        '\n'
        'echo "=== Installing Samba (offline) ==="\n'
        '\n'
        'cd "$(dirname "$0")"\n'
        '\n'
        'if command -v smbd &>/dev/null && systemctl is-active --quiet smbd 2>/dev/null; then\n'
        '    echo "Samba is already installed and running."\n'
        '    read -p "Reinstall? [y/N] " answer\n'
        '    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then\n'
        '        exit 0\n'
        '    fi\n'
        'fi\n'
        '\n'
        'echo "[1/4] Installing packages..."\n'
        'sudo dpkg -i --force-depends *.deb 2>&1 || true\n'
        'sudo apt-get install -f -y 2>/dev/null || true\n'
        'echo "Done."\n'
        '\n'
        'echo "[2/4] Configuring Samba share..."\n'
        'if [ -n "$SUDO_USER" ]; then\n'
        '    ACTUAL_USER="$SUDO_USER"\n'
        'else\n'
        '    ACTUAL_USER="$(whoami)"\n'
        'fi\n'
        'USER_HOME=$(eval echo "~$ACTUAL_USER")\n'
        'SHARE_DIR="$USER_HOME"\n'
        '\n'
        'if ! grep -q "\\[KTV\\]" /etc/samba/smb.conf 2>/dev/null; then\n'
        '    cat >> /etc/samba/smb.conf <<SMBEOF\n'
        '\n'
        '[KTV]\n'
        '   comment = KTV Media Files\n'
        '   path = $SHARE_DIR\n'
        '   browseable = yes\n'
        '   read only = no\n'
        '   guest ok = no\n'
        '   valid users = $ACTUAL_USER\n'
        '   create mask = 0775\n'
        '   directory mask = 0775\n'
        'SMBEOF\n'
        '    echo "Share [KTV] added -> path=$SHARE_DIR"\n'
        'else\n'
        '    echo "Share [KTV] already exists in smb.conf"\n'
        'fi\n'
        '\n'
        'echo "[3/4] Setting Samba password for $ACTUAL_USER..."\n'
        'sudo smbpasswd -a "$ACTUAL_USER"\n'
        '\n'
        'echo "[4/4] Starting Samba..."\n'
        'sudo systemctl enable smbd nmbd\n'
        'sudo systemctl restart smbd nmbd\n'
        '\n'
        'if systemctl is-active --quiet smbd; then\n'
        '    IP=$(hostname -I | awk \'{print $1}\')\n'
        '    echo ""\n'
        '    echo "Samba is running!"\n'
        '    echo "Windows Explorer: \\\\\\\\$IP\\\\KTV"\n'
        '    echo "User: $ACTUAL_USER"\n'
        'else\n'
        '    echo "ERROR: smbd failed to start."\n'
        '    echo "Check: sudo journalctl -u smbd -n 20"\n'
        '    exit 1\n'
        'fi\n'
    )
    script_path = output_dir / 'install_samba.sh'
    with open(script_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)


def main():
    output_dir = Path(__file__).parent / 'samba_packages'
    output_dir.mkdir(exist_ok=True)

    log("=== Samba Offline Package Downloader (Ubuntu 20.04 Focal) ===\n")

    log("[1/3] Building package database...")
    packages = fetch_package_index()
    log(f"  Total packages in index: {len(packages)}\n")

    if 'samba' not in packages:
        log("ERROR: 'samba' not found in package index!")
        sys.exit(1)

    log(f"  Samba version: {packages['samba'].get('Version', '?')}\n")

    log("[2/3] Resolving dependency tree...")
    needed = resolve_all(packages, 'samba')
    log(f"  Packages to download: {len(needed)}\n")

    total_size = 0
    download_list = []
    for name in needed:
        pkg = packages[name]
        size = int(pkg.get('Size', 0))
        total_size += size
        filename = os.path.basename(pkg.get('Filename', ''))
        download_list.append((name, pkg, filename, size))
        log(f"  {name:40s} {size // 1024:>6d} KB")

    log(f"\n  Total: {total_size / 1024 / 1024:.1f} MB\n")

    log("[3/3] Downloading packages...")
    for i, (name, pkg, filename, size) in enumerate(download_list, 1):
        local_path = output_dir / filename
        if local_path.exists() and local_path.stat().st_size == size:
            log(f"  [{i}/{len(download_list)}] Cached: {filename}")
            continue

        url = f"{MIRROR}/{pkg['Filename']}"
        log(f"  [{i}/{len(download_list)}] Downloading: {filename}...")
        try:
            download_file(url, local_path, timeout=120)
            log(f"  [{i}/{len(download_list)}] OK ({size // 1024} KB)")
        except Exception as e:
            log(f"  [{i}/{len(download_list)}] ERROR: {e}")
            if local_path.exists():
                local_path.unlink()

    create_install_script(output_dir)

    log(f"\nDone! Files saved to: {output_dir.resolve()}")
    log(f"Total: {len(download_list)} .deb + install_samba.sh")
    log("\nUsage:")
    log("  1. Copy 'samba_packages' folder to USB drive")
    log("  2. On the nettop:")
    log("     cd /media/<user>/<usb>/samba_packages")
    log("     chmod +x install_samba.sh")
    log("     sudo bash install_samba.sh")


if __name__ == '__main__':
    main()
