import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time notifications.
    
    Connect using:
    ws://example.com/ws/notifications/?token=your-jwt-token
    OR
    Use an Authorization header with "Bearer your-jwt-token"
    """
    async def connect(self):
        # Reject connection if the user is anonymous
        if self.scope["user"].is_anonymous:
            logger.info("Anonymous user attempted to connect to WebSocket. Connection rejected.")
            await self.close()
            return

        # Assign group name based on the user's ID
        self.group_name = f"user_{self.scope['user'].id}"
        logger.info(f"User {self.scope['user'].id} connected to WebSocket.")

        # Add the user to the group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # Remove the user from the group only if group_name is set
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(f"User {self.scope['user'].id} disconnected from WebSocket.")

    async def send_notification(self, event):
        # Send notification to the WebSocket
        logger.info(f"Sending notification to WebSocket: {event['message']}")
        await self.send(text_data=json.dumps(event["message"]))
