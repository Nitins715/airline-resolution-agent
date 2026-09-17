# Airline Resolution Assistant

A customer-facing web application that handles airline flight disruption resolution (cancellations and delays) using an AI-grounded approach.

## Overview
This project simulates an airline's automated customer service assistant. It allows customers to inquire about disrupted flights and receive compensation, rebooking, or hotel arrangements. The assistant follows strict deterministic policies while using AI for natural language understanding and generation.

## AI Architecture
- **Hugging Face Model**: `mistralai/Mistral-7B-Instruct-v0.3` (or customizable) is used for natural language understanding and empathetic response generation.
- **LangGraph**: Orchestrates the agent workflow (state graph: context identification → intent detection → data retrieval → policy evaluation → resolution execution).
- **LangChain**: Used for prompt structuring and LLM integrations.
- **PolicyEngine**: A deterministic, rule-based engine that has the final authority on all compensation limits, rebooking rules, and escalation thresholds. The LLM is strictly prohibited from overriding or hallucinating policy decisions.

## Tech Stack
- **Backend**: Django 5.2, Django REST Framework (DRF)
- **Database**: PostgreSQL (via `dj-database-url`, `psycopg2-binary`) or local SQLite fallback
- **AI/Workflow**: LangChain, LangGraph, Hugging Face Hub API
- **Frontend**: Vanilla HTML/CSS/JS with responsive design
- **Deployment**: Render (Docker or Native Python), Gunicorn, Whitenoise

## Local Setup (Using `venv`)

1. **Clone the repository and enter the directory**:
   ```bash
   git clone <repository_url>
   cd ResolutionAgent
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
   *Edit `.env` to add your `HUGGINGFACEHUB_API_TOKEN`.*

5. **Run Migrations and Seed Data**:
   ```bash
   python manage.py migrate
   python manage.py seed_assignment_data
   ```

6. **Start the Development Server**:
   ```bash
   python manage.py runserver
   ```
   Open `http://127.0.0.1:8000/` in your browser.

## Testing

Run the full test suite (unit tests + API scenario tests) using pytest:
```bash
pytest tests/ -v
```

## Hugging Face Configuration

The application uses Hugging Face Inference APIs to process natural language without heavy local computation.

In your `.env` or Render environment variables, configure:
```env
HUGGINGFACEHUB_API_TOKEN=your_token_here
HF_MODEL_NAME=mistralai/Mistral-7B-Instruct-v0.3
```
*Note: Never hardcode tokens in the source code. If running a local model is preferred, update `hf_client.py` to point to your local endpoint (e.g., Ollama or vLLM) by changing the API URL structure.*

## Render Deployment

This app is ready to be deployed on Render using either the `render.yaml` Blueprint or Docker.

**Option 1: Using render.yaml (Blueprint)**
1. Connect your repository to Render.
2. Render will automatically detect `render.yaml` and provision a Web Service and a PostgreSQL database.
3. Add your `HUGGINGFACEHUB_API_TOKEN` to the Web Service environment variables in the Render Dashboard.

**Option 2: Using Docker**
1. Create a new Web Service on Render and select "Docker" as the environment.
2. Render will build using the provided `Dockerfile`.
3. Add `DATABASE_URL` and `HUGGINGFACEHUB_API_TOKEN` to the environment variables.

*The app binds to `0.0.0.0:$PORT` automatically and serves static files via Whitenoise.*

## Demo Scenarios

The seed command populates the database with three specific assignment scenarios:

1. **Priya Nair (Gold, SK4821X)**: Flight cancelled. Requests a full refund + free business class upgrade. (Outcome: Refund processed, upgrade denied/escalated).
2. **Arvind Kulkarni (Silver, TR1190B)**: Flight delayed 4h. Requests hotel accommodation. (Outcome: Meal voucher + lounge granted, hotel denied because delay < 5h).
3. **Meher Kaur (Platinum, WL7742)**: Flight delayed 6h. Requests full-night hotel + ₹2,000 fare waiver. (Outcome: Hotel for delayed hours only granted, ₹2,000 waiver escalated to supervisor).

A built-in scenario runner is available in the UI to test these flows with a single click.

## API Health Check
A health endpoint is available at `/api/health/` for load balancers and uptime monitoring.
