import json
import os

class Config:
    DEFAULT_PORT = 8080
    DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.device_address: str = ""
        self.device_name: str = ""
        self.web_port: int = self.DEFAULT_PORT
        self.load()

    def load(self):
        """Загружает конфиг из файла. Если файла нет, использует значения по умолчанию."""
        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
                self.device_address = data.get("device_address", "")
                self.device_name = data.get("device_name", "")
                self.web_port = data.get("web_port", self.DEFAULT_PORT)
        except (FileNotFoundError, json.JSONDecodeError):
            # Файл не найден или повреждён - используем дефолтные значения
            pass

    def save(self):
        """Сохраняет текущие настройки в JSON-файл."""
        data = {
            "device_address": self.device_address,
            "device_name": self.device_name,
            "web_port": self.web_port,
        }
        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def set_device(self, address: str, name: str = ""):
        """Обновляет информацию о выбранном устройстве и сохраняет."""
        self.device_address = address
        self.device_name = name
        self.save()

    def __repr__(self):
        return (f"Config(device_address={self.device_address!r}, "
                f"device_name={self.device_name!r}, web_port={self.web_port})")