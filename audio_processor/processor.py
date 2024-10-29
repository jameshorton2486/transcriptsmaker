import numpy as np
from pydub import AudioSegment
from scipy import signal
import soundfile as sf
import io
import os
import librosa
import noisereduce as nr
from scipy.fftpack import fft, ifft
import logging
import time
import signal as sys_signal
from functools import wraps
import psutil
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from .exceptions import *

# Configure logging with additional metrics
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('audio_processing.log')
    ]
)
logger = logging.getLogger(__name__)

def timeout_handler(signum, frame):
    raise AudioProcessingTimeout("Audio processing operation timed out")

def with_timeout(seconds=300):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            sys_signal.signal(sys_signal.SIGALRM, timeout_handler)
            sys_signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
                sys_signal.alarm(0)
                return result
            except AudioProcessingTimeout:
                logger.error(f"Operation timed out after {seconds} seconds")
                raise
            finally:
                sys_signal.alarm(0)
        return wrapper
    return decorator

def log_memory_usage():
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    logger.info(f"Memory usage: {mem_info.rss / 1024 / 1024:.2f} MB")

def calculate_snr(signal, noise):
    """Calculate Signal-to-Noise Ratio in dB"""
    signal_power = np.mean(signal ** 2)
    noise_power = np.mean(noise ** 2)
    if noise_power == 0:
        return float('inf')
    return 10 * np.log10(signal_power / noise_power)

class AudioProcessor:
    SUPPORTED_FORMATS = {'wav', 'mp3', 'flac', 'mp4'}
    TARGET_SAMPLE_RATE = 16000
    TARGET_DB = -20
    MIN_SAMPLE_RATE = 8000
    MAX_CHANNELS = 2
    CHUNK_SIZE = 50 * 1024 * 1024  # 50MB chunks
    MAX_RETRIES = 3
    
    def __init__(self, file_path):
        self.file_path = file_path
        self._validate_file()
        self.progress = 0
        self.total_chunks = 0
        self.processed_chunks = 0
        
    def _validate_file(self):
        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            raise FileNotFoundError(f"Audio file not found: {self.file_path}")
            
        self.format = self.file_path.split('.')[-1].lower()
        if self.format not in self.SUPPORTED_FORMATS:
            logger.error(f"Unsupported format: {self.format}")
            raise AudioFormatError(f"Unsupported audio format: {self.format}")
            
        # Check file size for chunked processing
        self.file_size = os.path.getsize(self.file_path)
        self.requires_chunking = self.file_size > 100 * 1024 * 1024  # 100MB
        if self.requires_chunking:
            self.total_chunks = (self.file_size + self.CHUNK_SIZE - 1) // self.CHUNK_SIZE
            logger.info(f"File size: {self.file_size / 1024 / 1024:.2f}MB, will be processed in {self.total_chunks} chunks")
    
    def _validate_audio_parameters(self, audio):
        if audio.frame_rate < self.MIN_SAMPLE_RATE:
            raise AudioQualityError(f"Sample rate too low: {audio.frame_rate}Hz (minimum: {self.MIN_SAMPLE_RATE}Hz)")
        
        if audio.channels > self.MAX_CHANNELS:
            raise AudioQualityError(f"Too many channels: {audio.channels} (maximum: {self.MAX_CHANNELS})")
    
    def _process_chunk(self, chunk_data, sample_rate):
        """Process a single chunk of audio data"""
        try:
            # Convert chunk to numpy array
            samples = np.array(chunk_data.get_array_of_samples(), dtype=np.float32)
            samples = samples / (1 << (8 * chunk_data.sample_width - 1))
            
            # Process channels in parallel
            channels = self.split_channels(samples)
            with ThreadPoolExecutor(max_workers=min(len(channels), multiprocessing.cpu_count())) as executor:
                enhanced_channels = list(executor.map(
                    lambda x: self.enhance_audio(x, sample_rate),
                    channels
                ))
            
            # Combine channels if necessary
            if len(enhanced_channels) > 1:
                enhanced_chunk = np.stack(enhanced_channels, axis=1)
            else:
                enhanced_chunk = enhanced_channels[0]
                
            return enhanced_chunk
            
        except Exception as e:
            logger.error(f"Error processing chunk: {str(e)}")
            raise AudioEnhancementError(f"Failed to process chunk: {str(e)}")
        finally:
            # Clear memory
            del samples
            del channels
            log_memory_usage()
            
    @with_timeout(300)
    def process_audio(self):
        """Enhanced processing pipeline with chunked processing and memory management"""
        start_time = time.time()
        logger.info(f"Starting audio processing for file: {self.file_path}")
        log_memory_usage()
        
        try:
            audio = AudioSegment.from_file(self.file_path)
            self._validate_audio_parameters(audio)
            sample_rate = audio.frame_rate
            
            if self.requires_chunking:
                enhanced_chunks = []
                chunk_duration = self.CHUNK_SIZE * 1000 // (audio.frame_rate * audio.sample_width * audio.channels)  # ms
                
                for i in range(0, len(audio), chunk_duration):
                    chunk = audio[i:i + chunk_duration]
                    retry_count = 0
                    
                    while retry_count < self.MAX_RETRIES:
                        try:
                            enhanced_chunk = self._process_chunk(chunk, sample_rate)
                            enhanced_chunks.append(enhanced_chunk)
                            self.processed_chunks += 1
                            self.progress = (self.processed_chunks / self.total_chunks) * 100
                            logger.info(f"Processed chunk {self.processed_chunks}/{self.total_chunks} ({self.progress:.1f}%)")
                            break
                        except Exception as e:
                            retry_count += 1
                            logger.warning(f"Retry {retry_count} for chunk {self.processed_chunks + 1}: {str(e)}")
                            if retry_count == self.MAX_RETRIES:
                                raise
                            time.sleep(1)
                    
                    # Clear memory after each chunk
                    del chunk
                    log_memory_usage()
                
                enhanced_audio = np.concatenate(enhanced_chunks)
                del enhanced_chunks
                
            else:
                enhanced_audio = self._process_chunk(audio, sample_rate)
            
            # Classify background noise
            noise_type = self.classify_background_noise(enhanced_audio, sample_rate)
            
            total_time = time.time() - start_time
            logger.info(f"Total processing time: {total_time:.2f} seconds")
            log_memory_usage()
            
            return enhanced_audio, sample_rate, noise_type
            
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            if isinstance(e, AudioProcessingError):
                raise
            raise AudioEnhancementError(f"Failed to process audio: {str(e)}")
    
    def enhance_audio(self, audio_data, sample_rate):
        """Optimized audio enhancement with adaptive thresholds"""
        try:
            start_time = time.time()
            
            # Calculate initial SNR
            noise_sample = audio_data[:int(sample_rate * 0.1)]  # First 100ms
            initial_snr = calculate_snr(audio_data, noise_sample)
            logger.info(f"Initial SNR: {initial_snr:.2f} dB")
            
            # Adaptive noise reduction threshold based on SNR
            noise_reduction_strength = min(0.75, max(0.3, 1.0 - initial_snr / 30))
            
            # Apply pre-emphasis filter
            pre_emphasis = 0.97
            emphasized_audio = np.append(
                audio_data[0],
                audio_data[1:] - pre_emphasis * audio_data[:-1]
            )
            
            # Optimized FFT-based processing
            fft_size = 2048  # Optimal size for performance
            hop_length = fft_size // 4
            
            # Apply adaptive noise reduction
            cleaned_audio = self.adaptive_noise_reduction(
                emphasized_audio,
                sample_rate,
                noise_reduction_strength
            )
            
            # Apply echo cancellation
            echo_cancelled = self.echo_cancellation(cleaned_audio, sample_rate)
            
            # Apply band-pass filter
            nyquist = sample_rate // 2
            low_cutoff = 80
            high_cutoff = 8000
            b, a = signal.butter(
                N=4,
                Wn=[low_cutoff/nyquist, high_cutoff/nyquist],
                btype='band'
            )
            filtered_audio = signal.filtfilt(b, a, echo_cancelled)
            
            # Calculate final SNR
            final_snr = calculate_snr(filtered_audio, noise_sample)
            logger.info(f"Final SNR: {final_snr:.2f} dB (improvement: {final_snr - initial_snr:.2f} dB)")
            
            processing_time = time.time() - start_time
            logger.info(f"Audio enhancement completed in {processing_time:.2f} seconds")
            return filtered_audio
            
        except Exception as e:
            logger.error(f"Error enhancing audio: {str(e)}")
            raise AudioEnhancementError(f"Failed to enhance audio: {str(e)}")
    
    def adaptive_noise_reduction(self, audio_data, sample_rate, strength=0.75):
        """Apply adaptive noise reduction with enhanced parameters"""
        try:
            start_time = time.time()
            noise_clip = audio_data[:int(sample_rate)]
            reduced_noise = nr.reduce_noise(
                y=audio_data,
                y_noise=noise_clip,
                sr=sample_rate,
                stationary=False,
                prop_decrease=strength
            )
            logger.info(f"Noise reduction completed in {time.time() - start_time:.2f} seconds")
            return reduced_noise
        except Exception as e:
            logger.error(f"Error in noise reduction: {str(e)}")
            raise AudioEnhancementError(f"Failed to reduce noise: {str(e)}")
    
    def save_enhanced_audio(self, audio_data, sample_rate, output_path):
        """Save enhanced audio with error handling"""
        try:
            start_time = time.time()
            sf.write(output_path, audio_data, sample_rate)
            logger.info(f"Enhanced audio saved to {output_path} in {time.time() - start_time:.2f} seconds")
        except Exception as e:
            logger.error(f"Error saving enhanced audio: {str(e)}")
            raise AudioEnhancementError(f"Failed to save enhanced audio: {str(e)}")
