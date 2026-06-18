from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import engine, Base

# 1. IMPORT THE ROUTERS
from .routers import finance, invoice_api, bankbook, procurement, claim_payment, cashbook, gas_master
from .routers import procurement_memo
app = FastAPI(title="Finance API (Python)")

# Allow CORS
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. INCLUDE THE ROUTERS

# Existing Finance Router
app.include_router(finance.router)

# Existing Invoice Router (Prefix removed as per user request)
app.include_router(invoice_api.router, prefix="/pyapi", tags=["Invoices"])
app.include_router(gas_master.router, prefix="/pyapi/MasterGas", tags=["Gas Master"])

# --- NEW: Include BankBook Router ---
# Since your request URL was /api/AR/..., we must add the /api prefix here too.
# User requested /AR/... so removing /api prefix to make it accessible at root /AR
app.include_router(bankbook.router, tags=["Bank Book"]) 

# Including CashBook Router (Missing previously)
# cashbook router already has prefix="/AR/cash"
app.include_router(cashbook.router, tags=["Cash Book"])

# Include Procurement Router
app.include_router(procurement.router, tags=["Procurement"]) 


# Include PPP Router
#app.include_router(ppp.router, prefix="/api", tags=["Periodic Payment Plan"]) 

# Include Claim Payment Router
app.include_router(claim_payment.router) 


from .routers import pr_attachment
app.include_router(pr_attachment.router) 

app.include_router(procurement_memo.router)

from .routers import ledger
app.include_router(ledger.router)



# Include Download File Router
from .routers import download_file
app.include_router(download_file.router)

from .routers import dn_cn
app.include_router(dn_cn.router)

from .routers import journal
app.include_router(journal.router)

from .routers import petty_cash
app.include_router(petty_cash.router)

from .routers import overdraft
from .routers import salescommissionreport
from .routers import opening_balance

app.include_router(overdraft.router)
app.include_router(salescommissionreport.router)
app.include_router(opening_balance.router)
# Auto-create new tables (e.g. tbl_overdraft) if they don't exist yet
from .models.overdraft import TblOverDraft  # noqa: ensure model is registered
@app.on_event("startup")
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

@app.get("/")
def read_root():
    return {"message": "Finance API is running"}