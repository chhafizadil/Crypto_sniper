from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from utils.logger import log
import psutil
import pandas as pd
import os

app = FastAPI()
templates = Jinja2Templates(directory="dashboard/templates")

@app.get("/")
async def dashboard(request: Request):
    try:
        # Log memory and CPU usage
        memory = psutil.Process().memory_info().rss / 1024 / 1024
        cpu_percent = psutil.cpu_percent(interval=0.1)
        log(f"[Dashboard] Loading - Memory: {memory:.2f} MB, CPU: {cpu_percent:.1f}%")

        # Load signals from signals_log.csv
       signals_file = "logs/signals_log_new.csv"
        if not os.path.exists(signals_file):
            log(f"[Dashboard] Signals file not found at {signals_file}", level='ERROR')
            return templates.TemplateResponse("dashboard.html", {"request": request, "signals": []})

        try:
            signals_df = pd.read_csv(signals_file)
            # Ensure required columns exist
            required_columns = ['symbol', 'direction', 'confidence', 'tp1', 'tp2', 'tp3', 'timestamp']
            missing_columns = [col for col in required_columns if col not in signals_df.columns]
            if missing_columns:
                log(f"[Dashboard] Missing columns in signals file: {missing_columns}", level='ERROR')
                signals = []
            else:
                # Convert to list of dictionaries for template
                signals = signals_df[required_columns].to_dict(orient="records")
                # Format timestamps and numerical values
                for signal in signals:
                    signal['confidence'] = f"{signal['confidence']:.2f}%"
                    signal['tp1'] = f"{signal['tp1']:.4f}"
                    signal['tp2'] = f"{signal['tp2']:.4f}"
                    signal['tp3'] = f"{signal['tp3']:.4f}"
        except Exception as e:
            log(f"[Dashboard] Error reading signals file: {e}", level='ERROR')
            signals = []

        template_path = "dashboard/templates/dashboard.html"
        if not os.path.exists(template_path):
            log(f"[Dashboard] Template not found at {template_path}", level='ERROR')
            return {"error": "Dashboard template not found"}

        log(f"[Dashboard] Rendering template with {len(signals)} signals")
        return templates.TemplateResponse("dashboard.html", {"request": request, "signals": signals})
    except Exception as e:
        log(f"[Dashboard] Error loading dashboard: {e}", level='ERROR')
        return {"error": str(e)}
