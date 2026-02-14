#!/usr/bin/env python3
"""
Simple log viewer for OperatorKTV
Shows the last N lines of the log file
"""

import sys
from pathlib import Path
import argparse


def view_logs(lines=100, follow=False):
    """View log file"""
    log_file = Path.home() / '.operatorktv' / 'operator_ktv.log'
    
    if not log_file.exists():
        print(f"Log file not found: {log_file}")
        print("Run the application first to create logs.")
        return
    
    print(f"Log file: {log_file}")
    print(f"Size: {log_file.stat().st_size / 1024:.2f} KB")
    print("=" * 80)
    
    if follow:
        # Follow mode (like tail -f)
        print("Following log file (Press Ctrl+C to stop)...\n")
        import time
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # Go to end
            f.seek(0, 2)
            
            try:
                while True:
                    line = f.readline()
                    if line:
                        print(line, end='')
                    else:
                        time.sleep(0.1)
            except KeyboardInterrupt:
                print("\nStopped following log file.")
    else:
        # Show last N lines
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
            
            print('\n'.join(last_lines))
            
            if len(all_lines) > lines:
                print(f"\n... showing last {lines} of {len(all_lines)} lines")
            else:
                print(f"\n... {len(all_lines)} lines total")


def main():
    parser = argparse.ArgumentParser(description='View OperatorKTV logs')
    parser.add_argument('-n', '--lines', type=int, default=100,
                       help='Number of lines to show (default: 100)')
    parser.add_argument('-f', '--follow', action='store_true',
                       help='Follow log file (like tail -f)')
    parser.add_argument('--clear', action='store_true',
                       help='Clear the log file')
    
    args = parser.parse_args()
    
    if args.clear:
        log_file = Path.home() / '.operatorktv' / 'operator_ktv.log'
        if log_file.exists():
            log_file.unlink()
            print(f"Log file cleared: {log_file}")
        else:
            print("Log file does not exist")
        return
    
    view_logs(lines=args.lines, follow=args.follow)


if __name__ == '__main__':
    main()
