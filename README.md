# Multimeter BLE Server

Приложение для подключения к мультиметрам UNI-T через BLE, отображения измерений в реальном времени и интеграции в OBS Studio.
[Поддержать автора](https://donatty.com/radionews)

## Возможности

- **BLE-подключение** к мультиметрам UNI-T (Протестировано с UT60BT)
- **Локальный веб-сервер** с простым JSON API
- **Готовый HTML-виджет** для OBS с отображением измерений
- **Автоматическое переподключение** при потере связи
- **Работа в фоне** (иконка в системном трее)

## Установка

```bash
git clone https://github.com/yourname/multimeter-ble-server.git
cd multimeter-ble-server
pip install -r requirements.txt
```

## Зависимости

- `bleak` – работа с BLE
- `fastapi` + `uvicorn` – веб-сервер
- `pystray` + `Pillow` – иконка в трее

## Быстрый старт

1. **Выбор устройства**  
   Запустите без аргументов для интерактивной настройки:
   ```bash
   python multimeter_ble.py
   ```
   Отсканируется список BLE-устройств, выберите нужное. Настройки сохранятся в `config.json`.

2. **Запуск веб-сервера** (окно консоли останется открытым):
   ```bash
   python multimeter_ble.py --serve
   ```
   Сервер слушает порт `8080` (можно изменить через `--port`).

3. **Откройте в браузере**  
   Перейдите по адресу `http://localhost:8080`. Вы увидите виджет мультиметра.

4. **Добавление в OBS**  
   В OBS добавьте источник «Браузер» → укажите URL `http://localhost:8080`
   Версия с 7 сегментными цифрами `http://localhost:8080/7seg`
   Рекомендуемая ширина 400, высота 100.

## Аргументы командной строки

- --scan          Просканировать BLE-устройства и выйти
- --serve         Запустить веб-сервер и BLE-подключение в консоли
- --tray          Запустить в трее (без консоли)
- --test          Подключиться к мультиметру и выводить данные в консоль (без сервера)
- --port PORT     Изменить порт веб-сервера (по умолчанию 8080)
- --config PATH   Путь к файлу конфигурации
- --debug         Включить запись подробных логов в multimeter_ble.log

## Фоновая работа (трей)

Запуск без окна, с иконкой в трее:

```bash
pythonw multimeter_ble.py --tray
```

Или через скрипт `start_hidden.bat`:

```bat
start "" pythonw.exe multimeter_ble.py --tray > nul 2>&1
```

## REST API

Сервер предоставляет три эндпоинта:

### 1. HTML-виджет

`GET /`

Возвращает встроенную HTML-страницу. Её можно заменить на свою (см. раздел «Кастомизация»).

### 2. HTML-виджет

`GET /7seg`

Возвращает встроенную HTML-страницу с цифрами в стиле 7 сегментных индикаторов.

### 3. Данные в JSON

`GET /api/data`

Ответ всегда содержит актуальное состояние мультиметра.

**Пример ответа:**

```json
{
  "connected": true,
  "function": "DCV",
  "value": 12.34,
  "unit": "V",
  "range": "99.99V",
  "is_ol": false,
  "is_dc": true,
  "is_hold": false,
  "is_rel": false,
  "is_auto": true,
  "battery": 85,
  "is_battery_low": false
}
```

**Поля:**

| Поле           | Тип      | Описание |
|----------------|----------|----------|
| `connected`    | bool     | Есть ли активное BLE-соединение |
| `function`     | string   | Режим работы: `DCV`, `ACV`, `OHM`, `CAP`, `Hz`, `°C` и др. |
| `value`        | float|null  | Числовое значение или `"OL"` (перегрузка) |
| `unit`         | string   | Единица измерения (`V`, `mV`, `Ω`, `kΩ`, `μF`…) |
| `range`        | string   | Текущий предел (например `"99.99V"`) |
| `is_ol`        | bool     | Перегрузка (Over Limit) |
| `is_dc`        | bool     | Постоянный ток (`true`) или переменный (`false`) |
| `is_hold`      | bool     | Режим HOLD |
| `is_rel`       | bool     | Режим REL |
| `is_auto`      | bool     | Автоматический выбор предела |
| `battery`      | int      | Заряд батареи 0–100 (0 если нет данных) |
| `is_battery_low` | bool    | Низкий заряд |

> В случае ошибки возвращается `{"connected": false}` плюс может быть поле `error`.

## Кастомизация HTML-виджета

Вы можете написать собственный `index.html` и положить его в папку `templates/`. При этом доступны следующие возможности:

* **Опрос данных**  
  Ваша страница может запрашивать JSON с `api/data` с помощью `fetch()` и обновлять интерфейс.

* **Рекомендуемая частота опроса**  
  Каждые 200–300 мс достаточно для плавного обновления.

* **Пример минимальной страницы**

```html
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { background: black; color: yellow; font: bold 48px monospace; }
    </style>
</head>
<body>
    <div id="display">--</div>
    <script>
        setInterval(async () => {
            const res = await fetch('/api/data');
            const data = await res.json();
            if (data.connected) {
                document.getElementById('display').innerText =
                    (data.is_ol ? 'OL' : data.value) + ' ' + data.unit;
            } else {
                document.getElementById('display').innerText = '---';
            }
        }, 200);
    </script>
</body>
</html>
```

Замените стандартный файл в `templates/index.html` и перезапустите сервер.

## Поддерживаемые режимы мультиметра

- `AC V / DC V` – переменное/постоянное напряжение
- `AC mV / DC mV` – милливольты
- `RES` – сопротивление (Ω, кΩ, МΩ)
- `CAP` – ёмкость (нФ, мкФ, мФ)
- `Hz` – частота (Гц, кГц, МГц)
- `%` – коэффициент заполнения (duty cycle)
- `DC A / AC A` – сила тока (мкА, мА, А)
- `°C / °F` – температура
- `CONT` – прозвонка
- `Diode` – проверка диодов

Точные единицы и диапазоны загружаются из JSON-файла `funOl_<модель>.json` (рядом со скриптом). Для модели `UT60BT` используется файл `funOl_UT6.json`.

## Файл конфигурации

`config.json` создаётся автоматически:

```json
{
  "device_address": "AA:BB:CC:DD:EE:FF",
  "device_name": "UT6",
  "web_port": 8080
}
```

## Лицензия

OSL-3.0