"""
Consumer de WebSocket para el KDS de cocina.
El frontend (kitchenService.subscribe) se conecta a ws/kitchen/<tenant>/ y
recibe en vivo los tickets nuevos y los cambios de estado.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer


class KitchenConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.tenant = self.scope["url_route"]["kwargs"]["tenant"]
        self.group = f"kitchen_{self.tenant}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Avance de estado emitido por una tablet de cocina
        data = json.loads(text_data or "{}")
        await self.channel_layer.group_send(
            self.group, {"type": "ticket.update", "payload": data}
        )

    async def ticket_new(self, event):
        await self.send(text_data=json.dumps({"event": "ticket.new", "ticket": event["ticket"]}))

    async def ticket_update(self, event):
        await self.send(text_data=json.dumps({"event": "ticket.update", "payload": event["payload"]}))

    async def product_availability(self, event):
        # Cambios de disponibilidad ("Agotado") en vivo para menú/pedidos.
        await self.send(text_data=json.dumps({"event": "product.availability", "products": event["products"]}))
