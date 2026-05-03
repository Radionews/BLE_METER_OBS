import asyncio
import logging
from typing import Optional, List, Dict, Callable, Awaitable
from bleak import BleakScanner, BleakClient
from data_parser import DataParser, ParsedData

logger = logging.getLogger("BLEManager")

SERVICE_UUID = "49535343-fe7d-4ae5-8fa9-9fafd205e455"
NOTIFY_UUID  = "49535343-1e4d-4bd9-ba61-23c647249616"
WRITE_UUID   = "49535343-6daa-4d02-abf6-19569aca69fe"
WRITE_UUID2  = "49535343-8841-43f4-a8d4-ecbe34729bb3"

HEADER = bytes([0xAB, 0xCD, 0x03])

DataCallback = Callable[[ParsedData], Awaitable[None]]
DisconnectCallback = Callable[[], Awaitable[None]]

class BLEHandler:
    def __init__(self,
                 on_data: Optional[DataCallback] = None,
                 on_disconnect: Optional[DisconnectCallback] = None,
                 sampling_interval_ms: int = 1000,
                 auto_reconnect: bool = True,
                 json_dir: str = "."):
        self.on_data = on_data
        self.on_disconnect = on_disconnect
        self.client: Optional[BleakClient] = None
        self.write_char_uuid = None
        self._sampling_interval = sampling_interval_ms / 1000.0
        self._is_sampling = False
        self._model = "Unknown"
        self._json_dir = json_dir
        self._auto_reconnect = auto_reconnect
        self._reconnect_task: Optional[asyncio.Task] = None
        self._address: Optional[str] = None

    async def scan(self, timeout: float = 5.0) -> List[Dict[str, str]]:
        logger.info(f"Сканирование в течение {timeout} сек...")
        devices = await BleakScanner.discover(timeout=timeout)
        result = []
        for d in devices:
            name = d.name or "Unknown"
            result.append({"address": d.address, "name": name})
        result.sort(key=lambda x: x["name"].lower())
        return result

    async def connect(self, address: str):
        self._address = address
        await self._cleanup_client()
        self.client = BleakClient(address, disconnected_callback=self._on_disconnected)
        await self.client.connect()
        logger.info("BLE client подключен")

        self.write_char_uuid = await self._select_write_characteristic()
        if not self.write_char_uuid:
            raise RuntimeError("Не найдена характеристика для записи")

        await self.client.start_notify(NOTIFY_UUID, self._notification_handler)
        logger.info("Подписка на уведомления активирована")

        await asyncio.sleep(0.3)
        await self._request_device_type()

    async def _cleanup_client(self):
        await self.stop_sampling()
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None

    async def stop(self):
        self._auto_reconnect = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        await self._cleanup_client()
        logger.info("BLEHandler остановлен")

    async def _select_write_characteristic(self):
        for service in self.client.services:
            for char in service.characteristics:
                if char.uuid == WRITE_UUID2:
                    logger.info("Используется новый Write UUID2")
                    return WRITE_UUID2
                elif char.uuid == WRITE_UUID:
                    logger.info("Используется старый Write UUID")
        return WRITE_UUID

    def _make_cmd(self, code: int) -> bytes:
        s = code + 379
        return HEADER + bytes([code, (s >> 8) & 0xFF, s & 0xFF])

    async def _request_device_type(self):
        cmd = self._make_cmd(0x5F)
        logger.info(f"Запрос типа устройства: {cmd.hex()}")
        try:
            await self.client.write_gatt_char(self.write_char_uuid, cmd, response=False)
        except Exception as e:
            logger.error(f"Ошибка отправки запроса типа: {e}")

    async def start_sampling(self):
        if self._is_sampling:
            return
        self._is_sampling = True
        logger.info("Запуск цикла сбора данных")
        while self._is_sampling and self.client and self.client.is_connected:
            try:
                cmd = self._make_cmd(0x5D)
                await self.client.write_gatt_char(self.write_char_uuid, cmd, response=False)
                await asyncio.sleep(self._sampling_interval)
            except Exception as e:
                logger.error(f"Ошибка при опросе: {e}")
                break
        self._is_sampling = False
        logger.warning("Цикл опроса остановлен")

    async def stop_sampling(self):
        self._is_sampling = False

    def _notification_handler(self, sender, data: bytearray):
        raw = bytes(data)
        logger.debug(f"Notification raw ({len(raw)}): {raw.hex()}")

        if len(raw) == 7 and raw[0] == 0xAB and raw[1] == 0xCD \
                and raw[3] == 0xFF and raw[4] == 0x00:
            logger.info("Подтверждение команды")
            return
        if len(raw) == 9 and raw[0] == 0xAB and raw[1] == 0xCD \
                and raw[3] == 0xAA and raw[4] == 0xAA:
            logger.warning("Ошибка, повторный запрос типа устройства")
            asyncio.ensure_future(self._request_device_type())
            return

        if len(raw) == 19:
            parsed = DataParser.parse(raw)
            if parsed is None:
                logger.warning("Не удалось разобрать 19-байтный пакет")
                return
            if self.on_data:
                asyncio.ensure_future(self.on_data(parsed))
            return

        # Имя модели (уведомление с текстовой строкой)
        if len(raw) >= 7:
            text_part = raw[3:len(raw)-5]
            if all(32 <= b <= 126 for b in text_part):
                model = text_part.decode('ascii').strip()
                # Логируем полное имя для диагностики
                logger.info(f"Получено имя модели: '{model}' (длина: {len(model)})")
                self._model = model
                # Загружаем JSON, передавая точное имя
                DataParser.load_model_json(model, self._json_dir)
                if not self._is_sampling:
                    asyncio.ensure_future(self.start_sampling())
                return

        logger.warning(f"Неизвестный формат уведомления: {raw.hex()}")

    def _on_disconnected(self, client):
        logger.warning("BLE соединение разорвано")
        self._is_sampling = False
        if self.on_disconnect:
            asyncio.ensure_future(self.on_disconnect())
        if self._auto_reconnect and self._address:
            self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self):
        logger.info("Запуск цикла переподключения")
        while self._auto_reconnect and self._address:
            try:
                await self.connect(self._address)
                logger.info("Переподключение успешно")
                return
            except Exception as e:
                logger.warning(f"Переподключение не удалось: {e}. Повтор через 5 сек.")
                await asyncio.sleep(5)