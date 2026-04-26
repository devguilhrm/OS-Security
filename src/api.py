import logging
import shutil
import time
import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from src.metrics import OCR_SUCCESS_TOTAL, OCR_REVIEW_TOTAL, OCR_FAILURE_TOTAL, OCR_LATENCY_SECONDS
from src.config import Config
from src.database import DBManager
from src.pipeline import process_image
from src.fleet_mapping import get_fleet_mapper
from src.signature_service import SignatureService
import boto3
from botocore.exceptions import ClientError
import uvicorn
from fastapi import Request, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import time

 
app = FastAPI(title="OCR Order Service", version="2.1.0", docs_url="/docs", redoc_url=None)
logger = logging.getLogger(__name__)
 
db_manager: DBManager = None
sig_service: SignatureService = None
executor = None
 
 
# ---------------------------------------------------------------------------
# Startup / shutdown
# ---------------------------------------------------------------------------
 
@app.on_event("startup")
async def startup_event():
    global db_manager, sig_service
    db_manager = DBManager(Config.DB_PATH)
    sig_service = SignatureService(db_manager)
    logger.info("✅ DBManager e SignatureService inicializados")
 
 
@app.on_event("shutdown")
async def shutdown_event():
    if db_manager and db_manager.conn:
        db_manager.conn.close()
        logger.info("🔒 Conexão com o banco encerrada")
 
 
# ---------------------------------------------------------------------------
# Static files (UI de assinatura)
# ---------------------------------------------------------------------------
 
app.mount("/static", StaticFiles(directory="static"), name="static")
 
 
# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
 
class S3IngestRequest(BaseModel):
    bucket: str
    key: str
    region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
 
 
class SignVirtualRequest(BaseModel):
    plate: str
    signature: str                          # base64 da imagem de assinatura
    signatory_name: str = "Cliente"
    signatory_role: str = "Responsável"
    reason: str = "Aceite OS"
    pdf_path: str = ""                      # opcional: caminho explícito do PDF
 
 
# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
 
def _download_s3(req: S3IngestRequest) -> Path:
    session = boto3.Session(
        aws_access_key_id=req.aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=req.aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=req.region or os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )
    s3 = session.resource("s3")
    dest = Config.INPUT_DIR / Path(req.key).name
    try:
        s3.Bucket(req.bucket).download_file(req.key, str(dest))
        return dest
    except ClientError as e:
        raise HTTPException(status_code=400, detail=f"S3 error: {e}")
 
 
def _resolve_pdf_for_plate(plate: str, explicit_path: str = "") -> Path:
    """
    Resolve o caminho do PDF da OS para uma dada placa.
 
    Prioridade:
      1. Caminho explícito informado pelo caller.
      2. Busca no diretório de saída padrão  output/ordens/<COMPANY>/<plate>/<plate>_*.pdf
         — retorna o arquivo mais recente se houver mais de um.
    """
    if explicit_path:
        p = Path(explicit_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"PDF não encontrado: {explicit_path}")
        return p
 
    # Busca genérica em toda a árvore de output
    search_root = Path("output/ordens")
    matches = sorted(search_root.glob(f"**/{plate}/{plate}_*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
 
    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhum PDF encontrado para a placa '{plate}'. "
                   "Informe 'pdf_path' explicitamente ou verifique se a OS já foi processada.",
        )
    if len(matches) > 1:
        logger.warning(
            "⚠️  Múltiplos PDFs encontrados para %s — usando o mais recente: %s",
            plate, matches[0],
        )
    return matches[0]
 
 
def submit_for_processing(file_path: Path):
    start = time.perf_counter()
    status = "success"
    try:
        success = process_image(file_path, db_manager)
        if success:
            OCR_SUCCESS_TOTAL.inc()
        else:
            OCR_REVIEW_TOTAL.inc()
            status = "review"
    except Exception as e:
        logger.error("❌ Pipeline falhou para %s: %s", file_path.name, e)
        OCR_FAILURE_TOTAL.inc()
        status = "failure"
        try:
            shutil.move(str(file_path), str(Config.REVIEW_DIR / file_path.name))
        except Exception:
            pass
    finally:
        latency = time.perf_counter() - start
        OCR_LATENCY_SECONDS.labels(status=status).observe(latency)
 
 
# ---------------------------------------------------------------------------
# Rotas de infraestrutura
# ---------------------------------------------------------------------------
 
@app.get("/health")
def health():
    return {"status": "ok", "service": "ocr-automation"}
 
 
@app.get("/ready")
def readiness():
    checks = {
        "tesseract": True,
        "database": db_manager is not None and db_manager.conn is not None,
        "input_dir": Config.INPUT_DIR.exists(),
        "output_dir": Config.BASE_DIR.exists(),
    }
    if not all(checks.values()):
        raise HTTPException(status_code=503, detail={"checks": checks})
    return {"status": "ready", "checks": checks}
 
 
@app.get("/metrics")
def metrics_endpoint():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
 
 
# ---------------------------------------------------------------------------
# Rotas de negócio — frotas
# ---------------------------------------------------------------------------
 
@app.get("/api/v1/fleets")
def get_fleet_mappings(company: str = Query(None, description="Filtrar por código da empresa")):
    """Consulta as regras ativas de mapeamento de frotas em tempo real."""
    mapper = get_fleet_mapper()
    rules = mapper.get_rules()
    if company:
        rules = [r for r in rules if r.get("company", "").upper() == company.upper()]
    return {"status": "ok", "total_rules": len(rules), "mappings": rules}
 
 
# ---------------------------------------------------------------------------
# Rotas de ingestão
# ---------------------------------------------------------------------------
 
@app.post("/ingest")
async def ingest_http(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
):
    allowed = {"image/jpeg", "image/png", "image/tiff", "image/bmp", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Formato de imagem não suportado")
    dest = Config.INPUT_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    background_tasks.add_task(submit_for_processing, dest)
    return {"message": f"✅ {file.filename} enfileirado para processamento"}
 
 
@app.post("/ingest-s3")
async def ingest_s3(req: S3IngestRequest, background_tasks: BackgroundTasks = None):
    dest = _download_s3(req)
    background_tasks.add_task(submit_for_processing, dest)
    return {"message": f"✅ S3://{req.bucket}/{req.key} baixado e enfileirado"}
 
 
# ---------------------------------------------------------------------------
# Rotas de assinatura virtual
# ---------------------------------------------------------------------------
 
@app.get("/sign", response_class=HTMLResponse)
def signature_page(plate: str = "ABC1D23"):
    """
    Carrega a página de coleta de assinatura digital para a placa informada.
    O HTML estático em /static/signature.html recebe a placa via query string
    e, ao submeter, chama POST /api/v1/sign-virtual.
    """
    return (
        f"<iframe "
        f"src='/static/signature.html?plate={plate}' "
        f"width='100%' height='500px' style='border:none;'>"
        f"</iframe>"
    )
 
 
@app.post("/api/v1/sign-virtual")
async def sign_virtual(payload: SignVirtualRequest, request: Request):
    """
    Aplica assinatura virtual em PDF de OS.
 
    Body (JSON):
        plate           – Placa do veículo (obrigatório)
        signature       – Assinatura em base64 (obrigatório)
        signatory_name  – Nome do signatário (padrão: "Cliente")
        signatory_role  – Cargo/função (padrão: "Responsável")
        reason          – Motivo do aceite (padrão: "Aceite OS")
        pdf_path        – Caminho explícito do PDF (opcional; se omitido,
                          o serviço localiza automaticamente via placa)
    """
    if not payload.plate:
        raise HTTPException(status_code=422, detail="Campo 'plate' é obrigatório")
    if not payload.signature:
        raise HTTPException(status_code=422, detail="Campo 'signature' é obrigatório")
 
    pdf_path = _resolve_pdf_for_plate(payload.plate, payload.pdf_path)
 
    # Captura o IP real mesmo atrás de proxy reverso
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP", "")
        or (request.client.host if request.client else "unknown")
    )
 
    try:
        result = await sig_service.apply_virtual_signature(
            plate=payload.plate,
            pdf_path=pdf_path,
            signature_b64=payload.signature,
            signatory_name=payload.signatory_name,
            signatory_role=payload.signatory_role,
            client_ip=client_ip,
            reason=payload.reason,
        )
    except Exception as e:
        logger.error("❌ Falha ao aplicar assinatura para placa %s: %s", payload.plate, e)
        raise HTTPException(status_code=500, detail=f"Erro ao aplicar assinatura: {e}")
 
    return result
 
 
# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

# 🆕 Schema de validação
class VirtualSignaturePayload(BaseModel):
    plate: str = Field(..., pattern=r"^[A-Z0-9\-]{6,8}$", description="Placa no formato Mercosul ou antigo")
    signature: str = Field(..., description="Base64 da assinatura (data:image/png;base64,...)")
    signatory_name: str = Field(..., min_length=2, max_length=100)
    signatory_role: str = Field(..., min_length=2, max_length=50)
    reason: str = Field(default="Aceite e conferência da OS", max_length=200)

# 🆕 Extração segura de IP (proxy-aware)
def get_client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip", "")
    return xri or (request.client.host if request.client else "127.0.0.1")

# 🆕 Endpoint de assinatura virtual
@app.post("/api/v1/sign-virtual")
async def sign_virtual(request: Request, payload: VirtualSignaturePayload):
    client_ip = get_client_ip(request)
    try:
        result = await sig_service.apply_virtual_signature(
            plate=payload.plate.upper(),
            signature_b64=payload.signature,
            signatory_name=payload.signatory_name,
            signatory_role=payload.signatory_role,
            client_ip=client_ip,
            reason=payload.reason
        )
        result["timestamp"] = time.time()
        return JSONResponse(content=result, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"💥 Erro não tratado em /sign-virtual: {e}")
        raise HTTPException(status_code=500, detail="Falha interna no serviço de assinatura")    