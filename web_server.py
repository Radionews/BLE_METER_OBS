import pathlib
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates"
INDEX_PATH = TEMPLATES_DIR / "index.html"

try:
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        HTML_CONTENT = f.read()
except FileNotFoundError:
    HTML_CONTENT = "<html><body><h1>Error: index.html not found</h1></body></html>"

app = FastAPI(title="Multimeter BLE Server")

class DataBroadcaster:
    def __init__(self):
        self.latest_data = {
            "connected": False,
            "function": "---",
            "value": None,
            "unit": "",
            "range": "",
            "is_ol": False,
            "is_dc": True,
            "is_hold": False,
            "is_rel": False,
            "is_auto": False,
            "battery": 0,
            "is_battery_low": False,
        }

    def update(self, parsed_data):
        self.latest_data = {
            "connected": True,
            "function": parsed_data.function,
            "value": parsed_data.value if not parsed_data.is_ol else "OL",
            "unit": parsed_data.unit,
            "range": parsed_data.range_str,
            "is_ol": parsed_data.is_ol,
            "is_dc": parsed_data.is_dc,
            "is_hold": parsed_data.is_hold,
            "is_rel": parsed_data.is_rel,
            "is_auto": parsed_data.is_auto,
            "battery": parsed_data.load_progress,
            "is_battery_low": parsed_data.is_battery_low,
        }

    def set_disconnected(self):
        self.latest_data["connected"] = False

broadcaster: Optional[DataBroadcaster] = None

@app.get("/api/data")
async def get_data():
    if broadcaster is None:
        return JSONResponse({"connected": False, "error": "no broadcaster"}, status_code=503)
    return broadcaster.latest_data

@app.get("/")
async def root():
    return HTMLResponse(content=HTML_CONTENT)