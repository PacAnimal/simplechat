import asyncio
import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import get_current_profile
from ..config import settings
from ..database import get_db
from ..models import Dataset, DatasetFile, Profile
from ..rag.embedder import EMBED_MODEL
from ..rag.indexer import DATASET_ALLOWED_MIME_TYPES, index_file, reindex_dataset
from ..rag.store import delete_collection
from ..schemas import DatasetCreate, DatasetFileMeta, DatasetRead

logger = logging.getLogger("simplechat.api.datasets")
router = APIRouter(prefix="/datasets", tags=["datasets"])

MAX_FILE_SIZE = 20 * 1024 * 1024


async def _get_owned_dataset(dataset_id: int, profile_id: int, db: AsyncSession) -> Dataset:
    ds = await db.get(Dataset, dataset_id)
    if not ds or ds.profile_id != profile_id:
        raise HTTPException(404, "Dataset not found")
    return ds


def _ollama_url() -> str:
    url = settings.ollama_api_url
    if not url:
        raise HTTPException(503, "Ollama is not configured on this server")
    return url


@router.get("", response_model=list[DatasetRead])
async def list_datasets(
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dataset)
        .where(Dataset.profile_id == profile.id)
        .options(selectinload(Dataset.files))
        .order_by(Dataset.created_at)
    )
    return result.scalars().all()


@router.post("", response_model=DatasetRead, status_code=201)
async def create_dataset(
    body: DatasetCreate,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    ds = Dataset(profile_id=profile.id, name=body.name)
    db.add(ds)
    await db.commit()
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == ds.id)
        .options(selectinload(Dataset.files))
    )
    return result.scalar_one()


@router.get("/{dataset_id}", response_model=DatasetRead)
async def get_dataset(
    dataset_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Dataset)
        .where(Dataset.id == dataset_id, Dataset.profile_id == profile.id)
        .options(selectinload(Dataset.files))
    )
    ds = result.scalar_one_or_none()
    if not ds:
        raise HTTPException(404, "Dataset not found")
    return ds


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_owned_dataset(dataset_id, profile.id, db)
    await asyncio.to_thread(delete_collection, dataset_id)
    await db.delete(ds)
    await db.commit()


@router.post("/{dataset_id}/files", response_model=DatasetFileMeta)
async def upload_dataset_file(
    dataset_id: int,
    file: UploadFile = File(...),
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    base_url = _ollama_url()
    ds = await _get_owned_dataset(dataset_id, profile.id, db)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 20 MB)")

    mime = file.content_type or "application/octet-stream"
    if mime not in DATASET_ALLOWED_MIME_TYPES:
        raise HTTPException(
            415,
            "Unsupported type. Supported: text, csv, json, pdf, Excel, Word, PowerPoint",
        )

    safe_name = os.path.basename((file.filename or "file").replace("\r", "").replace("\n", "")) or "file"
    df = DatasetFile(
        dataset_id=ds.id,
        filename=safe_name,
        mime_type=mime,
        content=content,
        size=len(content),
    )
    db.add(df)
    await db.commit()
    await db.refresh(df)

    try:
        chunk_count = await asyncio.to_thread(
            index_file, dataset_id, df.id, safe_name, content, mime, base_url, EMBED_MODEL
        )
        logger.info("upload: indexed %d chunks for %s in dataset %d", chunk_count, safe_name, dataset_id)
    except Exception:
        logger.warning(
            "upload: indexing failed for %s in dataset %d — file saved, collection not updated",
            safe_name, dataset_id, exc_info=True,
        )

    return df


@router.delete("/{dataset_id}/files/{file_id}", status_code=204)
async def delete_dataset_file(
    dataset_id: int,
    file_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_owned_dataset(dataset_id, profile.id, db)

    df = await db.get(DatasetFile, file_id)
    if not df or df.dataset_id != dataset_id:
        raise HTTPException(404, "File not found")

    await db.delete(df)
    await db.commit()

    base_url = settings.ollama_api_url
    if base_url:
        result = await db.execute(
            select(DatasetFile).where(DatasetFile.dataset_id == dataset_id)
        )
        remaining = result.scalars().all()
        await asyncio.to_thread(reindex_dataset, dataset_id, remaining, base_url, EMBED_MODEL)
    else:
        await asyncio.to_thread(delete_collection, dataset_id)


@router.post("/{dataset_id}/reindex", status_code=204)
async def reindex(
    dataset_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    base_url = _ollama_url()
    ds = await _get_owned_dataset(dataset_id, profile.id, db)

    result = await db.execute(
        select(DatasetFile).where(DatasetFile.dataset_id == dataset_id)
    )
    files = result.scalars().all()
    await asyncio.to_thread(reindex_dataset, dataset_id, files, base_url, EMBED_MODEL)
