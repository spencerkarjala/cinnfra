"""Small API and static server for composing reference mood boards."""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from config import ARTWORK_DIR, STATIC_DIR
from database import (
    add_board_item,
    create_board,
    delete_board,
    delete_board_item,
    get_all_boards,
    get_all_references,
    get_board,
    get_board_items,
    init_database,
    replace_board_items,
)


class BoardItemRequest(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    reference_id: str = Field(min_length=1, max_length=100)
    position_x: float
    position_y: float
    width: float = Field(ge=40, le=6000)
    height: float = Field(ge=40, le=6000)


class BoardItemResponse(BoardItemRequest):
    pass


class BoardResponse(BaseModel):
    id: str
    name: str
    created_at: str
    items: list[BoardItemResponse] = Field(default_factory=list)


class CreateBoardRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Board name cannot be blank")
        return value


class UpdateBoardItemsRequest(BaseModel):
    items: list[BoardItemRequest] = Field(max_length=2000)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_database()
    yield


app = FastAPI(
    title="Reference Visualizer",
    description="Compose saved reference media into mood boards",
    lifespan=lifespan,
)


async def board_response(board: dict) -> BoardResponse:
    items = await get_board_items(board["id"])
    return BoardResponse(
        id=board["id"],
        name=board["name"],
        created_at=board["created_at"],
        items=[BoardItemResponse(**item) for item in items],
    )


@app.get("/api/references")
async def list_references():
    return await get_all_references()


@app.get("/api/artwork/{filename}")
async def get_artwork(filename: str):
    artwork_root = ARTWORK_DIR.resolve()
    file_path = (artwork_root / filename).resolve()
    if file_path.parent != artwork_root or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(file_path)


@app.get("/api/boards", response_model=list[BoardResponse])
async def list_boards():
    return [await board_response(board) for board in await get_all_boards()]


@app.post("/api/boards", response_model=BoardResponse, status_code=201)
async def create_board_endpoint(request: CreateBoardRequest):
    board = await create_board(str(uuid.uuid4()), request.name)
    return BoardResponse(**board, items=[])


@app.get("/api/boards/{board_id}", response_model=BoardResponse)
async def get_board_endpoint(board_id: str):
    board = await get_board(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="Board not found")
    return await board_response(board)


@app.delete("/api/boards/{board_id}")
async def delete_board_endpoint(board_id: str):
    if not await delete_board(board_id):
        raise HTTPException(status_code=404, detail="Board not found")
    return {"deleted": board_id}


@app.put("/api/boards/{board_id}/items")
async def update_items_endpoint(board_id: str, request: UpdateBoardItemsRequest):
    if await get_board(board_id) is None:
        raise HTTPException(status_code=404, detail="Board not found")
    items = [item.model_dump() for item in request.items]
    await replace_board_items(board_id, items)
    return {"updated": len(items)}


@app.post(
    "/api/boards/{board_id}/items",
    response_model=BoardItemResponse,
    status_code=201,
)
async def add_item_endpoint(board_id: str, request: BoardItemRequest):
    if await get_board(board_id) is None:
        raise HTTPException(status_code=404, detail="Board not found")
    await add_board_item(
        request.id,
        board_id,
        request.reference_id,
        request.position_x,
        request.position_y,
        request.width,
        request.height,
    )
    return BoardItemResponse(**request.model_dump())


@app.delete("/api/boards/{board_id}/items/{item_id}")
async def delete_item_endpoint(board_id: str, item_id: str):
    if not await delete_board_item(board_id, item_id):
        raise HTTPException(status_code=404, detail="Item not found")
    return {"deleted": item_id}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
