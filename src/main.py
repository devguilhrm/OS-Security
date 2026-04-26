import re
import hashlib
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


app = FastAPI(title="OCR Order Service", version="2.2.0", docs_url="/docs", redoc_url=None)
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

def _calculate_hash(file_path: Path) -> str:
    """Calcula SHA-256 do arquivo em chunks para não estourar memória."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _download_s3(bucket: str, key: str, region: str = "us-east-1",
                 aws_access_key_id: str = "", aws_secret_access_key: str = "") -> Path:
    """Baixa arquivo do S3 para o diretório de entrada local."""
    session = boto3.Session(
        aws_access_key_id=aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=region or os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
    )
    s3 = session.resource("s3")
    dest = Config.INPUT_DIR / Path(key).name
    try:
        s3.Bucket(bucket).download_file(key, str(dest))
        return dest
    except ClientError as e:
        raise HTTPException(status_code=400, detail=f"S3 error: {e}")


def route_document(file_path: Path, plate_hint: str = None) -> None:
    """
    Roteia o arquivo recebido para o pipeline correto:
      - PDF        → staging de assinatura virtual (fluxo ERP)
      - Imagem     → pipeline OCR padrão
      - Outros     → descartado para REVIEW_DIR com aviso
    """
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        # Fluxo ERP → PDF → Assinatura Virtual
        Config.SIGNATURE_STAGING_DIR.mkdir(parents=True, exist_ok=True)

        # Extrai placa do nome do arquivo se não informada via query param
        plate = plate_hint
        if not plate:
            match = Config.FILE_PLATE_REGEX.search(file_path.stem)
            plate = match.group(1).upper() if match else "UNKNOWN"

        # Move para diretório de staging de assinatura
        dest_pdf = Config.SIGNATURE_STAGING_DIR / file_path.name
        shutil.move(str(file_path), str(dest_pdf))

        # Calcula hash e registra no DB aguardando assinatura
        file_hash = _calculate_hash(dest_pdf)
        db_manager.register_pending_signature(file_hash, plate, dest_pdf)
        logger.info("📄 PDF roteado para assinatura: %s | Placa: %s", dest_pdf.name, plate)

    elif ext in Config.SUPPORTED_EXTENSIONS:
        # Fluxo padrão: Imagem → OCR → PDF → Arquivamento
        submit_for_processing(file_path)

    else:
        logger.warning("⚠️ Formato não suportado descartado: %s", file_path.name)
        shutil.move(str(file_path), str(Config.REVIEW_DIR / file_path.name))


def submit_for_processing(file_path: Path) -> None:
    """Executa o pipeline OCR e atualiza métricas Prometheus."""
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


def _resolve_pdf_for_plate(plate: str, explicit_path: str = "") -> Path:
    """
    Resolve o caminho do PDF da OS para uma dada placa.

    Prioridade:
      1. Caminho explícito informado pelo caller.
      2. Busca em output/ordens/**/<plate>/<plate>_*.pdf
         — retorna o arquivo mais recente se houver mais de um.
      3. Busca no SIGNATURE_STAGING_DIR para PDFs ainda aguardando assinatura.
    """
    if explicit_path:
        p = Path(explicit_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"PDF não encontrado: {explicit_path}")
        return p

    # Busca em output/ordens (PDFs já arquivados)
    search_root = Path("output/ordens")
    matches = sorted(
        search_root.glob(f"**/{plate}/{plate}_*.pdf"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    # Também busca no staging (PDFs aguardando assinatura)
    if hasattr(Config, "SIGNATURE_STAGING_DIR") and Config.SIGNATURE_STAGING_DIR.exists():
        staging_matches = sorted(
            Config.SIGNATURE_STAGING_DIR.glob(f"{plate}_*.pdf"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        matches = matches + staging_matches

    # Reordena toda a lista combinada pelo mtime
    matches = sorted(matches, key=lambda f: f.stat().st_mtime, reverse=True)

    if not matches:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Nenhum PDF encontrado para a placa '{plate}'. "
                "Informe 'pdf_path' explicitamente ou verifique se a OS já foi processada."
            ),
        )
    if len(matches) > 1:
        logger.warning(
            "⚠️  Múltiplos PDFs encontrados para %s — usando o mais recente: %s",
            plate, matches[0],
        )
    return matches[0]


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
# Rotas de ingestão (v2.2 — suporte a PDF + imagem com roteamento automático)
# ---------------------------------------------------------------------------

@app.post("/ingest")
async def ingest_http(
    file: UploadFile = File(...),
    plate: str = Query(None, description="Placa explícita (opcional, extraída do nome do arquivo se omitida)"),
    background_tasks: BackgroundTasks = None,
):
    """
    Recebe PDF ou imagem via HTTP multipart e roteia automaticamente:
      - PDF   → staging de assinatura virtual (fluxo ERP)
      - Imagem → pipeline OCR

    O parâmetro `plate` é opcional: se omitido, a placa é extraída do nome
    do arquivo via Config.FILE_PLATE_REGEX.
    """
    allowed_mime = {
        "application/pdf",
        "image/jpeg", "image/png", "image/tiff", "image/bmp", "image/webp",
    }
    if file.content_type not in allowed_mime:
        raise HTTPException(status_code=400, detail="MIME não suportado. Use PDF ou imagens comuns.")

    dest = Config.INPUT_DIR / file.filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    background_tasks.add_task(route_document, dest, plate)
    flow = "assinatura" if dest.suffix.lower() == ".pdf" else "OCR"
    return {"message": f"✅ {file.filename} enfileirado para {flow}"}


@app.post("/ingest-s3")
async def ingest_s3(
    bucket: str = Query(..., description="Nome do bucket S3"),
    key: str = Query(..., description="Chave do objeto no S3"),
    plate: str = Query(None, description="Placa explícita (opcional)"),
    region: str = Query("us-east-1", description="Região AWS"),
    background_tasks: BackgroundTasks = None,
):
    """
    Baixa arquivo do S3 e roteia para assinatura (PDF) ou OCR (imagem).
    Credenciais lidas de AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY do ambiente.
    """
    dest = _download_s3(bucket=bucket, key=key, region=region)
    background_tasks.add_task(route_document, dest, plate)
    flow = "assinatura" if dest.suffix.lower() == ".pdf" else "OCR"
    return {"message": f"✅ S3://{bucket}/{key} enfileirado para {flow}"}


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