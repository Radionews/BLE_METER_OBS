import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("DataParser")

FUNCTION_STRINGS = [
    "AC V", "AC mV", "DC V", "DC mV", "Hz", "%", "RES", "CONT", "Diode", "CAP",
    "°C", "°F", "DC μA", "AC μA", "DC mA", "AC mA", "DC A", "AC A", "NCV"
]

DEFAULT_UNITS = {
    "AC V": "V", "AC mV": "mV", "DC V": "V", "DC mV": "mV",
    "Hz": "Hz", "%": "%", "RES": "Ω", "CONT": "Ω", "Diode": "V",
    "CAP": "F", "°C": "°C", "°F": "°F",
    "DC μA": "μA", "AC μA": "μA", "DC mA": "mA", "AC mA": "mA",
    "DC A": "A", "AC A": "A", "NCV": ""
}

class ParsedData:
    def __init__(self):
        self.value: Optional[float] = None
        self.unit: str = "?"
        self.function: str = "?"
        self.range_str: str = ""
        self.is_ol: bool = False
        self.max_value: float = 0.0
        self.min_value: float = 0.0
        self.value2: Optional[float] = None
        self.function2: str = ""
        self.range2_str: str = ""
        self.unit2: str = ""
        self.is_dc: bool = False
        self.is_auto: bool = False
        self.is_hold: bool = False
        self.is_rel: bool = False
        self.is_max: bool = False
        self.is_min: bool = False
        self.is_peak_max: bool = False
        self.is_peak_min: bool = False
        self.is_bar_pol: bool = False
        self.is_battery_low: bool = False
        self.is_hv_warning: bool = False
        self.load_progress: int = 0

    def __repr__(self):
        val = f"{self.value} {self.unit}" if not self.is_ol else "OL"
        return f"<ParsedData {val} ({self.function}) DC={self.is_dc} Auto={self.is_auto} Hold={self.is_hold}>"


class DataParser:
    _range_map: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def load_model_json(cls, model_name: str, json_dir: str = "."):
        filename = f"funOl_{model_name}.json"
        path = os.path.join(json_dir, filename)
        logger.info(f"Поиск JSON диапазонов: {path}")
        if not os.path.exists(path):
            logger.warning(f"JSON-файл не найден: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ol_data = data.get("OL", {})
            cls._range_map.clear()
            for func, ranges in ol_data.items():
                func_map = {}
                for ridx, arr in ranges.items():
                    if len(arr) >= 4:
                        # Очищаем единицы от возможных некорректных символов
                        unit = arr[1]
                        unit = unit.replace("©", "Ω").replace("&#169;", "Ω")
                        # Замена u на μ 
                        unit = unit.replace("u", "μ")  # если хотите отображать "μ"
                        func_map[ridx] = {
                            "range_str": arr[0],
                            "unit": unit,
                            "max": float(arr[2]),
                            "min": float(arr[3])
                        }
                cls._range_map[func] = func_map
            logger.info(f"Загружены диапазоны для модели {model_name} ({len(cls._range_map)} функций)")
        except Exception as e:
            logger.error(f"Ошибка загрузки JSON-диапазонов: {e}")

    @classmethod
    def _get_range_info(cls, function: str, range_index: str):
        if function in cls._range_map and range_index in cls._range_map[function]:
            return cls._range_map[function][range_index]
        return None

    @staticmethod
    def _guess_unit(function: str, value: Optional[float]) -> str:
        if function in ("DCV", "ACV") and value is not None:
            if abs(value) < 1.0:
                return "mV"
        return DEFAULT_UNITS.get(function, "?")

    @staticmethod
    def parse(raw: bytes) -> Optional[ParsedData]:
        if len(raw) != 19:
            logger.warning(f"Неверная длина пакета: {len(raw)}")
            return None
        if raw[0] != 0xAB or raw[1] != 0xCD:
            logger.warning("Неверный заголовок пакета")
            return None
        if raw[2] != len(raw) - 3:
            logger.warning(f"Байт длины не совпадает: {raw[2]} != {len(raw)-3}")
            return None

        result = ParsedData()
        b3 = raw[3]
        is_inrush = (b3 & 0x80) != 0

        if is_inrush:
            func_idx = b3 & 0x7F
            result.function2 = DataParser._get_function(func_idx)
            range_idx = DataParser._extract_range(raw[4])
            result.range2_str = range_idx
            result.value2 = DataParser._extract_value(raw[5:12])
            info = DataParser._get_range_info(result.function2, range_idx)
            if info:
                result.unit2 = info["unit"]
            else:
                result.unit2 = DataParser._guess_unit(result.function2, result.value2)
            return result

        func_idx = b3
        result.function = DataParser._get_function(func_idx)
        range_idx = DataParser._extract_range(raw[4])
        result.range_str = range_idx

        info = DataParser._get_range_info(result.function, range_idx)
        if info:
            result.unit = info["unit"]
            result.max_value = info["max"]
            result.min_value = info["min"]
            result.range_str = info["range_str"]
        else:
            result.unit = DataParser._guess_unit(result.function, None)

        raw_value_str = bytes(raw[5:12]).decode('ascii', errors='ignore')
        is_ol, is_negative_ol = DataParser._detect_ol(raw_value_str)
        if is_ol:
            result.is_ol = True
            if is_negative_ol:
                result.value = result.min_value
            else:
                result.value = result.max_value
        else:
            result.value = DataParser._extract_value(raw[5:12])

        if not info and result.value is not None:
            result.unit = DataParser._guess_unit(result.function, result.value)

        if result.value is None and not result.is_ol:
            logger.warning(f"Не удалось извлечь значение: {raw[5:12].hex()} -> {raw[5:12]}")

        result.load_progress = raw[12] * 10 + raw[13]

        flags14 = raw[14]
        result.is_max = (flags14 & 0x08) != 0
        result.is_min = (flags14 & 0x04) != 0
        result.is_hold = (flags14 & 0x02) != 0
        result.is_rel = (flags14 & 0x01) != 0

        flags15 = raw[15]
        result.is_auto = (flags15 & 0x04) == 0
        result.is_battery_low = (flags15 & 0x02) != 0
        result.is_hv_warning = (flags15 & 0x01) != 0

        flags16 = raw[16]
        result.is_dc = (flags16 & 0x08) == 0
        result.is_peak_max = (flags16 & 0x04) != 0
        result.is_peak_min = (flags16 & 0x02) != 0
        result.is_bar_pol = (flags16 & 0x01) != 0

        return result

    @staticmethod
    def _get_function(idx: int) -> str:
        if 0 <= idx < len(FUNCTION_STRINGS):
            return FUNCTION_STRINGS[idx]
        return FUNCTION_STRINGS[-1]

    @staticmethod
    def _extract_range(b: int) -> str:
        return str(b - 48)

    @staticmethod
    def _extract_value(seven_bytes: bytes) -> Optional[float]:
        try:
            raw_str = seven_bytes.decode('ascii', errors='ignore')
            clean = raw_str.strip().replace(" ", "")
            clean = clean.replace(",", ".")
            if not clean:
                return None
            return float(clean)
        except (ValueError, UnicodeDecodeError):
            logger.warning(f"Не удалось преобразовать значение: {seven_bytes.hex()} -> {seven_bytes}")
            return None

    @staticmethod
    def _detect_ol(raw_str: str) -> tuple:
        # Убираем пробелы, точки и любые другие разделители,
        # оставляем только буквы и возможный знак минуса
        clean = raw_str.strip()
        # Удаляем всё, кроме букв и минуса
        clean = ''.join(ch for ch in clean if ch.isalpha() or ch == '-')
        clean = clean.upper()
        
        if not clean:
            return False, False
        
        has_minus = clean.startswith("-")
        if has_minus:
            clean = clean[1:]
        
        # Теперь строка содержит только буквы, например "OL"
        if "OL" in clean:
            return True, has_minus
        return False, False