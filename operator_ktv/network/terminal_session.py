"""
SSH Terminal session manager
Manages persistent SSH shell sessions for terminal widget
"""

import paramiko
import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class TerminalSession:
    """Manages an interactive SSH shell session"""
    
    def __init__(self, ssh_client: paramiko.SSHClient):
        self.ssh_client = ssh_client
        self.channel: Optional[paramiko.Channel] = None
        self.running = False
        self.output_callback: Optional[Callable[[str], None]] = None
        self.read_thread: Optional[threading.Thread] = None
    
    def start(self, output_callback: Callable[[str], None]) -> bool:
        """Start interactive shell session"""
        try:
            logger.info("Starting terminal session")
            self.output_callback = output_callback
            
            # Open a channel for interactive shell
            self.channel = self.ssh_client.invoke_shell(
                term='xterm',
                width=80,
                height=24
            )
            
            # Set channel to non-blocking
            self.channel.setblocking(0)
            
            # Start background thread to read output
            self.running = True
            self.read_thread = threading.Thread(target=self._read_output, daemon=True)
            self.read_thread.start()
            
            logger.info("Terminal session started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start terminal session: {e}", exc_info=True)
            return False
    
    def _read_output(self):
        """Background thread to continuously read shell output"""
        import time
        
        while self.running and self.channel:
            try:
                if self.channel.recv_ready():
                    data = self.channel.recv(4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        if self.output_callback:
                            self.output_callback(text)
                
                # Check for stderr as well
                if self.channel.recv_stderr_ready():
                    data = self.channel.recv_stderr(4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        if self.output_callback:
                            self.output_callback(text)
                
                # Small delay to prevent busy waiting
                time.sleep(0.01)
                
            except Exception as e:
                if self.running:
                    logger.error(f"Error reading terminal output: {e}")
                break
    
    def send_input(self, text: str):
        """Send input to the shell"""
        if self.channel and not self.channel.closed:
            try:
                self.channel.send(text.encode('utf-8'))
            except Exception as e:
                logger.error(f"Failed to send input: {e}")
    
    def resize(self, width: int, height: int):
        """Resize the terminal"""
        if self.channel and not self.channel.closed:
            try:
                self.channel.resize_pty(width=width, height=height)
            except Exception as e:
                logger.error(f"Failed to resize terminal: {e}")
    
    def stop(self):
        """Stop the terminal session"""
        logger.info("Stopping terminal session")
        self.running = False
        
        if self.channel:
            try:
                self.channel.close()
            except:
                pass
            self.channel = None
        
        if self.read_thread:
            # Give thread a moment to finish
            self.read_thread.join(timeout=1.0)
            self.read_thread = None
        
        logger.info("Terminal session stopped")
    
    def is_active(self) -> bool:
        """Check if session is active"""
        return (self.running and 
                self.channel is not None and 
                not self.channel.closed)
