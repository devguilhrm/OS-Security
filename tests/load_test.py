#!/usr/bin/env python3
"""
Load Test para Automação de Ordens de Serviço
Simula queda de imagens em INPUT_DIR e monitora PROCESSAD/REVISÃO
Uso: python tests/load_test.py --source ./sample_images --count 50 --rate 2
"""

import argparse
import logging
import shutil
import statistics
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

@dataclass
class TestMetrics:
    total_files: int = 0
    processed: int = 0
    reviewed: int = 0
    failed_to_track: int = 0
    latencies: List[float] = field(default_factory=list)
    start_time: float = 0.0

    def add_success(self, latency: float):
        self.processed += 1
        self.latencies.append(latency)

    def add_review(self, latency: float):
        self.reviewed += 1
        self.latencies.append(latency)

    def report(self):
        duration = time.time() - self.start_time
        throughput = self.total_files / duration if duration > 0 else 0
        avg_lat = statistics.mean(self.latencies) if self.latencies else 0
        min_lat = min(self.latencies) if self.latencies else 0
        max_lat = max(self.latencies) if self.latencies else 0
        p95_lat = statistics.median(self.latencies) if self.latencies else 0  # Simplificado

        print("\n" + "="*60)
        print("📊 RELATÓRIO DE TESTE DE CARGA")
        print("="*60)
        print(f"⏱️  Duração Total       : {duration:.2f}s")
        print(f"📥 Throughput           : {throughput:.2f} arquivos/s")
        print(f"✅ Processados         : {self.processed}")
        print(f"⚠️  Enviados p/ Revisão : {self.reviewed}")
        print(f"❌ Não rastreados       : {self.failed_to_track}")
        print(f"📈 Latência Média       : {avg_lat:.3f}s")
        print(f"📉 Latência Min/Max     : {min_lat:.3f}s / {max_lat:.3f}s")
        print(f"🎯 Taxa de Sucesso      : {(self.processed / self.total_files * 100):.1f}%")
        print("="*60)

def drop_file(source: Path, target: Path, filename: str, tracker: Dict, metrics: TestMetrics):
    dest = target / filename
    try:
        if dest.exists():
            dest.unlink()
        shutil.copy2(source / filename, dest)
        tracker[filename] = time.perf_counter()
        metrics.total_files += 1
    except Exception as e:
        logger.error(f"❌ Falha ao copiar {filename}: {e}")

def monitor_output(processed_dir: Path, review_dir: Path, tracker: Dict, metrics: TestMetrics, timeout: float) -> None:
    end_time = time.time() + timeout
    checked_files = set()

    while time.time() < end_time and (len(tracker) - len(checked_files)) > 0:
        for fname, start in list(tracker.items()):
            if fname in checked_files:
                continue

            if (processed_dir / fname).exists():
                latency = time.perf_counter() - start
                metrics.add_success(latency)
                checked_files.add(fname)
                continue

            if (review_dir / fname).exists():
                latency = time.perf_counter() - start
                metrics.add_review(latency)
                checked_files.add(fname)
                continue

        time.sleep(0.5)  # Polling interval

    # Marca remanescentes como não rastreados
    for fname in tracker:
        if fname not in checked_files:
            metrics.failed_to_track += 1

def main():
    parser = argparse.ArgumentParser(description="Teste de carga para Automação OS")
    parser.add_argument("--source", type=Path, default="./sample_images", help="Diretório com imagens de teste")
    parser.add_argument("--input", type=Path, default="./input", help="Diretório de entrada (monitorado)")
    parser.add_argument("--processed", type=Path, default="./output/processadas")
    parser.add_argument("--review", type=Path, default="./output/revisao")
    parser.add_argument("--count", type=int, default=20, help="Quantidade de arquivos para soltar")
    parser.add_argument("--rate", type=float, default=2.0, help="Arquivos por segundo (controle de burst)")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout máximo em segundos")
    args = parser.parse_args()

    if not args.source.exists():
        logger.error(f"❌ Diretório fonte não encontrado: {args.source}")
        return

    images = [f for f in args.source.iterdir() if f.is_file() and f.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}]
    if not images:
        logger.error("❌ Nenhuma imagem válida encontrada no diretório fonte.")
        return

    logger.info(f"🚀 Iniciando teste: {args.count} arquivos @ {args.rate}/s | Timeout: {args.timeout}s")
    metrics = TestMetrics()
    metrics.start_time = time.time()
    tracker: Dict[str, float] = {}

    # Controle de ritmo
    interval = 1.0 / args.rate if args.rate > 0 else 0.1
    selected = images[:args.count] * (args.count // len(images) + 1)
    selected = selected[:args.count]

    with ThreadPoolExecutor(max_workers=min(args.count, 8)) as executor:
        for img in selected:
            future = executor.submit(drop_file, args.source, args.input, img.name, tracker, metrics)
            time.sleep(interval)
        
        # Aguarda finalizção das cópias
        [f.result() for f in executor]

    logger.info("📡 Monitorando resultados...")
    monitor_output(args.processed, args.review, tracker, metrics, args.timeout)
    metrics.report()

if __name__ == "__main__":
    main()