# AI Talent Pool Generation System

An AI-powered backend system that transforms job descriptions into structured hiring requirements and serves as the foundation for candidate discovery, evaluation, ranking, and talent pool generation.

The system leverages FastAPI, Ollama, PostgreSQL, and AI-driven extraction techniques to automate the initial stages of talent acquisition.

---

## Overview

The goal of this project is to build an end-to-end Talent Intelligence Platform capable of:

* Extracting hiring requirements from job descriptions
* Discovering candidates across multiple sources
* Evaluating candidate suitability
* Ranking candidates based on fit
* Generating talent pools for recruiters

---

## Current Features

### Job Description Analysis

Extracts:

* Job Role
* Required Skills
* Experience Requirements
* Qualifications

### AI-Powered Processing

Uses Ollama with locally hosted LLMs for:

* Information extraction
* Structured JSON generation
* Requirement identification

### PostgreSQL Persistence

Stores:

* Original Job Description
* Extracted Job Role
* Required Skills
* Experience Requirements
* Qualifications
* Metadata and timestamps

### REST API

Built using FastAPI with automatic Swagger documentation.

---

## Technology Stack

### Backend

* FastAPI
* Uvicorn

### AI Layer

* Ollama
* Qwen 2.5 Coder

### Database

* PostgreSQL
* Neon Database
* SQLAlchemy

### Data Validation

* Pydantic

---

## Project Structure

```text
app/
│
├── api/
│   └── router.py
│
├── core/
│   ├── config.py
│   └── database.py
│
├── integrations/
│   └── ollama_client.py
│
├── models/
│   └── job_description.py
│
├── repositories/
│   └── job_description_repository.py
│
├── schemas/
│   └── jd_schema.py
│
├── services/
│   └── jd_extraction_service.py
│
└── main.py

tests/

requirements.txt
.env
README.md
```

---

## Setup

### Clone Repository

```bash
git clone <repository-url>
cd ai-talent-pool-generation-system
```

### Create Virtual Environment

```bash
python -m venv venv
```

### Activate Virtual Environment

Windows:

```bash
venv\Scripts\activate
```

Linux/macOS:

```bash
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

Create a `.env` file in the project root.

```env
APP_NAME=AI Talent Pool Generation System
APP_VERSION=1.0.0

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:3b

DATABASE_URL=<your_neon_connection_string>
```

---

## Ollama Setup

Pull the model:

```bash
ollama pull qwen2.5-coder:3b
```

Verify installation:

```bash
ollama list
```

Start Ollama:

```bash
ollama serve
```

---

## Run Application

Start FastAPI:

```bash
uvicorn app.main:app --reload
```

Application:

```text
http://127.0.0.1:8000
```

Swagger Documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Available Endpoints

### Health Check

```http
GET /api/health
```

### Ollama Connectivity Test

```http
POST /api/test_ollama
```

### Extract Job Description

```http
POST /api/extract_jd
```

### Extract and Save Job Description

```http
POST /api/extract_and_save_jd
```

Example Request:

```json
{
  "job_description": "We are hiring a Python Backend Developer with 3+ years of experience. Required skills include Python, FastAPI, PostgreSQL, Docker and Git."
}
```

---

## Current Workflow

```text
Job Description
       │
       ▼
FastAPI
       │
       ▼
Ollama
       │
       ▼
Structured Job Requirements
       │
       ▼
PostgreSQL
       │
       ▼
API Response
```

---

## Development Roadmap

### Phase 1

* FastAPI Setup
* Ollama Integration

### Phase 2

* Job Description Extraction

### Phase 3

* PostgreSQL Persistence

### Upcoming Phases

### Phase 4

* Candidate Discovery
* GitHub Integration

### Phase 5

* Candidate Normalization
* Candidate Deduplication

### Phase 6

* Semantic Search
* Vector Embeddings
* Similarity Matching

### Phase 7

* Candidate Evaluation
* AI Scoring Engine

### Phase 8

* Talent Pool Generation
* Candidate Ranking
* Recommendation Engine

---

## Current Status

Completed:

* FastAPI Backend Setup
* Ollama Integration
* Job Description Extraction
* PostgreSQL Persistence

In Progress:

* Candidate Discovery Pipeline

---

## License

This project is under active development for learning, experimentation, and portfolio purposes.
