import numpy as np
from pydub import AudioSegment
from scipy import signal
import soundfile as sf
import io
import os
import librosa
import noisereduce as nr
from scipy.fftpack import fft, ifft

class AudioProcessor:
    SUPPORTED_FORMATS = {'wav', 'mp3', 'flac', 'mp4'}
    TARGET_SAMPLE_RATE = 16000
    TARGET_DB = -20
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.format = file_path.split('.')[-1].lower()
        if self.format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {self.format}")
            
    def process_audio(self):
        """Main processing pipeline for audio enhancement"""
        # Load and normalize audio
        audio = self.normalize_audio()
        
        # Convert to numpy array for advanced processing
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        samples = samples / (1 << (8 * audio.sample_width - 1))  # Normalize to [-1, 1]
        sample_rate = audio.frame_rate
        
        # Apply channel separation if stereo
        channels = self.split_channels(samples)
        
        # Apply audio enhancement
        enhanced_channels = [self.enhance_audio(channel, sample_rate) for channel in channels]
        
        # Combine channels if necessary
        if len(enhanced_channels) > 1:
            enhanced_audio = np.stack(enhanced_channels, axis=1)
        else:
            enhanced_audio = enhanced_channels[0]
            
        # Classify background noise
        noise_type = self.classify_background_noise(enhanced_audio, sample_rate)
            
        return enhanced_audio, sample_rate, noise_type
            
    def normalize_audio(self):
        """Normalize audio to target sample rate and apply volume normalization"""
        audio = AudioSegment.from_file(self.file_path)
        
        # Convert to mono if needed
        if audio.channels > 2:
            audio = audio.set_channels(2)
            
        # Normalize sample rate
        if audio.frame_rate != self.TARGET_SAMPLE_RATE:
            audio = audio.set_frame_rate(self.TARGET_SAMPLE_RATE)
        
        # Normalize volume
        change_in_dbfs = self.TARGET_DB - audio.dBFS
        normalized_audio = audio.apply_gain(change_in_dbfs)
        
        return normalized_audio
        
    def split_channels(self, samples):
        """Split stereo audio into separate channels"""
        if len(samples.shape) > 1:
            return [samples[:, i] for i in range(samples.shape[1])]
        return [samples]

    def adaptive_noise_reduction(self, audio_data, sample_rate):
        """Apply adaptive noise reduction using noise reduce library"""
        # Get noise profile from first 1000ms
        noise_clip = audio_data[:int(sample_rate)]
        reduced_noise = nr.reduce_noise(
            y=audio_data,
            y_noise=noise_clip,
            sr=sample_rate,
            stationary=False,
            prop_decrease=0.75
        )
        return reduced_noise

    def echo_cancellation(self, audio_data, sample_rate):
        """Apply echo cancellation using adaptive filtering"""
        # Parameters for echo cancellation
        delay = int(0.05 * sample_rate)  # 50ms delay
        decay = 0.3
        
        # Create simulated echo
        echo = np.zeros_like(audio_data)
        echo[delay:] = audio_data[:-delay] * decay
        
        # Apply adaptive filter
        filter_length = 1024
        step_size = 0.1
        
        # Initialize filter coefficients
        w = np.zeros(filter_length)
        
        # Process in chunks
        chunk_size = 1024
        cancelled_audio = np.zeros_like(audio_data)
        
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i + chunk_size]
            echo_chunk = echo[i:i + chunk_size]
            
            if len(chunk) < chunk_size:
                break
                
            # Update filter coefficients
            x = np.concatenate([np.zeros(filter_length - 1), chunk])
            for n in range(len(chunk)):
                x_n = x[n:n + filter_length]
                d = echo_chunk[n]
                y = np.dot(w, x_n)
                e = d - y
                w = w + step_size * e * x_n
                cancelled_audio[i + n] = audio_data[i + n] - y
                
        return cancelled_audio

    def classify_background_noise(self, audio_data, sample_rate):
        """Classify background noise type using spectral features"""
        # Extract audio features
        mfccs = librosa.feature.mfcc(y=audio_data, sr=sample_rate, n_mfcc=13)
        spectral_centroids = librosa.feature.spectral_centroid(y=audio_data, sr=sample_rate)
        spectral_rolloff = librosa.feature.spectral_rolloff(y=audio_data, sr=sample_rate)
        
        # Simple rule-based classification
        mean_mfcc = np.mean(mfccs)
        mean_centroid = np.mean(spectral_centroids)
        mean_rolloff = np.mean(spectral_rolloff)
        
        # Classify based on spectral characteristics
        if mean_centroid < 1000 and mean_rolloff < 2000:
            return "ambient"
        elif mean_centroid > 3000 and mean_rolloff > 5000:
            return "mechanical"
        elif 1000 <= mean_centroid <= 3000:
            return "speech_babble"
        else:
            return "unknown"
        
    def enhance_audio(self, audio_data, sample_rate):
        """Apply audio enhancement techniques"""
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
        
        # Apply band-pass filter to focus on speech frequencies
        nyquist = sample_rate // 2
        low_cutoff = 80  # Hz
        high_cutoff = 8000  # Hz
        b, a = signal.butter(
            N=4,
            Wn=[low_cutoff/nyquist, high_cutoff/nyquist],
            btype='band'
        )
        filtered_audio = signal.filtfilt(b, a, echo_cancelled)
        
        return filtered_audio
        
    def save_enhanced_audio(self, audio_data, sample_rate, output_path):
        """Save the enhanced audio to a file"""
        sf.write(output_path, audio_data, sample_rate)
