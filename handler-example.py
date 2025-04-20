import time
import logging
from uuid import uuid4
from fastapi import HTTPException, Depends
from pydantic import BaseModel
from app import app
from dependencies.session import get_current_user
from shared.user import AuthUser
from dependencies.dynamodb import get_dataset_table

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatasetCreateRequest(BaseModel):
    """Request model for creating a dataset."""
    url: str
    name: str
    columnsConfig: dict
    customData: dict = None

@app.post("/dataset", tags=["Client/Dataset"])
async def create_dataset(
    dataset: DatasetCreateRequest,
    user: AuthUser = Depends(get_current_user),
    table = Depends(get_dataset_table)
):
    """Create a new dataset."""
    try:
        dataset_id = str(uuid4())
        dataset_item = {
            "id": dataset_id,
            "userId": user.identities[0].userId,
            "name": dataset.name,
            "url": dataset.url,
            "columnsConfig": dataset.columnsConfig,
            "createdAt": int(time.time()),
            "customData": dataset.customData or {},
        }

        logger.info(f"📦 Creating dataset: {dataset.name}")
        table.put_item(Item=dataset_item)

        logger.info(f"✅ Dataset created with ID: {dataset_id}")
        return {"message": "Dataset created successfully", "datasetId": dataset_id}

    except Exception as e:
        logger.error(f"Failed to create dataset: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Failed to create dataset"
        )
