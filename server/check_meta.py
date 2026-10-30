"""Check that the Meta Model API key works.

Lists the models the key can use, then asks Muse Spark 1.3 one question:
about a photo if you pass one, otherwise a plain text check.

    .venv\\Scripts\\python.exe check_meta.py [photo.jpg]
"""

import base64
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    key = os.environ.get("MODEL_API_KEY", "").strip()
    if not key:
        sys.exit("MODEL_API_KEY is empty. Paste your key into server/.env.")
    client = OpenAI(base_url=BASE_URL, api_key=key)

    ids = sorted(m.id for m in client.models.list())
    print("Models on this key:", ", ".join(ids))

    if len(sys.argv) > 1:
        photo = Path(sys.argv[1])
        mime = mimetypes.guess_type(photo.name)[0] or "image/jpeg"
        data = base64.b64encode(photo.read_bytes()).decode()
        content = [
            {"type": "input_text",
             "text": "Describe what you see in one or two sentences. "
                     "If it's a toilet, say whether the tank lid is off."},
            {"type": "input_image", "image_url": f"data:{mime};base64,{data}"},
        ]
    else:
        content = [{"type": "input_text",
                    "text": "Reply with one short sentence confirming "
                            "which model you are and that you're ready."}]

    response = client.responses.create(
        model=MODEL, input=[{"role": "user", "content": content}])
    print(f"\n{MODEL} says:\n{response.output_text}")


if __name__ == "__main__":
    main()
