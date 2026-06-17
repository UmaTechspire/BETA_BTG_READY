from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..database import get_db
from ..models.pr_attachment import PrAttachment

router = APIRouter(
    prefix="/pr/attachment",
    tags=["PR Attachment"],
    responses={404: {"description": "Not found"}},
)

@router.delete("/{prattachid}")
async def delete_pr_attachment(prattachid: int, db: AsyncSession = Depends(get_db)):
    """
    Hard delete the attachment row from the database.
    """
    # Check if exists first
    result = await db.execute(select(PrAttachment).where(PrAttachment.prattachid == prattachid))
    attachment = result.scalars().first()
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Hard delete the row
    try:
        await db.execute(delete(PrAttachment).where(PrAttachment.prattachid == prattachid))
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Database delete failed: {str(e)}")

    return {"status": True, "message": "Attachment deleted successfully"}
