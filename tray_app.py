import asyncio
import threading
import logging
from typing import Optional
import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger("TrayApp")

class TrayApp:
    def __init__(self, ble_handler, web_server_task, on_exit=None):
        self.ble_handler = ble_handler
        self.web_server_task = web_server_task
        self.on_exit = on_exit
        self.icon: Optional[pystray.Icon] = None
        self._loop = asyncio.get_event_loop()

    def create_icon(self):
        def draw_image(connected):
            img = Image.new('RGB', (64, 64), 'black')
            d = ImageDraw.Draw(img)
            color = 'green' if connected else 'red'
            d.ellipse([16, 16, 48, 48], fill=color)
            return img

        self._icon_image = draw_image(False)

        menu = pystray.Menu(
            pystray.MenuItem("Выход", self.on_exit_clicked),
        )

        self.icon = pystray.Icon(
            "multimeter_ble",
            self._icon_image,
            "Multimeter BLE Server",
            menu
        )

    def set_connected(self, connected: bool):
        if not self.icon:
            return
        def draw_image(conn):
            img = Image.new('RGB', (64, 64), 'black')
            d = ImageDraw.Draw(img)
            color = 'green' if conn else 'red'
            d.ellipse([16, 16, 48, 48], fill=color)
            return img

        self._icon_image = draw_image(connected)
        self.icon.icon = self._icon_image

    def on_exit_clicked(self, icon, item):
        logger.info("Выход из трея")
        if self.on_exit:
            self.on_exit()
        if self.icon:
            self.icon.stop()

    def run(self):
        self.create_icon()
        self.icon.run()