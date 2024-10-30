import os
import logging
import asyncio
import json
from typing import Optional, Dict, Any, Callable
from datetime import datetime
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions
)

logger = logging.getLogger(__name__)

class DeepgramStreamingClient:
    """Client for handling real-time streaming transcription with Deepgram"""
    
    def __init__(self):
        self.api_key = os.environ.get('DEEPGRAM_API_KEY')
        if not self.api_key:
            raise ValueError("Deepgram API key not found in environment variables")
            
        # Initialize Deepgram client without verbose logging option
        self.client = DeepgramClient(api_key=self.api_key)
        self.active_connections = set()
        logger.info("Deepgram streaming client initialized")

    async def handle_websocket(self, websocket) -> None:
        """Handle WebSocket connection for real-time transcription"""
        connection_id = id(websocket)
        start_time = datetime.utcnow()
        metrics = {
            'connection_id': connection_id,
            'start_time': start_time.isoformat(),
            'chunks_processed': 0,
            'errors': 0
        }
        
        try:
            self.active_connections.add(connection_id)
            logger.info(f"New WebSocket connection established: {connection_id}")

            # Configure live transcription options
            options = LiveOptions(
                model="nova-2",
                language="en-US",
                smart_format=True,
                punctuate=True,
                diarize=True,
                encoding="linear16",
                channels=1,
                sample_rate=16000,
                interim_results=True
            )

            # Create live transcription
            live = self.client.listen.live.v("1")
            connection = await live.start(options)
            logger.info("Live transcription connection established")

            # Handle transcription events
            @connection.on('transcript')
            async def handle_transcript(transcript):
                try:
                    if transcript and isinstance(transcript, dict):
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
                        elif 'error' in transcript:
                            logger.error(f"Deepgram error: {transcript['error']}")
                            metrics['errors'] += 1
                            await websocket.send(json.dumps({
                                'type': 'error',
                                'error': transcript['error']
                            }))
                except Exception as e:
                    logger.error(f"Error processing transcript: {str(e)}")
                    metrics['errors'] += 1

            @connection.on('error')
            async def handle_error(error):
                logger.error(f"Deepgram error: {str(error)}")
                metrics['errors'] += 1
                try:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'error': str(error)
                    }))
                except Exception as e:
                    logger.error(f"Error sending error message: {str(e)}")

            @connection.on('close')
            async def handle_close():
                logger.info("Deepgram connection closed")

            # Handle incoming audio data
            while True:
                try:
                    data = await websocket.receive_bytes()
                    if not data:  # Empty data means connection closed
                        break
                    await connection.send(data)
                except Exception as e:
                    logger.error(f"Error receiving/sending data: {str(e)}")
                    break

            await connection.finish()

        except Exception as e:
            logger.error(f"WebSocket error: {str(e)}")
            try:
                await websocket.send(json.dumps({
                    'type': 'error',
                    'error': 'Connection error occurred'
                }))
            except:
                pass
        finally:
            # Cleanup and log metrics
            if connection_id in self.active_connections:
                self.active_connections.remove(connection_id)
            end_time = datetime.utcnow()
            metrics.update({
                'end_time': end_time.isoformat(),
                'duration': (end_time - start_time).total_seconds()
            })
            logger.info(f"WebSocket connection closed. Metrics: {metrics}")
            await self.cleanup_connection(websocket)

    async def cleanup_connection(self, websocket) -> None:
        """Clean up resources when a WebSocket connection is terminated"""
        try:
            await websocket.close()
        except Exception as e:
            logger.error(f"Error during WebSocket cleanup: {str(e)}")

    def get_active_connections(self) -> int:
        """Get the number of active WebSocket connections"""
        return len(self.active_connections)
