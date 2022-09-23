import os

from app import create_app
from app.storage import Storage
from app.exchange import GateioSpot


secret_code = os.environ["ACCESS_CODE"]
store = Storage(os.environ["DATA"])
api_key, api_secret = os.environ["GATE_IO_KEY"], os.environ["GATE_IO_SECRET"]
client = GateioSpot(api_key, api_secret)
app = create_app(client, store, secret_code)


app.run(debug=os.environ.get("DEBUG") is not None,
        host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), threaded=True)
