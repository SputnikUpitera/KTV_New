"""
Media player wrapper built on top of the ordinary VLC executable.
"""

import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class Player:
    """VLC process wrapper used by the daemon."""

    def __init__(
        self,
        vlc_path: str = '/usr/bin/vlc',
        display: str = ':0',
        avcodec_hw: str = 'any',
        video_output: str = 'xcb_x11',
        avcodec_threads: int = 2,
        file_caching_ms: int = 1000,
        network_caching_ms: int = 1500,
        enable_frame_skip: bool = True,
        extra_vlc_args: Optional[List[str]] = None,
    ):
        self.vlc_path = vlc_path
        self.display = display
        self.avcodec_hw = (avcodec_hw or '').strip()
        self.video_output = (video_output or '').strip()
        self.avcodec_threads = max(0, int(avcodec_threads))
        self.file_caching_ms = max(0, int(file_caching_ms))
        self.network_caching_ms = max(0, int(network_caching_ms))
        self.enable_frame_skip = enable_frame_skip
        self.extra_vlc_args = list(extra_vlc_args or [])
        self.process: Optional[subprocess.Popen] = None
        self.current_file: Optional[str] = None
        self.is_playing = False
        self.is_paused = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.playback_ended_callback: Optional[Callable] = None
        self.callback_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.playback_generation = 0
        self.stop_requested_generation: Optional[int] = None

    def set_playback_ended_callback(self, callback: Optional[Callable[[str], None]] = None):
        """Set callback to be called when playback ends."""
        with self.callback_lock:
            self.playback_ended_callback = callback

    def play(self, filepath: str, fullscreen: bool = True) -> bool:
        """Play a video file with the ordinary VLC executable."""
        if self.has_media():
            logger.info("Stopping current playback before starting new one")
            self.stop()

        if not Path(filepath).exists():
            logger.error("File not found: %s", filepath)
            return False

        logger.info("Starting VLC process playback: %s", filepath)
        return self._start_playback(filepath, fullscreen)

    def stop(self) -> bool:
        """Stop current playback."""
        if not self.has_media():
            return False

        try:
            with self.state_lock:
                generation = self.playback_generation
                stopped_file = self.current_file
                process = self.process
                self.stop_requested_generation = generation

            logger.info("Stopping playback")
            self._terminate_process(process)
            self._finalize_playback(generation, invoke_callback=False)
            logger.info("Playback stopped: %s", Path(stopped_file).name if stopped_file else 'unknown')
            return True
        except Exception as exc:
            logger.error("Error stopping playback: %s", exc, exc_info=True)
            return False

    def pause(self) -> bool:
        """Pause the current VLC process."""
        with self.state_lock:
            if not self.current_file or self.is_paused or not self.process:
                return False
            process = self.process

        pause_signal = getattr(signal, 'SIGSTOP', None)
        if pause_signal is None or not self._send_process_signal(process, pause_signal):
            return False

        with self.state_lock:
            self.is_paused = True
            self.is_playing = False
        logger.info("Playback paused")
        return True

    def resume(self) -> bool:
        """Resume a paused VLC process."""
        with self.state_lock:
            if not self.current_file or not self.is_paused or not self.process:
                return False
            process = self.process

        resume_signal = getattr(signal, 'SIGCONT', None)
        if resume_signal is None or not self._send_process_signal(process, resume_signal):
            return False

        with self.state_lock:
            self.is_paused = False
            self.is_playing = True
        logger.info("Playback resumed")
        return True

    def get_status(self) -> dict:
        """Get current player status."""
        with self.state_lock:
            current_file = self.current_file
            return {
                'is_playing': self.is_playing,
                'is_paused': self.is_paused,
                'can_pause': current_file is not None,
                'current_file': current_file,
                'filename': Path(current_file).name if current_file else None
            }

    def is_busy(self) -> bool:
        """Check if player currently has media loaded."""
        return self.has_media()

    def has_media(self) -> bool:
        """Check whether a media item is currently loaded."""
        with self.state_lock:
            process = self.process
            if self.current_file is None or process is None:
                return False
            return process.poll() is None

    def _start_playback(self, filepath: str, fullscreen: bool) -> bool:
        """Start VLC as a subprocess and monitor it until exit."""
        generation = None
        try:
            command = self._build_command(filepath, fullscreen)
            env = self._build_environment()

            with self.state_lock:
                self.playback_generation += 1
                generation = self.playback_generation
                self.stop_requested_generation = None
                self.current_file = filepath
                self.is_playing = False
                self.is_paused = False

            logger.info("Launching VLC command: %s", command)
            process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                start_new_session=(os.name != 'nt'),
                text=True,
            )

            with self.state_lock:
                if generation != self.playback_generation:
                    self._terminate_process(process)
                    return False
                self.process = process
                self.is_playing = True

            time.sleep(0.25)
            if process.poll() is not None:
                stderr = self._read_process_stderr(process)
                logger.error("VLC exited during startup for %s: %s", filepath, stderr)
                self._finalize_playback(generation, invoke_callback=False)
                return False

            self.monitor_thread = threading.Thread(
                target=self._monitor_playback,
                args=(generation, filepath, process),
                daemon=True
            )
            self.monitor_thread.start()

            logger.info("Playback started via VLC process: %s", Path(filepath).name)
            return True
        except Exception as exc:
            logger.error("Failed to start playback: %s", exc, exc_info=True)
            if generation is not None:
                self._finalize_playback(generation, invoke_callback=False)
            else:
                self._clear_state()
            return False

    def _monitor_playback(self, generation: int, filepath: str, process: subprocess.Popen):
        """Wait for VLC process exit and finalize playback state."""
        return_code = process.wait()
        with self.state_lock:
            invoke_callback = (
                generation == self.playback_generation
                and self.stop_requested_generation != generation
            )

        if return_code == 0:
            logger.info("Playback finished normally: %s", Path(filepath).name)
        else:
            stderr = self._read_process_stderr(process)
            logger.error(
                "VLC exited with code %s for %s: %s",
                return_code,
                Path(filepath).name,
                stderr,
            )
        self._finalize_playback(generation, invoke_callback=invoke_callback)

    def _build_environment(self) -> dict:
        """Build environment for VLC process."""
        env = os.environ.copy()
        env['DISPLAY'] = self.display
        if not env.get('XDG_RUNTIME_DIR'):
            runtime_dir = f"/run/user/{os.getuid()}" if hasattr(os, 'getuid') else ''
            if runtime_dir and Path(runtime_dir).exists():
                env['XDG_RUNTIME_DIR'] = runtime_dir
        return env

    def _build_command(self, filepath: str, fullscreen: bool) -> List[str]:
        """Build VLC command-line arguments."""
        args = [
            self.vlc_path,
            '--quiet',
            '--no-video-title-show',
            '--no-osd',
            '--no-playlist-enqueue',
            '--play-and-exit',
            f'--file-caching={self.file_caching_ms}',
            f'--network-caching={self.network_caching_ms}',
        ]

        if fullscreen:
            args.append('--fullscreen')

        avcodec_hw = self.avcodec_hw.lower()
        if avcodec_hw in {'none', 'off', 'disabled', 'false', 'software'}:
            args.append('--avcodec-hw=none')
        elif avcodec_hw:
            args.append(f'--avcodec-hw={self.avcodec_hw}')

        if self.video_output:
            args.append(f'--vout={self.video_output}')

        if self.avcodec_threads > 0:
            args.append(f'--avcodec-threads={self.avcodec_threads}')

        if self.enable_frame_skip:
            args.extend(['--drop-late-frames', '--skip-frames'])

        args.extend(self.extra_vlc_args)
        args.append(str(filepath))
        return args

    def _terminate_process(self, process: Optional[subprocess.Popen]):
        """Terminate a VLC process and its process group when possible."""
        if process is None or process.poll() is not None:
            return

        try:
            if os.name != 'nt':
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=5)
            return
        except subprocess.TimeoutExpired:
            logger.warning("VLC did not exit after terminate; killing")
        except ProcessLookupError:
            return

        try:
            if os.name != 'nt':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=2)
        except Exception as exc:
            logger.warning("Could not kill VLC process: %s", exc)

    def _send_process_signal(self, process: subprocess.Popen, sig: int) -> bool:
        """Send a signal to VLC's process group."""
        if process.poll() is not None:
            return False
        try:
            if os.name != 'nt':
                os.killpg(process.pid, sig)
            else:
                process.send_signal(sig)
            return True
        except Exception as exc:
            logger.error("Could not send signal %s to VLC process: %s", sig, exc)
            return False

    def _read_process_stderr(self, process: subprocess.Popen) -> str:
        """Read any buffered VLC stderr without making failure reporting noisy."""
        stderr = getattr(process, 'stderr', None)
        if not stderr:
            return ""
        try:
            return stderr.read()[-2000:].strip()
        except Exception:
            return ""

    def _finalize_playback(self, generation: int, invoke_callback: bool):
        """Clear state for a finished playback session."""
        with self.state_lock:
            if generation != self.playback_generation:
                return
            filepath = self.current_file
            self.process = None
            self.current_file = None
            self.is_playing = False
            self.is_paused = False
            self.stop_requested_generation = None

        if invoke_callback and filepath:
            with self.callback_lock:
                callback = self.playback_ended_callback
            if callback:
                try:
                    callback(filepath)
                except Exception as exc:
                    logger.error("Error in playback ended callback: %s", exc, exc_info=True)

    def _clear_state(self):
        """Reset in-memory playback state."""
        with self.state_lock:
            self.process = None
            self.current_file = None
            self.is_playing = False
            self.is_paused = False
            self.stop_requested_generation = None


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    player = Player()

    def on_playback_ended(filepath):
        print(f"Callback: Playback ended for {filepath}")

    player.set_playback_ended_callback(on_playback_ended)

    test_file = "/opt/ktv/media/test.mp4"
    if Path(test_file).exists():
        print(f"Testing playback with {test_file}")
        player.play(test_file)
        time.sleep(5)
        player.stop()
    else:
        print(f"Test file not found: {test_file}")

    print(f"Status: {player.get_status()}")
