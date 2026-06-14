from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os

load_dotenv()

mongo_uri = os.getenv("MONGO_URI")

client = AsyncIOMotorClient(
    mongo_uri,
    serverSelectionTimeoutMS=5000
)

db = client["smart_hub_2026"]

settings_collection = db["settings"]
data_collection = db["sensor_data"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Settings(BaseModel):
    user_temp: float
    user_light: str
    light_duration: str


class SensorData(BaseModel):
    temperature: float
    presence: bool


def calculate_light_time_off(user_light: str, light_duration: str):
    start_time = datetime.strptime(user_light, "%H:%M:%S")

    duration = light_duration.lower().strip()

    if duration.endswith("h"):
        delta = timedelta(hours=int(duration.replace("h", "")))
    elif duration.endswith("m"):
        delta = timedelta(minutes=int(duration.replace("m", "")))
    elif duration.endswith("s"):
        delta = timedelta(seconds=int(duration.replace("s", "")))
    else:
        delta = timedelta(hours=int(duration))

    off_time = start_time + delta

    return off_time.strftime("%H:%M:%S")


@app.get("/")
def root():
    return {"message": "Welcome to my Smart Hub API!"}


@app.put("/settings")
async def update_settings(settings: Settings):
    settings_data = settings.model_dump()

    settings_data["light_time_off"] = calculate_light_time_off(
        settings.user_light,
        settings.light_duration
    )

    await settings_collection.delete_many({})
    await settings_collection.insert_one(settings_data)

    settings_data.pop("_id", None)

    return {
        "message": "Settings updated successfully",
        "settings": settings_data
    }


@app.post("/data", status_code=status.HTTP_201_CREATED)
async def create_sensor_data(data: SensorData):
    data_record = data.model_dump()

    if data_record["temperature"] <= -100 or data_record["temperature"] >= 100:
        raise HTTPException(
            status_code=400,
            detail="Invalid temperature reading"
        )

    data_record["datetime"] = datetime.now().isoformat()

    await data_collection.insert_one(data_record)

    count = await data_collection.count_documents({})

    if count > 300:
        old_records = data_collection.find(
            {},
            {"_id": 1}
        ).sort("datetime", 1).limit(count - 300)

        old_ids = []

        async for record in old_records:
            old_ids.append(record["_id"])

        if old_ids:
            await data_collection.delete_many({"_id": {"$in": old_ids}})

    data_record.pop("_id", None)

    return {
        "message": "Sensor data saved successfully",
        "data": data_record
    }


@app.get("/state")
async def get_state():
    settings = await settings_collection.find_one({}, {"_id": 0})

    if not settings:
        settings = {
            "user_temp": 30,
            "user_light": "19:30:00",
            "light_duration": "4h",
            "light_time_off": "23:30:00"
        }

    latest_data = await data_collection.find_one(
        {},
        {"_id": 0},
        sort=[("datetime", -1)]
    )

    if not latest_data:
        return {
            "fan": False,
            "light": False
        }

    fan = (
        latest_data["temperature"] > settings["user_temp"]
        and latest_data["presence"]
    )

    current_time = datetime.now().strftime("%H:%M:%S")

    start = settings["user_light"]
    end = settings["light_time_off"]

    if start <= end:
        time_active = start <= current_time <= end
    else:
        time_active = current_time >= start or current_time <= end

    light = latest_data["presence"] and time_active

    return {
        "fan": fan,
        "light": light
    }


@app.get("/graph")
async def get_graph_data(size: int = 10):
    if size <= 0:
        raise HTTPException(
            status_code=400,
            detail="Size must be greater than 0"
        )

    graph_data = []

    cursor = data_collection.find(
        {},
        {"_id": 0}
    ).sort("datetime", -1).limit(size)

    async for record in cursor:
        graph_data.append(record)

    graph_data.reverse()

    return graph_data


@app.delete("/data")
async def clear_sensor_data():
    await data_collection.delete_many({})
    return {"message": "All sensor data cleared"}