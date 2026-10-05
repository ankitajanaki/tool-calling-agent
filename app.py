import base64
import binascii
import json
import uuid
from pathlib import Path

import litellm
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator

from tools import TOOLS, run_tool, search_closet, CLOSET_PATH

# --- Config ---

SYSTEM_PROMPT = (
    "You are a concise personal styling assistant. Help users style what they own, "
    "consider the occasion and weather, and find new pieces when requested. "
    "Ask for missing details when needed. Ground recommendations in available information "
    "and be clear about uncertainty."
)
MAX_TOOL_ROUNDS = 5

# --- The Harness ---


def run_agent(messages: list[dict]) -> tuple[str, list[dict]]:
    """Complete until the model answers without asking for a tool.

    Returns the final text and a record of every tool call made along the way.
    """
    tool_calls = []

    for _ in range(MAX_TOOL_ROUNDS):
        reply = litellm.completion(
            model="vertex_ai/gemini-3.5-flash-lite",
            vertex_location="global",
            messages=messages,
            tools=TOOLS,
        ).choices[0].message

        # Append assistant's reply (text, tool calls, or both) to the context.
        # model_dump() keeps it a plain dict: the raw object carries provider-specific
        # fields that trip Pydantic when LiteLLM re-serializes it next round.
        messages += [reply.model_dump()]

        if not reply.tool_calls:
            return reply.content, tool_calls

        # The harness, not the model, runs each tool and appends the result
        for call in reply.tool_calls:
            try:
                args = json.loads(call.function.arguments)
            except (ValueError, TypeError):
                args = None
                result = json.dumps({"error": "Invalid JSON arguments. Retry with a JSON object."})
            else:
                result = run_tool(call.function.name, args)
            tool_calls += [{"name": call.function.name, "args": args, "result": result}]

            messages += [{"role": "tool", "tool_call_id": call.id, "content": result}]

    return "Sorry, I hit my tool-call limit before finishing.", tool_calls


# --- Session Store ---

# session_id -> list of messages. In-memory, single process.
sessions: dict[str, list] = {}

# --- FastAPI App ---

app = FastAPI()
STATIC_PATH = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")


class ChatRequest(BaseModel):
    message: str = ""
    session_id: str | None = None
    image: str | None = Field(default=None, max_length=7_000_000)

    @field_validator("image")
    @classmethod
    def validate_image(cls, value):
        if value is None:
            return value
        header, separator, encoded = value.partition(",")
        allowed = {"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"}
        if not separator or header not in allowed:
            raise ValueError("Upload a JPEG, PNG or WebP image.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid image encoding.")
        if not raw or len(raw) > 5 * 1024 * 1024:
            raise ValueError("Images must be between 1 byte and 5 MB.")
        signatures = {
            "data:image/jpeg;base64": raw.startswith(b"\xff\xd8\xff"),
            "data:image/png;base64": raw.startswith(b"\x89PNG\r\n\x1a\n"),
            "data:image/webp;base64": raw.startswith(b"RIFF") and raw[8:12] == b"WEBP",
        }
        if not signatures[header]:
            raise ValueError("Image content does not match its file type.")
        return value

    @model_validator(mode="after")
    def require_content(self):
        if not self.message.strip() and not self.image:
            raise ValueError("Enter a message or attach an image.")
        return self


class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list[dict]


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "index.html")


@app.get("/closet")
def closet():
    result = json.loads(search_closet())
    if "error" in result:
        raise HTTPException(status_code=500, detail="Could not load the closet.")
    return result


@app.post("/closet/{item_id}/image")
def save_closet_image(item_id: int, request: ChatRequest):
    """Save a user-selected photo locally for an existing wardrobe item."""
    if not request.image:
        raise HTTPException(status_code=400, detail="Attach a photo to save.")
    try:
        items = json.loads(CLOSET_PATH.read_text())
        item = next((item for item in items if item["id"] == item_id), None)
        if item is None:
            raise HTTPException(status_code=404, detail="Closet item not found.")
        header, encoded = request.image.split(",", 1)
        extension = {"data:image/jpeg;base64": "jpg", "data:image/png;base64": "png", "data:image/webp;base64": "webp"}[header]
        filename = f"photo-{item_id}-{uuid.uuid4().hex[:12]}.{extension}"
        (STATIC_PATH / "closet" / filename).write_bytes(base64.b64decode(encoded))
        item["image_url"] = f"/static/closet/{filename}"
        item["image_kind"] = "photo"
        CLOSET_PATH.write_text(json.dumps(items, indent=4) + "\n")
    except (OSError, ValueError):
        raise HTTPException(status_code=500, detail="Could not save the closet photo.")
    return item


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    # Get or create the session
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions:
        sessions[session_id] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Append user's message to the context
    content = request.message
    if request.image:
        content = [
            {"type": "text", "text": request.message.strip() or "Find similar clothing products to those in this photo."},
            {"type": "image_url", "image_url": {"url": request.image}},
        ]
    sessions[session_id] += [{"role": "user", "content": content}]

    try:
        response, tool_calls = run_agent(sessions[session_id])
    except Exception as e:
        # Auth, billing, a model that is not running: show it in the chat, not as a 500.
        response, tool_calls = f"Model call failed: {type(e).__name__}: {str(e)[:300]}", []

    return ChatResponse(response=response, session_id=session_id, tool_calls=tool_calls)


@app.post("/clear")
def clear(session_id: str | None = None):
    sessions.pop(session_id, None)
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
