"""
API Server for KTV daemon
Handles commands from Windows GUI client via TCP socket
"""

import socket
import json
import threading
import logging
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)


class APIServer:
    """TCP socket server for handling remote commands"""
    
    def __init__(self, host: str = '0.0.0.0', port: int = 8888):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.handlers: Dict[str, Callable] = {}
        self.server_thread = None
    
    def register_handler(self, command: str, handler: Callable):
        """Register a command handler"""
        self.handlers[command] = handler
        logger.debug(f"Registered handler for command: {command}")
    
    def start(self):
        """Start the API server"""
        if self.running:
            logger.warning("API server already running")
            return
        
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.running = True
            
            self.server_thread = threading.Thread(target=self._accept_connections, daemon=True)
            self.server_thread.start()
            
            logger.info(f"API server started on {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            raise
    
    def stop(self):
        """Stop the API server"""
        if not self.running:
            return
        
        self.running = False
        
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        
        logger.info("API server stopped")
    
    def _accept_connections(self):
        """Accept incoming connections"""
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                logger.debug(f"Client connected from {address}")
                
                # Handle client in a separate thread
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()
                
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")
    
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """Handle a client connection"""
        try:
            # Set timeout for client operations
            client_socket.settimeout(30.0)
            
            # Receive data
            data = b''
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
            
            if not data:
                logger.warning(f"No data received from {address}")
                return
            
            # Parse request
            try:
                request = json.loads(data.decode('utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON from {address}: {e}")
                response = self._create_error_response("Invalid JSON")
                self._send_response(client_socket, response)
                return
            
            # Process command
            response = self._process_command(request)
            
            # Send response
            self._send_response(client_socket, response)
            
        except socket.timeout:
            logger.warning(f"Client {address} timed out")
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
        finally:
            try:
                client_socket.close()
            except:
                pass
            logger.debug(f"Client {address} disconnected")
    
    def _process_command(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process a command request"""
        command = request.get('command')
        params = request.get('params', {})
        
        if not command:
            return self._create_error_response("Missing 'command' field")
        
        if command not in self.handlers:
            return self._create_error_response(f"Unknown command: {command}")
        
        try:
            handler = self.handlers[command]
            result = handler(params)
            
            return {
                'success': True,
                'command': command,
                'result': result
            }
        except Exception as e:
            logger.error(f"Error executing command '{command}': {e}", exc_info=True)
            return self._create_error_response(str(e), command=command)
    
    def _create_error_response(self, error_message: str, command: str = None) -> Dict[str, Any]:
        """Create an error response"""
        response = {
            'success': False,
            'error': error_message
        }
        if command:
            response['command'] = command
        return response
    
    def _send_response(self, client_socket: socket.socket, response: Dict[str, Any]):
        """Send response to client"""
        try:
            response_json = json.dumps(response)
            client_socket.sendall(response_json.encode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending response: {e}")


# Example usage and testing
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    server = APIServer()
    
    # Register some test handlers
    def handle_ping(params):
        return {'pong': True, 'timestamp': params.get('timestamp')}
    
    def handle_status(params):
        return {
            'daemon_running': True,
            'player_status': 'idle',
            'current_file': None
        }
    
    server.register_handler('ping', handle_ping)
    server.register_handler('status', handle_status)
    
    try:
        server.start()
        print("API server running. Press Ctrl+C to stop...")
        
        # Keep the main thread alive
        import time
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.stop()
