#  OCR Order Service | Microserviço de Validação, Assinatura Virtual e  Sistema de Processamento de Documentos/Arquivamento de OS.

**Resolução do gargalo de aceite técnico em Ordens de Serviço: validação automática de placa, captura de assinatura digital auditável, segregação por frota e fechamento de ciclo com ERP.** 

Este projeto é uma solução robusta para ingestão de documentos, processamento de OCR de placas (padrão Mercosul/Antigo), gestão de frotas e coleta de assinaturas virtuais com trilha de auditoria imutável.

Projetado para oficinas centrais que prestam serviços diversos para gestoras de frota e locadoras que exigem rastreabilidade, conformidade e escalabilidade operacional.

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green) ![Docker](https://img.shields.io/badge/Docker-24.0+-blue) ![License](https://img.shields.io/badge/License-MIT-yellow) ![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)

---

## 🔍 O Desafio Operacional: Assinatura em OS e o Ciclo de Confirmação Quebrado

Em operações que atendem locadoras e empresas com frotas de 150 a 500+ veículos, a **Ordem de Serviço (OS) não é um documento interno**. É o comprovante técnico de entrega, a base de faturamento e o único vínculo confiável entre oficina e cliente.

Quando a assinatura de aceite falta, chega atrasada ou é coletada de forma analógica/desestruturada, o ciclo operacional se fragmenta:
- 📉 **Financeiro:** Faturas contestadas por “serviço não aceito”, glosas não justificadas, capital de giro travado em ciclos de 30–60 dias.
- 🔄 **Operacional:** Perseguição manual de assinaturas, OS duplicadas, retrabalho de cadastro, gargalos no balcão de saída e perda de SLA.
- ⚖️ **Jurídico & Compliance:** Ausência de trilha auditável para seguros, garantias, LGPD ou fiscalizações. Impossibilidade de provar autoria, timestamp ou condições de entrega.
- 📊 **Estratégico:** Escalabilidade limitada. Sem validação padronizada, a operação cresce linearmente, com margem erosiva por atrito administrativo e risco reputacional em licitações.

**Sem assinatura válida e arquivada, não há confirmação de serviço.** E sem confirmação, não há fechamento comercial, auditoria confiável ou relacionamento sustentável com grandes locadoras.

---

## ✅ A Solução Técnica

O **OCR Order Service** elimina o ponto cego de aceite técnico. É um microserviço *stateless*, orientado a eventos e containerizado, que automatiza o ciclo completo da OS:

1. Recebe imagens ou PDFs via HTTP, S3 ou sistema de arquivos  
2. Extrai e valida placas com algoritmo oficial da CONTRAN  
3. Segmenta automaticamente por locadora/frota  
4. Disponibiliza canvas de assinatura virtual em tablets/navegadores  
5. Aplica overlay criptografado, gera hash SHA-256 e registra trilha imutável (IP real, signatário, papel, timestamp)  
6. Arquiva o documento, atualiza estado no DB e notifica o ERP via webhook assíncrono  

Resultado: **aceite técnico em <10s, zero perda de evidência, arquivamento automático e fechamento de ciclo sem intervenção manual.**

---

## 🏗️ Arquitetura & Stack
```mermaid
graph LR
    A[ERP / Tablet / S3 / Pasta] -->|POST /ingest| B(FastAPI Gateway)
    B --> C{Roteamento}
    C -->|Imagem| D[OCR Pipeline]
    C -->|PDF| E [Assinatura Virtual]
    D --> F [Validação CONTRAN + Mapeamento Frota]
    E --> G [Overlay + Audit Trail]
    F --> H [SQLite WAL]
    G --> H[Webhook ERP Async]
    H --> I[Prometheus / Grafana]
```

# 🛠️ Stack Técnica do Projeto

| Componente | Tecnologia |
| :--- | :--- |
| **Linguagem** | Python 3.11+ |
| **Framework Web** | FastAPI + Uvicorn |
| **Visão Computacional** | OpenCV, Pytesseract |
| **Manipulação PDF/Overlay** | PyPDF2, ReportLab |
| **Banco de Dados** | SQLite 3 (WAL mode) |
| **Monitoramento** | Prometheus, Grafana |
| **Containerização** | Docker & Docker Compose |
| **Testes** | pytest, httpx, Pillow, opencv-python |
---


---

##  Funcionalidades

| Camada | Recursos |
| :--- | :--- |
| **Ingestão & Roteamento** | HTTP multipart, S3/MinIO, Watchdog local. Separação automática: imagens → OCR, PDFs → assinatura |
| **OCR & Visão Computacional** | Pré-processamento OpenCV, rotação automática (0°/90°/180°/270°), threshold adaptável |
| **Validação de Negócio** | Regex Mercosul/antigo, algoritmo oficial CONTRAN (dígito verificador), limiar de confiança configurável |
| **Gestão de Frotas** | Mapeamento dinâmico (prefix/regex/exact), cache `@lru_cache`, hot-reload sem restart, segregação `/{LOCADORA}/{PLACA}/` |
| **Assinatura Virtual** | Canvas responsivo, validação PNG + magic bytes, overlay seguro, hash SHA-256, extração IP proxy-aware, trilha imutável |
| **Persistência & Idempotência** | SQLite (WAL mode), 3 tabelas (`processed_files`, `pending_signatures`, `signature_audit`), hash SHA256, `INSERT OR REPLACE` |
| **Integração ERP** | Webhooks assíncronos não-bloqueantes (`ocr_plate_processed`, `os_cycle_closed`), headers customizáveis, timeout seguro |
| **Observabilidade** | `/health`, `/ready`, `/metrics` (Prometheus), Grafana auto-provisionado, logs estruturados, métricas de SLA |
| **Segurança & Compliance** | Container não-root, validação Pydantic, LGPD-aligned (imagem descartada pós-overlay), fallback graceful, `.p12` isolado |

---

## ⚡ Início Rápido

### Pré-requisitos
* **Docker Engine / Desktop** 24.0+
* **Docker Compose (V2)** 2.20+
* **make** (Linux/macOS) ou **WSL2/Git Bash** (Windows)

### Instalação & Execução
```bash
# Clone o repositório
git clone [https://github.com/seu-usuario/seu-projeto.git](https://github.com/seu-usuario/seu-projeto.git)
cd seu-projeto

# Inicie o ambiente via Docker Compose
docker-compose up -d

# Verifique o status dos serviços
docker-compose ps

# Instalação & Execução

# 1. Clone e configure
git clone <URL_DO_REPO> && cd Automacao-Ordens-de-Servico
cp .env.example .env

# 2. Prepare ambiente, construa e inicie
make setup && make build && make up

# 3. Verifique saúde do serviço
make health
# Esperado: ✅ /health OK | ✅ /ready OK
```
---

### 🔗 Acessos 

| Serviço | URL | Credenciais |
| :--- | :--- | :--- |
| **API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | Pública |
| **Grafana** | [http://localhost:3000](http://localhost:3000) | `admin` / `admin` |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | Pública |

---

### ✍️ Assinatura Virtual

| Endpoint | Método | Descrição |
| :--- | :--- | :--- |
| `/sign?plate=ABC1D23` | `GET` | Retorna iframe com canvas de assinatura. Ideal para tablets ou browsers. |
| `/api/v1/sign-virtual` | `POST` | Aplica overlay no PDF, registra trilha de auditoria (audit trail), arquiva o documento e dispara o fechamento de ciclo no ERP. |


**Exemplo de Payload (`POST /api/v1/sign-virtual`):**
```json
{
  "file_hash": "a1b2c3d4...",
  "signature_base64": "data:image/png;base64,...",
  "metadata": {
    "signer_name": "João Silva",
    "document_id": "OS-12345"
  }
}
```

Aqui estão as secções de **Persistência** e **Segurança** formatadas com tabelas e realces para garantir a melhor legibilidade no GitHub:

---

## 🗄️ Persistência & Idempotência

O serviço utiliza **SQLite com WAL mode** (*Write-Ahead Logging*), garantindo concorrência segura para leituras e escritas simultâneas sem a complexidade de um banco de dados externo.

| Tabela | Propósito | Chave Primária / Index |
| :--- | :--- | :--- |
| `processed_files` | Garante a idempotência do processamento de imagens e OCR. | `file_hash` (SHA256) |
| `pending_signatures` | Controle de estados dos PDFs (aguardando, assinado, arquivado). | `file_hash`, `status` |
| `signature_audit` | Trilha de auditoria imutável para todas as assinaturas virtuais. | `id`, `file_hash`, `signature_hash` |

> **Idempotência:** Todo arquivo ingerido gera um hash único antes de qualquer processamento. Isso garante que reinícios de serviço, quedas de conexão ou reenvios pelo ERP não gerem duplicidade de dados ou custos desnecessários de OCR.

---

## 🛡️ Segurança & Compliance

| Risco | Mitigação Implementada |
| :--- | :--- |
| **Falsificação de assinatura** | Registro de Hash SHA256 + IP real (proxy-aware) + Timestamp + Dados do signatário em `signature_audit`. |
| **Injeção de payload** | Validação rigorosa via **Pydantic** + Verificação de *magic bytes* de ficheiros PNG + Limite de tamanho de upload. |
| **IP incorreto (Proxy/LB)** | Extração segura de cabeçalhos: `X-Forwarded-For` → `X-Real-IP` → `request.client`. |
| **Webhook ERP indisponível** | Execução em *Thread daemon* com timeout de 5s e estratégia de fallback não-bloqueante. |
| **LGPD / Retenção de dados** | Armazenamento restrito a metadados e hashes. A imagem bruta da assinatura é descartada imediatamente após o overlay. |
| **Segurança do Container** | Execução como `appuser` (non-root), volumes de escrita mapeados e `HEALTHCHECK` nativo. |

### ⚠️ Nota sobre Validade Jurídica
A **Assinatura Virtual (E-Sign)** nativa cobre aceites operacionais e controles internos. Para conformidade com validade jurídica plena (padrão **ICP-Brasil** ou **LGPD contratual**), é necessário ativar as variáveis `SIGN_CERT_PATH` e `SIGN_CERT_PASSWORD` para processamento via módulo **pdftk PKCS#7**.

---

##  📜 Licença

🔒 **AVISO DE LICENÇA:** Este projeto é disponibilizado para avaliação técnica. Clonagem para estudo é permitida. **Forks, modificações, distribuições, contribuições ou uso comercial sem autorização prévia são expressamente proibidos.** Consulte o arquivo [LICENSE](LICENSE) para detalhes.