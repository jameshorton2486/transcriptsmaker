import os
import logging
import asyncio
import json
from typing import Optional, Dict, Any
from datetime import datetime
from deepgram import (
    DeepgramClient,
    LiveOptions,
    LiveTranscriptionEvents
)

logger = logging.getLogger(__name__)

class DeepgramStreamingClient:
    """Enhanced client for handling real-time streaming transcription with Deepgram"""
    
    def __init__(self):
        self.api_key = os.environ.get('DEEPGRAM_API_KEY')
        if not self.api_key:
            raise ValueError("Deepgram API key not found in environment variables")
            
        self.client = DeepgramClient(api_key=self.api_key)
        self.active_connections = {}  # Store connection info with metrics
        self.reconnect_attempts = {}  # Track reconnection attempts per connection
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 1.0  # Base delay in seconds
        logger.info("Deepgram streaming client initialized")

    async def handle_websocket(self, websocket) -> None:
        """Enhanced WebSocket connection handler with improved error recovery"""
        connection_id = id(websocket)
        start_time = datetime.utcnow()
        metrics = {
            'connection_id': connection_id,
            'start_time': start_time.isoformat(),
            'chunks_processed': 0,
            'errors': 0,
            'reconnect_attempts': 0,
            'bytes_processed': 0,
            'status': 'initializing'
        }
        
        try:
            self.active_connections[connection_id] = metrics
            logger.info(f"New WebSocket connection established: {connection_id}")

            # Configure optimized live transcription options
            options = LiveOptions(
                model="nova-2",
                language="en-US",
                smart_format=True,
                punctuate=True,
                diarize=True,
                encoding="linear16",
                channels=1,
                sample_rate=16000,
                interim_results=True,
                utterance_end_ms=1000,
                vad_events=True
            )

            # Initialize live transcription with retry logic
            live_transcription = await self._initialize_live_transcription(options)
            if not live_transcription:
                raise Exception("Failed to initialize live transcription")

            metrics['status'] = 'connected'
            await self._send_connection_status(websocket, 'connected')

            # Set up event handlers
            @live_transcription.on(LiveTranscriptionEvents.Transcript)
            async def handle_transcript(transcript):
                try:
                    if transcript and isinstance(transcript, dict):
                        await self._process_transcript(websocket, transcript, metrics)
                except Exception as e:
                    logger.error(f"Error processing transcript: {str(e)}")
                    metrics['errors'] += 1

            @live_transcription.on(LiveTranscriptionEvents.Error)
            async def handle_error(error):
                logger.error(f"Deepgram error: {str(error)}")
                metrics['errors'] += 1
                await self._handle_connection_error(websocket, error, metrics)

            @live_transcription.on(LiveTranscriptionEvents.Close)
            async def handle_close():
                logger.info(f"Deepgram connection closed for {connection_id}")
                metrics['status'] = 'closed'
                await self._send_connection_status(websocket, 'closed')

            # Process audio stream with enhanced error handling
            while True:
                try:
                    data = await websocket.receive_bytes()
                    if not data:
                        break
                    
                    metrics['bytes_processed'] += len(data)
                    await live_transcription.send(data)
                    
                    # Update processing metrics
                    metrics['chunks_processed'] += 1
                    if metrics['chunks_processed'] % 100 == 0:
                        logger.info(f"Processing metrics for {connection_id}: {metrics}")
                        
                except Exception as e:
                    logger.error(f"Error processing audio data: {str(e)}")
                    if not await self._handle_connection_error(websocket, e, metrics):
                        break

            await live_transcription.finish()

        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            await self._handle_connection_error(websocket, e, metrics)
        finally:
            await self._cleanup_connection(websocket, connection_id, metrics)

    async def _initialize_live_transcription(self, options):
        """Initialize live transcription with retry logic"""
        attempts = 0
        while attempts < self.max_reconnect_attempts:
            try:
                live = self.client.listen.live.v("1")
                connection = await live.start(options)
                return connection
            except Exception as e:
                attempts += 1
                if attempts >= self.max_reconnect_attempts:
                    logger.error(f"Failed to initialize live transcription after {attempts} attempts")
                    return None
                wait_time = self.reconnect_delay * (2 ** attempts)
                logger.warning(f"Retrying live transcription initialization in {wait_time}s")
                await asyncio.sleep(wait_time)

    async def _process_transcript(self, websocket, transcript, metrics):
        """Process and send transcript data to client"""
        try:
            if 'channel' in transcript and 'alternatives' in transcript['channel']:
                alternative = transcript['channel']['alternatives'][0]
                response = {
                    'type': 'transcript',
                    'is_final': transcript.get('is_final', True),
                    'transcript': alternative.get('transcript', ''),
                    'confidence': alternative.get('confidence', 0),
                    'words': [
                        {
                            'word': word.get('word', ''),
                            'start': word.get('start', 0),
                            'end': word.get('end', 0),
                            'confidence': word.get('confidence', 0),
                            'speaker': word.get('speaker', None)
                        }
                        for word in alternative.get('words', [])
                    ]
                }
                await websocket.send(json.dumps(response))
                metrics['chunks_processed'] += 1
        except Exception as e:
            logger.error(f"Error processing transcript data: {str(e)}")
            metrics['errors'] += 1
            await self._send_error(websocket, "Error processing transcript")

    async def _handle_connection_error(self, websocket, error, metrics):
        """Enhanced error handling with reconnection logic"""
        metrics['errors'] += 1
        metrics['status'] = 'error'
        
        error_message = str(error)
        logger.error(f"Connection error: {error_message}")
        
        try:
            await self._send_error(websocket, error_message)
            
            if metrics['reconnect_attempts'] < self.max_reconnect_attempts:
                metrics['reconnect_attempts'] += 1
                wait_time = self.reconnect_delay * (2 ** metrics['reconnect_attempts'])
                
                await self._send_connection_status(websocket, 'reconnecting')
                await asyncio.sleep(wait_time)
                
                return True  # Continue processing
            else:
                logger.error(f"Max reconnection attempts reached for connection")
                await self._send_connection_status(websocket, 'failed')
                return False  # Stop processing
                
        except Exception as e:
            logger.error(f"Error handling connection error: {str(e)}")
            return False

    async def _send_error(self, websocket, error_message):
        """Send error message to client"""
        try:
            await websocket.send(json.dumps({
                'type': 'error',
                'error': error_message,
                'timestamp': datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")

    async def _send_connection_status(self, websocket, status):
        """Send connection status update to client"""
        try:
            await websocket.send(json.dumps({
                'type': 'status',
                'status': status,
                'timestamp': datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.error(f"Error sending status update: {str(e)}")

    async def _cleanup_connection(self, websocket, connection_id, metrics):
        """Enhanced cleanup with detailed logging"""
        try:
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            
            end_time = datetime.utcnow()
            metrics.update({
                'end_time': end_time.isoformat(),
                'duration': (end_time - datetime.fromisoformat(metrics['start_time'])).total_seconds(),
                'final_status': metrics['status']
            })
            
            logger.info(f"Connection cleanup completed. Final metrics: {metrics}")
            
            try:
                await websocket.close()
            except Exception as e:
                logger.error(f"Error closing websocket: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error during connection cleanup: {str(e)}")

    def get_active_connections(self) -> Dict[int, Dict[str, Any]]:
        """Get detailed information about active connections"""
        return self.active_connections
