from prometheus_client import Counter, Histogram

# Contadores de resultado
OCR_SUCCESS_TOTAL = Counter('ocr_process_success_total', 'Total de processamentos bem-sucedidos')
OCR_REVIEW_TOTAL = Counter('ocr_process_review_total', 'Total de arquivos enviados para revisão')
OCR_FAILURE_TOTAL = Counter('ocr_process_failure_total', 'Total de falhas críticas no pipeline')

# Histograma de latência por status
OCR_LATENCY_SECONDS = Histogram(
    'ocr_process_latency_seconds',
    'Tempo gasto no pipeline de processamento',
    ['status']  # label: success, review, failure
)