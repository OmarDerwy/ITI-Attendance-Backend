import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Log the headers sent with the WebSocket connection
        headers = dict(self.scope.get("headers", []))
        auth_header = headers.get(b"authorization", b"").decode("utf-8")
        logger.info(f"WebSocket connection headers: {headers}")
        logger.info(f"Authorization header: {auth_header}")

        if self.scope["user"].is_anonymous:
            self.group_name = "anonymous"
            logger.info("Anonymous user connected to WebSocket.")
        else:
            self.group_name = f"user_{self.scope['user'].id}"
            logger.info(f"User {self.scope['user'].id} connected to WebSocket.")

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info(f"Disconnected from WebSocket: {self.group_name}")

    async def send_notification(self, event):
        logger.info(f"Sending notification to WebSocket: {event['message']}")
        await self.send(text_data=json.dumps(event["message"]))
