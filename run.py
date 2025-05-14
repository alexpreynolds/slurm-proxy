import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

from app.constants import (
    APP_PORT,
    APP_HOST,
    APP_DEBUG_MODE,
    APP_USE_RELOADER,
)

from app import create_app

app = create_app()

app.run(
    debug=APP_DEBUG_MODE,
    use_reloader=APP_USE_RELOADER,
    host=APP_HOST,
    port=APP_PORT,
)