import asyncio
import argparse
import os
import sys
import logging
import threading
import uvicorn
from config import Config
from ble_manager import BLEHandler
from data_parser import ParsedData
from web_server import app, DataBroadcaster, broadcaster
from tray_app import TrayApp

# Глобальные объекты
broadcast_manager = DataBroadcaster()
import web_server
web_server.broadcaster = broadcast_manager

ble_handler = None
web_server_task = None
tray_app = None

async def on_measurement_received(parsed: ParsedData):
    broadcast_manager.update(parsed)
    if tray_app:
        tray_app.set_connected(True)

async def on_ble_disconnect():
    broadcast_manager.set_disconnected()
    if tray_app:
        tray_app.set_connected(False)

async def run_ble_connection(config: Config):
    global ble_handler
    if not config.device_address:
        logger.warning("Адрес устройства не указан, BLE не запущен") if logger else None
        if tray_app:
            tray_app.set_connected(False)
        return

    json_dir = os.path.dirname(os.path.abspath(__file__))
    ble_handler = BLEHandler(
        on_data=on_measurement_received,
        on_disconnect=on_ble_disconnect,
        json_dir=json_dir,
        auto_reconnect=True
    )

    try:
        await ble_handler.connect(config.device_address)
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Ошибка BLE: {e}", exc_info=True) if logger else None
    finally:
        if ble_handler:
            await ble_handler.stop()
            ble_handler = None
        broadcast_manager.set_disconnected()
        if tray_app:
            tray_app.set_connected(False)

async def run_web_server(port: int):
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_config=None,
        log_level="info"
    )
    server = uvicorn.Server(config)
    try:
        logger.info(f"Запуск веб-сервера на порту {port}") if logger else None
        await server.serve()
    except asyncio.CancelledError:
        logger.info("Веб-сервер остановлен (CancelledError)") if logger else None
    except Exception as e:
        logger.error(f"Критическая ошибка веб-сервера: {e}", exc_info=True) if logger else None

async def main_async(config: Config):
    global web_server_task
    logger.info("Запуск main_async") if logger else None
    web_server_task = asyncio.create_task(run_web_server(config.web_port))

    ble_task = asyncio.create_task(run_ble_connection(config))

    try:
        await asyncio.wait([web_server_task, ble_task], return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        pass
    finally:
        for task in [web_server_task, ble_task]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    logger.info("main_async завершён") if logger else None

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--config", type=str, default="config.json")
    parser.add_argument("--port", type=int)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--tray", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--debug", action="store_true", help="Включить подробное логирование в файл")
    return parser.parse_args()

async def scan_devices():
    ble = BLEHandler()
    devices = await ble.scan()
    for d in devices:
        print(f"{d['name']:30} {d['address']}")

async def test_connection(config: Config):
    if not config.device_address:
        print("Ошибка: нет адреса устройства.")
        return
    json_dir = os.path.dirname(os.path.abspath(__file__))
    ble = BLEHandler(on_data=on_measurement_received, json_dir=json_dir)
    try:
        await ble.connect(config.device_address)
        print("Сбор данных... Ctrl+C для выхода.")
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await ble.stop()

async def interactive_setup(config: Config):
    ble = BLEHandler()
    if config.device_address:
        print(f"Текущее устройство: {config.device_name} ({config.device_address})")
        ans = input("Сканировать заново? [y/N]: ").strip().lower()
        if ans != 'y':
            return

    devices = await ble.scan()
    if not devices:
        print("Устройства не найдены.")
        return

    print("\nДоступные устройства:")
    for idx, dev in enumerate(devices):
        print(f"{idx:3}: {dev['name']:30} [{dev['address']}]")

    while True:
        try:
            choice = input("Введите номер устройства (или 'q' для выхода): ").strip()
            if choice.lower() == 'q':
                sys.exit(0)
            idx = int(choice)
            if 0 <= idx < len(devices):
                selected = devices[idx]
                break
            else:
                print("Некорректный номер.")
        except ValueError:
            print("Введите число.")

    config.set_device(selected["address"], selected["name"])
    print(f"Выбрано: {selected['name']} ({selected['address']})")

def main():
    global tray_app, logger
    args = parse_args()
    config_path = args.config if not os.path.isabs(args.config) else args.config
    config = Config(config_path)

    # Настройка логгера
    if args.debug:
        # Подробное логирование в файл
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            handlers=[logging.FileHandler("multimeter_ble.log", encoding='utf-8')]
        )
        logger = logging.getLogger("Main")
        logger.debug("Режим отладки включен")
    else:
        # Полностью отключаем логирование (только критические ошибки)
        logging.basicConfig(level=logging.CRITICAL, handlers=[logging.NullHandler()])
        logger = None  # все вызовы logger будут проверены, если logger is None

    if args.port:
        config.web_port = args.port
        config.save()

    if args.scan:
        asyncio.run(scan_devices())
        return

    if args.test:
        asyncio.run(test_connection(config))
        return

    if args.tray:
        if logger:
            logger.info("Запуск в режиме трея")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        def start_asyncio():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main_async(config))

        thread = threading.Thread(target=start_asyncio, daemon=False)
        thread.start()

        def on_exit():
            if logger:
                logger.info("Запрошен выход из трея")
            loop.call_soon_threadsafe(loop.stop)

        tray_app = TrayApp(None, None, on_exit)
        tray_app.run()
        thread.join(timeout=3)
        if logger:
            logger.info("Программа завершена")
        return

    if args.serve:
        asyncio.run(main_async(config))
        return

    # Интерактивная настройка
    asyncio.run(interactive_setup(config))
    print("\nНастройка завершена.")
    print("Для запуска веб-сервера: python multimeter_ble.py --serve")
    print("Для запуска в трее: python multimeter_ble.py --tray")

if __name__ == "__main__":
    main()