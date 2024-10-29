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
from .exceptions import *

# Configure logging
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
            # Set the timeout handler
            sys_signal.signal(sys_signal.SIGALRM, timeout_handler)
            sys_signal.alarm(seconds)
            try:
                result = func(*args, **kwargs)
                sys_signal.alarm(0)  # Disable the alarm
                return result
            except AudioProcessingTimeout:
                logger.error(f"Operation timed out after {seconds} seconds")
                raise
            finally:
                sys_signal.alarm(0)  # Ensure alarm is disabled
        return wrapper
    return decorator

class AudioProcessor:
    SUPPORTED_FORMATS = {'wav', 'mp3', 'flac', 'mp4'}
    TARGET_SAMPLE_RATE = 16000
    TARGET_DB = -20
    MIN_SAMPLE_RATE = 8000
    MAX_CHANNELS = 2
    
    def __init__(self, file_path):
        """Initialize audio processor with input validation."""
        self.file_path = file_path
        self._validate_file()
        
    def _validate_file(self):
        """Validate audio file existence and format."""
        if not os.path.exists(self.file_path):
            logger.error(f"File not found: {self.file_path}")
            raise FileNotFoundError(f"Audio file not found: {self.file_path}")
            
        self.format = self.file_path.split('.')[-1].lower()
        if self.format not in self.SUPPORTED_FORMATS:
            logger.error(f"Unsupported format: {self.format}")
            raise AudioFormatError(f"Unsupported audio format: {self.format}")
    
    def _validate_audio_parameters(self, audio):
        """Validate audio parameters meet quality requirements."""
        if audio.frame_rate < self.MIN_SAMPLE_RATE:
            raise AudioQualityError(f"Sample rate too low: {audio.frame_rate}Hz (minimum: {self.MIN_SAMPLE_RATE}Hz)")
        
        if audio.channels > self.MAX_CHANNELS:
            raise AudioQualityError(f"Too many channels: {audio.channels} (maximum: {self.MAX_CHANNELS})")
            
    @with_timeout(300)  # 5 minutes timeout
    def process_audio(self):
        """Main processing pipeline for audio enhancement with timing information."""
        start_time = time.time()
        logger.info(f"Starting audio processing for file: {self.file_path}")
        
        try:
            # Load and normalize audio
            audio = self.normalize_audio()
            logger.info(f"Audio loaded and normalized in {time.time() - start_time:.2f} seconds")
            
            # Convert to numpy array for advanced processing
            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / (1 << (8 * audio.sample_width - 1))
            sample_rate = audio.frame_rate
            
            # Apply channel separation if stereo
            channels = self.split_channels(samples)
            logger.info(f"Channel separation completed in {time.time() - start_time:.2f} seconds")
            
            # Apply audio enhancement
            enhanced_channels = [self.enhance_audio(channel, sample_rate) for channel in channels]
            logger.info(f"Audio enhancement completed in {time.time() - start_time:.2f} seconds")
            
            # Combine channels if necessary
            if len(enhanced_channels) > 1:
                enhanced_audio = np.stack(enhanced_channels, axis=1)
            else:
                enhanced_audio = enhanced_channels[0]
                
            # Classify background noise
            noise_type = self.classify_background_noise(enhanced_audio, sample_rate)
            logger.info(f"Background noise classification completed in {time.time() - start_time:.2f} seconds")
                
            total_time = time.time() - start_time
            logger.info(f"Total processing time: {total_time:.2f} seconds")
            
            return enhanced_audio, sample_rate, noise_type
            
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            if isinstance(e, AudioProcessingError):
                raise
            raise AudioEnhancementError(f"Failed to process audio: {str(e)}")
            
    @with_timeout(60)
    def normalize_audio(self):
        """Normalize audio with input validation."""
        try:
            audio = AudioSegment.from_file(self.file_path)
            self._validate_audio_parameters(audio)
            
            # Convert to mono if needed
            if audio.channels > 2:
                audio = audio.set_channels(2)
                logger.info("Converted audio to stereo")
                
            # Normalize sample rate
            if audio.frame_rate != self.TARGET_SAMPLE_RATE:
                audio = audio.set_frame_rate(self.TARGET_SAMPLE_RATE)
                logger.info(f"Normalized sample rate to {self.TARGET_SAMPLE_RATE}Hz")
            
            # Normalize volume
            change_in_dbfs = self.TARGET_DB - audio.dBFS
            normalized_audio = audio.apply_gain(change_in_dbfs)
            logger.info(f"Normalized audio volume to {self.TARGET_DB}dB")
            
            return normalized_audio
            
        except Exception as e:
            logger.error(f"Error normalizing audio: {str(e)}")
            raise AudioEnhancementError(f"Failed to normalize audio: {str(e)}")

    def split_channels(self, samples):
        """Split stereo audio into separate channels."""
        try:
            if len(samples.shape) > 1:
                return [samples[:, i] for i in range(samples.shape[1])]
            return [samples]
        except Exception as e:
            logger.error(f"Error splitting channels: {str(e)}")
            raise AudioEnhancementError(f"Failed to split audio channels: {str(e)}")

    @with_timeout(120)
    def adaptive_noise_reduction(self, audio_data, sample_rate):
        """Apply adaptive noise reduction with enhanced parameters."""
        try:
            start_time = time.time()
            # Get noise profile from first 1000ms
            noise_clip = audio_data[:int(sample_rate)]
            reduced_noise = nr.reduce_noise(
                y=audio_data,
                y_noise=noise_clip,
                sr=sample_rate,
                stationary=False,
                prop_decrease=0.75
            )
            logger.info(f"Noise reduction completed in {time.time() - start_time:.2f} seconds")
            return reduced_noise
        except Exception as e:
            logger.error(f"Error in noise reduction: {str(e)}")
            raise AudioEnhancementError(f"Failed to reduce noise: {str(e)}")

    @with_timeout(60)
    def echo_cancellation(self, audio_data, sample_rate):
        """Apply echo cancellation with improved error handling."""
        try:
            start_time = time.time()
            delay = int(0.05 * sample_rate)
            decay = 0.3
            
            echo = np.zeros_like(audio_data)
            echo[delay:] = audio_data[:-delay] * decay
            
            filter_length = 1024
            step_size = 0.1
            w = np.zeros(filter_length)
            chunk_size = 1024
            cancelled_audio = np.zeros_like(audio_data)
            
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i:i + chunk_size]
                echo_chunk = echo[i:i + chunk_size]
                
                if len(chunk) < chunk_size:
                    break
                    
                x = np.concatenate([np.zeros(filter_length - 1), chunk])
                for n in range(len(chunk)):
                    x_n = x[n:n + filter_length]
                    d = echo_chunk[n]
                    y = np.dot(w, x_n)
                    e = d - y
                    w = w + step_size * e * x_n
                    cancelled_audio[i + n] = audio_data[i + n] - y
                    
            logger.info(f"Echo cancellation completed in {time.time() - start_time:.2f} seconds")
            return cancelled_audio
            
        except Exception as e:
            logger.error(f"Error in echo cancellation: {str(e)}")
            raise AudioEnhancementError(f"Failed to cancel echo: {str(e)}")

    @with_timeout(60)
    def classify_background_noise(self, audio_data, sample_rate):
        """Classify background noise with improved accuracy."""
        try:
            start_time = time.time()
            mfccs = librosa.feature.mfcc(y=audio_data, sr=sample_rate, n_mfcc=13)
            spectral_centroids = librosa.feature.spectral_centroid(y=audio_data, sr=sample_rate)
            spectral_rolloff = librosa.feature.spectral_rolloff(y=audio_data, sr=sample_rate)
            
            mean_mfcc = np.mean(mfccs)
            mean_centroid = np.mean(spectral_centroids)
            mean_rolloff = np.mean(spectral_rolloff)
            
            if mean_centroid < 1000 and mean_rolloff < 2000:
                noise_type = "ambient"
            elif mean_centroid > 3000 and mean_rolloff > 5000:
                noise_type = "mechanical"
            elif 1000 <= mean_centroid <= 3000:
                noise_type = "speech_babble"
            else:
                noise_type = "unknown"
                
            logger.info(f"Noise classification ({noise_type}) completed in {time.time() - start_time:.2f} seconds")
            return noise_type
            
        except Exception as e:
            logger.error(f"Error in noise classification: {str(e)}")
            raise AudioEnhancementError(f"Failed to classify background noise: {str(e)}")
        
    @with_timeout(120)
    def enhance_audio(self, audio_data, sample_rate):
        """Apply audio enhancement with improved error handling."""
        try:
            start_time = time.time()
            
            # Apply pre-emphasis filter
            pre_emphasis = 0.97
            emphasized_audio = np.append(
                audio_data[0],
                audio_data[1:] - pre_emphasis * audio_data[:-1]
            )
            
            # Apply adaptive noise reduction
            cleaned_audio = self.adaptive_noise_reduction(emphasized_audio, sample_rate)
            
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
            
            logger.info(f"Audio enhancement completed in {time.time() - start_time:.2f} seconds")
            return filtered_audio
            
        except Exception as e:
            logger.error(f"Error enhancing audio: {str(e)}")
            raise AudioEnhancementError(f"Failed to enhance audio: {str(e)}")
        
    def save_enhanced_audio(self, audio_data, sample_rate, output_path):
        """Save enhanced audio with error handling."""
        try:
            start_time = time.time()
            sf.write(output_path, audio_data, sample_rate)
            logger.info(f"Enhanced audio saved to {output_path} in {time.time() - start_time:.2f} seconds")
        except Exception as e:
            logger.error(f"Error saving enhanced audio: {str(e)}")
            raise AudioEnhancementError(f"Failed to save enhanced audio: {str(e)}")
